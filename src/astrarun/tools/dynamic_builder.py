"""Governed DynamicToolBuilder for AstraRun 1.0.

Provides model-independent dynamic tool generation, AST safety screening,
sandbox verification, governed artifact delivery via ExecutionBroker,
and bounded self-repair (max 2 attempts).
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.machine.resource_governor import GovernorDecision, ResourceGovernor
from astrarun.sandbox.manager import SandboxManager
from astrarun.sandbox.models import SandboxConfig, SandboxProfile, SandboxResult
from astrarun.security.execution_broker import ActionCategory, ActionProposal, ExecutionBroker
from astrarun.tools.ast_inspector import ASTInspectionResult, ASTInspector
from astrarun.tools.candidate import CandidateTool, CodeProvenance, DependencyRequest, RevisionRecord
from astrarun.tools.registry import ToolRegistry

logger = get_logger("astrarun.tools.dynamic_builder")


class RepairFailureType(str, Enum):
    """Categorized root causes for candidate tool execution failures."""
    SYNTAX_FAILURE = "SYNTAX_FAILURE"
    AST_POLICY_FAILURE = "AST_POLICY_FAILURE"
    IMPORT_FAILURE = "IMPORT_FAILURE"
    RUNTIME_EXCEPTION = "RUNTIME_EXCEPTION"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    SEMANTIC_VERIFICATION_FAILURE = "SEMANTIC_VERIFICATION_FAILURE"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    SECURITY_DENIAL = "SECURITY_DENIAL"


@dataclass
class StructuredRepairPacket:
    """Structured diagnostic packet passed to model repair engine."""
    failure_type: RepairFailureType
    original_goal: str
    current_revision: int
    current_source: str
    entrypoint: str
    exit_code: Optional[int]
    stderr: str
    stdout_tail: str
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    failing_file: Optional[str] = None
    failing_line: Optional[int] = None
    ast_violations: List[str] = field(default_factory=list)
    missing_artifacts: List[str] = field(default_factory=list)
    verification_error: str = ""
    output_dir: str = ""
    analysis: str = ""


@dataclass
class DeliverArtifactProposal:
    """Typed proposal to deliver a verified sandbox artifact to the host."""
    source: Path
    destination: Path
    source_sha256: str
    task_id: str
    user_intent_reason: str = "User requested deliverable placement"


def extract_exception_details(stderr: str) -> Dict[str, Any]:
    """
    Extract structured exception details from Python traceback without bug-specific logic.
    Identifies exception type, message, file, and line number generically.
    """
    exc_type = None
    exc_msg = None
    failing_file = None
    failing_line = None

    file_matches = re.findall(r'File\s+"([^"]+)",\s+line\s+(\d+)', stderr)
    if file_matches:
        failing_file, failing_line_str = file_matches[-1]
        try:
            failing_line = int(failing_line_str)
        except ValueError:
            pass

    exc_match = re.search(r'([A-Za-z_][A-Za-z0-9_]*Error|[A-Za-z_][A-Za-z0-9_]*Exception):\s*(.*)', stderr)
    if exc_match:
        exc_type = exc_match.group(1)
        exc_msg = exc_match.group(2).strip()

    return {
        "exception_type": exc_type,
        "exception_message": exc_msg,
        "failing_file": failing_file,
        "failing_line": failing_line,
    }


class RepairExhaustedError(RuntimeError):
    """Raised when bounded repair attempts are exhausted without success."""
    pass


@dataclass
class DynamicToolExecutionReport:
    """Comprehensive outcome report of dynamic tool synthesis and execution."""
    candidate_tool: CandidateTool
    sandbox_result: SandboxResult
    ast_result: ASTInspectionResult
    repair_attempts: int
    is_success: bool
    artifacts: List[Path] = field(default_factory=list)
    delivered_artifacts: List[Path] = field(default_factory=list)
    error_message: Optional[str] = None


class DynamicToolBuilder:
    """
    Authoritative builder and lifecycle runner for ephemeral dynamic tools.
    """

    def __init__(
        self,
        sandbox_manager: Optional[SandboxManager] = None,
        tool_registry: Optional[ToolRegistry] = None,
        ast_inspector: Optional[ASTInspector] = None,
        model_service: Optional[Any] = None,
        execution_broker: Optional[ExecutionBroker] = None,
        max_repair_attempts: int = 2,
    ) -> None:
        self.sandbox = sandbox_manager or SandboxManager()
        self.registry = tool_registry or ToolRegistry()
        self.inspector = ast_inspector or ASTInspector()
        if model_service is None:
            try:
                from astrarun.cognition.service import ModelService
                self.model_service = ModelService.get_instance()
            except Exception:
                self.model_service = None
        else:
            self.model_service = model_service

        if execution_broker is None:
            try:
                self.execution_broker = ExecutionBroker()
            except Exception:
                self.execution_broker = None
        else:
            self.execution_broker = execution_broker

        self.max_repair_attempts = max_repair_attempts

    def search_existing_capabilities(self, goal: str) -> Optional[str]:
        """Check if goal can be resolved by an existing permanent tool."""
        g = goal.lower().strip()
        for tool in self.registry.list_tools():
            name = tool.name.lower()
            if name in g:
                return tool.name
            if "port" in g and "inspect_port" in name:
                return tool.name
            if "process" in g and "inspect_process" in name:
                return tool.name
            if "folder" in g and "open_folder" in name:
                return tool.name
        return None

    def synthesize_tool_for_goal(self, goal: str, inputs: Optional[Dict[str, Any]] = None) -> CandidateTool:
        """
        Synthesize CandidateTool for a recognized user goal.
        Requires active Qwen2.5-Coder via ModelService; fails closed with MODEL_UNAVAILABLE if offline.
        """
        if self.model_service:
            try:
                candidate = self.model_service.generate_code(goal=goal, context=inputs)
                if candidate and candidate.source_files:
                    from astrarun.core.telemetry import CausalTelemetry, CausalEventType
                    telem = CausalTelemetry.get_instance()
                    telem.emit(
                        event_type=CausalEventType.ARTIFACT_CREATED.value,
                        component="DynamicToolBuilder",
                        output_hash=candidate.compute_source_hash(),
                        data={
                            "tool_id": candidate.tool_id,
                            "entrypoint": candidate.entrypoint,
                            "files": list(candidate.source_files.keys()),
                        },
                    )
                    return candidate
            except Exception as e:
                logger.error("ModelService code generation failed: %s", e)
                raise RuntimeError(f"MODEL_UNAVAILABLE: Code generation failed via ModelService: {e}")

        raise RuntimeError(
            "MODEL_UNAVAILABLE: Real code synthesis requires an active Qwen coder model via ModelService. "
            "Canned or simulated code generation is prohibited in production."
        )

    def repair_code(self, candidate: CandidateTool, repair_context: Any, attempt: int) -> CandidateTool:
        """
        Formulate and apply a structured repair to candidate tool code.
        Leverages Qwen2.5-Coder via ModelService with structured diagnostic context.
        """
        logger.info("Attempting bounded structured repair #%d for tool %s", attempt, candidate.tool_id)
        if self.model_service:
            try:
                repaired = self.model_service.repair_code(candidate, repair_context, attempt)
                if isinstance(repaired, str):
                    repaired = candidate.derive_repaired(repaired, f"Structured repair attempt {attempt}")
                if repaired and repaired.compute_source_hash() != candidate.compute_source_hash():
                    return repaired
            except Exception as e:
                logger.warning("ModelService structured code repair failed: %s", e)

        return candidate

    def deliver_artifact_via_broker(self, proposal: DeliverArtifactProposal) -> bool:
        """
        Deliver a verified sandbox artifact to the host via ExecutionBroker + ActionGate.
        Guarantees host filesystem mutations pass the authoritative security boundary.
        """
        if not self.execution_broker:
            logger.warning("No ExecutionBroker configured; cannot deliver artifact to host.")
            return False

        act_prop = ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={
                "source": str(proposal.source),
                "destination": str(proposal.destination),
                "source_sha256": proposal.source_sha256,
                "task_id": proposal.task_id,
            },
            source="dynamic_tool",
            task_id=proposal.task_id,
            reason=proposal.user_intent_reason,
        )
        res = self.execution_broker.execute(act_prop)
        if res.success:
            logger.info("Artifact delivered via ExecutionBroker: %s -> %s", proposal.source, proposal.destination)
            from astrarun.core.telemetry import CausalTelemetry, CausalEventType
            telem = CausalTelemetry.get_instance()
            telem.emit(
                event_type=CausalEventType.ARTIFACT_DELIVERED.value,
                component="DynamicToolBuilder",
                task_id=proposal.task_id,
                input_hash=proposal.source_sha256,
                output_hash=proposal.source_sha256,
                data={
                    "source": str(proposal.source),
                    "destination": str(proposal.destination),
                },
            )
            return True
        else:
            logger.warning("Artifact delivery blocked by ExecutionBroker: %s (%s)", res.message, res.verdict)
            return False

    def build_and_execute(
        self,
        candidate: CandidateTool,
        timeout_sec: float = 30.0,
    ) -> DynamicToolExecutionReport:
        """
        Execute candidate tool through full governed pipeline with AST checks,
        sandbox dry run, machine pressure awareness, and bounded structured repair.
        """
        # Assess machine resource pressure via ResourceGovernor
        try:
            gov = ResourceGovernor.get_instance()
            decision, reason = gov.assess_state(target_workload="sandbox_execution")
            if decision == GovernorDecision.LOW_MEMORY_EXECUTION_PROFILE:
                logger.warning("ResourceGovernor enforced LOW_MEMORY_EXECUTION_PROFILE: %s", reason)
                timeout_sec = min(timeout_sec, 20.0)
            elif decision == GovernorDecision.SERIALIZE_HEAVY_WORK:
                logger.info("ResourceGovernor enforced SERIALIZE_HEAVY_WORK: %s", reason)
        except Exception:
            pass

        current_tool = candidate
        repair_attempts = 0
        last_ast: Optional[ASTInspectionResult] = None
        last_sb_result: Optional[SandboxResult] = None

        if not current_tool.provenance:
            current_tool.provenance = CodeProvenance(
                task_id=current_tool.task_id,
                model=current_tool.generator_model,
                prompt_hash=hashlib.sha256(current_tool.goal.encode("utf-8")).hexdigest(),
                source_hash=current_tool.compute_source_hash(),
                entrypoint_hash=current_tool.compute_entrypoint_hash(),
                tree_hash=current_tool.compute_tree_hash(),
            )

        while repair_attempts <= self.max_repair_attempts:
            # 1. AST Inspection
            ast_res = self.inspector.inspect_candidate(current_tool)
            last_ast = ast_res

            if not ast_res.is_safe:
                logger.warning("AST safety violation in tool %s: %s", current_tool.tool_id, ast_res.violations)
                # If malicious/security violation, fail closed immediately without repair
                if any("Trust Kernel" in v or "Forbidden module" in v or "Prohibited OS" in v for v in ast_res.violations):
                    return DynamicToolExecutionReport(
                        candidate_tool=current_tool,
                        sandbox_result=SandboxResult(
                            run_id="denied",
                            profile=SandboxProfile.EPHEMERAL_TOOL,
                            status="DENIED",
                            exit_code=-1,
                            stdout="",
                            stderr=f"AST Inspection failed with security violations: {ast_res.violations}",
                            duration_ms=0.0,
                        ),
                        ast_result=ast_res,
                        repair_attempts=repair_attempts,
                        is_success=False,
                        error_message="AST Inspection failed with security violations.",
                    )

                if repair_attempts >= self.max_repair_attempts:
                    return DynamicToolExecutionReport(
                        candidate_tool=current_tool,
                        sandbox_result=SandboxResult(
                            run_id="denied",
                            profile=SandboxProfile.EPHEMERAL_TOOL,
                            status="DENIED",
                            exit_code=-1,
                            stdout="",
                            stderr=f"AST Inspection failed: {ast_res.violations}",
                            duration_ms=0.0,
                        ),
                        ast_result=ast_res,
                        repair_attempts=repair_attempts,
                        is_success=False,
                        error_message="AST Inspection failed with syntax/structure errors.",
                    )

                # Formulate structured AST repair packet
                repair_attempts += 1
                packet = StructuredRepairPacket(
                    failure_type=RepairFailureType.SYNTAX_FAILURE if ast_res.syntax_error else RepairFailureType.AST_POLICY_FAILURE,
                    original_goal=current_tool.goal,
                    current_revision=repair_attempts,
                    current_source=current_tool.source_files.get(current_tool.entrypoint, current_tool.executable_code),
                    entrypoint=current_tool.entrypoint,
                    exit_code=-1,
                    stderr="\n".join(ast_res.violations),
                    stdout_tail="",
                    ast_violations=ast_res.violations,
                    analysis="Syntax or AST validation error detected. Return valid self-contained Python.",
                )
                repaired = self.repair_code(current_tool, packet, repair_attempts)
                if repaired.compute_source_hash() == current_tool.compute_source_hash():
                    break
                current_tool = repaired
                continue

            # 2. Contained Sandbox Execution
            cfg = SandboxConfig(
                run_id=current_tool.task_id or current_tool.tool_id,
                profile=SandboxProfile.EPHEMERAL_TOOL,
                timeout_sec=timeout_sec,
                preserve_on_exit=True,
            )
            sb_res = self.sandbox.execute_candidate(current_tool, config=cfg)
            last_sb_result = sb_res

            # Audit Provenance for this execution revision
            src_h = current_tool.compute_source_hash()
            ep_h = current_tool.compute_entrypoint_hash()
            tr_h = current_tool.compute_tree_hash()
            staged_h = getattr(sb_res, "staged_source_hash", None) or ep_h
            exec_h = getattr(sb_res, "executed_source_hash", None) or ep_h
            gen_req_id = current_tool.task_id or f"req_{int(time.time()*1000)}"

            rev_rec = RevisionRecord(
                revision_number=repair_attempts + 1,
                generation_request_id=gen_req_id,
                sandbox_execution_id=sb_res.run_id,
                request_id=gen_req_id,
                prompt_hash=hashlib.sha256(current_tool.goal.encode("utf-8")).hexdigest(),
                response_hash=hashlib.sha256(current_tool.full_script().encode("utf-8")).hexdigest(),
                source_hash=src_h,
                entrypoint_hash=ep_h,
                tree_hash=tr_h,
                ast_safe=ast_res.is_safe,
                ast_violations=ast_res.violations,
                staged_hash=staged_h,
                executed_hash=exec_h,
                exit_code=sb_res.exit_code,
                stdout_summary=sb_res.stdout[:500],
                stderr_summary=sb_res.stderr[:500],
                artifacts_created=[str(p) for p in sb_res.created_artifacts],
                verification_status="PASSED" if sb_res.is_success else "FAILED",
                parent_revision=repair_attempts if repair_attempts > 0 else None,
                repair_reason="repair_cycle" if repair_attempts > 0 else "initial_synthesis",
            )
            current_tool.provenance.record_revision(rev_rec)

            goal_lower = current_tool.goal.lower()
            has_explicit_error = any(
                err_kw in (sb_res.stdout or "").lower()
                for err_kw in ("error: file", "filenotfounderror", "traceback (most recent call last)")
            )
            goal_expects_json = "json" in goal_lower
            produced_json = any(a.suffix.lower() == ".json" for a in (sb_res.created_artifacts or []))

            execution_truly_succeeded = sb_res.is_success and not has_explicit_error
            if goal_expects_json and not produced_json:
                execution_truly_succeeded = False

            if execution_truly_succeeded:
                logger.info("Dynamic tool %s executed successfully in %sms", current_tool.tool_id, sb_res.duration_ms)
                all_artifacts = list(sb_res.created_artifacts)
                # Ensure all tool source files created in sandbox workspace are captured as artifacts
                if hasattr(sb_res, "working_dir") and sb_res.working_dir:
                    for src_name in getattr(current_tool, "source_files", {}):
                        src_p = Path(sb_res.working_dir) / src_name
                        if src_p.exists() and src_p not in all_artifacts:
                            all_artifacts.append(src_p)

                delivered_artifacts: List[Path] = []

                # Parse stdout for explicit printed artifact paths
                for line in sb_res.stdout.splitlines():
                    match = re.search(r"([A-Za-z]:\\[^\r\n,;\"']+\.(?:png|jpg|jpeg|py|txt|csv|json|html|log|dat))", line)
                    if match:
                        found_p = Path(match.group(1).strip())
                        if found_p.exists() and found_p not in all_artifacts:
                            all_artifacts.append(found_p)

                # Authoritative Artifact Delivery via ExecutionBroker
                # Dynamic code writes ONLY into governed output scope.
                # If the goal explicitly requested a host destination, propose delivery via ExecutionBroker.
                goal_lower = current_tool.goal.lower()
                negated_delivery = any(w in goal_lower for w in ("don't copy", "do not copy", "leave it in", "leave in workspace", "don't save to", "do not move"))

                target_dest_dir = None
                if not negated_delivery:
                    # Check for explicit Windows directory path in goal (e.g. under: C:\path\to\dir or in D:\...)
                    path_match = re.search(r'\b(?:under|in|into|at|to)\s*:?\s*([A-Za-z]:\\[a-zA-Z0-9_\-\\]+)', current_tool.goal, re.I)
                    if path_match:
                        target_dest_dir = Path(path_match.group(1).strip())
                    elif "desktop" in goal_lower:
                        target_dest_dir = Path.home() / "Desktop"
                    elif "documents" in goal_lower:
                        target_dest_dir = Path.home() / "Documents"
                    elif "downloads" in goal_lower:
                        target_dest_dir = Path.home() / "Downloads"

                if target_dest_dir:
                    target_dest_dir.mkdir(parents=True, exist_ok=True)
                    for art in all_artifacts:
                        if art.parent != target_dest_dir and art.is_file():
                            art_hash = hashlib.sha256(art.read_bytes()).hexdigest()
                            prop = DeliverArtifactProposal(
                                source=art,
                                destination=target_dest_dir / art.name,
                                source_sha256=art_hash,
                                task_id=current_tool.task_id,
                                user_intent_reason=f"User requested artifact placement in {target_dest_dir.name}",
                            )
                            if self.deliver_artifact_via_broker(prop):
                                delivered_path = target_dest_dir / art.name
                                delivered_artifacts.append(delivered_path)

                report_artifacts = delivered_artifacts if delivered_artifacts else all_artifacts
                return DynamicToolExecutionReport(
                    candidate_tool=current_tool,
                    sandbox_result=sb_res,
                    ast_result=ast_res,
                    repair_attempts=repair_attempts,
                    is_success=True,
                    artifacts=report_artifacts,
                    delivered_artifacts=delivered_artifacts,
                )

            # Failure during sandbox execution -> Bounded structured repair
            logger.warning("Sandbox execution failed (exit_code=%s): %s", sb_res.exit_code, sb_res.stderr)
            if repair_attempts >= self.max_repair_attempts:
                break

            repair_attempts += 1
            if not sb_res.stderr and (has_explicit_error or (goal_expects_json and not produced_json)):
                sb_res.stderr = f"Runtime validation failed: stdout reported '{sb_res.stdout.strip()}'. Expected deliverables (e.g. JSON file) were not created. Ensure sample input file is created and written before reading, and results are saved to JSON."
            err_text = (sb_res.stderr or "").strip() or (sb_res.stdout or "").strip()
            exc_details = extract_exception_details(err_text)

            if "ImportError" in err_text or "ModuleNotFoundError" in err_text:
                ftype = RepairFailureType.IMPORT_FAILURE
                diag = f"Import error: {exc_details.get('exception_message') or 'Module not found'}."
            elif "SyntaxError" in err_text:
                ftype = RepairFailureType.SYNTAX_FAILURE
                diag = f"Python syntax error at line {exc_details.get('failing_line') or 'unknown'}."
            elif "Timeout" in err_text or sb_res.status == "TIMEOUT":
                ftype = RepairFailureType.TIMEOUT
                diag = "Process execution timed out."
            else:
                ftype = RepairFailureType.RUNTIME_EXCEPTION
                diag = f"Runtime exception: {exc_details.get('exception_type') or 'Exception'}."

            packet = StructuredRepairPacket(
                failure_type=ftype,
                original_goal=current_tool.goal,
                current_revision=repair_attempts,
                current_source=current_tool.source_files.get(current_tool.entrypoint, current_tool.executable_code),
                entrypoint=current_tool.entrypoint,
                exit_code=sb_res.exit_code,
                stderr=sb_res.stderr,
                stdout_tail=sb_res.stdout[-500:],
                exception_type=exc_details.get("exception_type"),
                exception_message=exc_details.get("exception_message"),
                failing_file=exc_details.get("failing_file"),
                failing_line=exc_details.get("failing_line"),
                output_dir=str(sb_res.output_dir or sb_res.working_dir or ""),
                analysis=diag,
            )

            repaired_tool = self.repair_code(current_tool, packet, repair_attempts)
            if isinstance(repaired_tool, str):
                repaired_tool = current_tool.derive_repaired(repaired_tool, f"Structured repair attempt {repair_attempts}")
            if repaired_tool.compute_source_hash() == current_tool.compute_source_hash():
                break
            current_tool = repaired_tool

        # If loop exits without success
        return DynamicToolExecutionReport(
            candidate_tool=current_tool,
            sandbox_result=last_sb_result or SandboxResult(
                run_id="error",
                profile=SandboxProfile.EPHEMERAL_TOOL,
                status="FAILED",
                exit_code=-1,
                stdout="",
                stderr="Max repair attempts exhausted.",
                duration_ms=0.0,
            ),
            ast_result=last_ast or ASTInspectionResult(is_safe=False),
            repair_attempts=repair_attempts,
            is_success=False,
            error_message="Tool execution failed and bounded repair attempts were exhausted.",
        )
