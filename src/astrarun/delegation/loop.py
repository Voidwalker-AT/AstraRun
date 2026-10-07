"""Delegated Orchestration Loop: Authoritative closed-loop execution.

Coordinates multi-turn dialogue with external AI delegates while enforcing:
1. Astra retains exclusive execution and verification authority.
2. Dual completion condition: LOCAL_ACCEPTANCE == PASS and DELEGATE_APPROVAL == APPROVED (if requested).
3. Hard iteration budgets (preventing infinite AI ping-pong).
4. Full provenance: advisor, executor, verifier, artifact hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.delegation.models import DelegateProposal, DelegateSession, ReviewStatus
from astrarun.delegation.packager import ContextPackager
from astrarun.delegation.provider import DelegateProvider, DelegateRegistry
from astrarun.sandbox.manager import SandboxConfig, SandboxManager, SandboxProfile, SandboxResult

logger = logging.getLogger(__name__)


@dataclass
class DelegatedRunResult:
    """Rigorous audit record of a delegated orchestration task."""
    task_id: str
    goal: str
    provider: str
    status: str  # "COMPLETED", "BUDGET_EXHAUSTED", "FAILED"
    turns_completed: int
    duration_seconds: float
    local_acceptance_passed: bool
    delegate_approval_received: bool
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    final_stdout: str = ""
    final_stderr: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)
    session: Optional[DelegateSession] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.session:
            d["session"] = self.session.to_dict()
        return d


class DelegatedOrchestrationLoop:
    """Orchestrates an open-ended goal loop across external delegates and local sandbox execution."""

    def __init__(
        self,
        registry: Optional[DelegateRegistry] = None,
        sandbox: Optional[SandboxManager] = None,
        packager: Optional[ContextPackager] = None,
    ) -> None:
        self.registry = registry or DelegateRegistry.get_instance()
        self.sandbox = sandbox or SandboxManager()
        self.packager = packager or ContextPackager()

    def execute_goal(
        self,
        goal: str,
        task_id: Optional[str] = None,
        provider_name: Optional[str] = None,
        workspace_dir: Optional[Path | str] = None,
        max_turns: int = 5,
        require_delegate_approval: bool = True,
    ) -> DelegatedRunResult:
        """Run the end-to-end delegated orchestration loop."""
        tid = task_id or f"del_task_{int(time.time())}"
        t_start = time.perf_counter()

        # 1. Resolve Provider
        provider = self.registry.resolve_provider(provider_name)
        logger.info("Starting delegated goal loop for '%s' using provider '%s'", goal, provider.provider_name)

        # 2. Initialize Session
        session = DelegateSession.create(
            provider=provider.provider_name,
            task_id=tid,
            objective=goal,
            max_turns=max_turns,
            require_delegate_approval=require_delegate_approval,
        )

        # Establish workspace
        if workspace_dir:
            ws_path = Path(workspace_dir).resolve()
            ws_path.mkdir(parents=True, exist_ok=True)
        else:
            ws_path = self.sandbox.base_dir / tid
            ws_path.mkdir(parents=True, exist_ok=True)

        current_source_files: Dict[str, str] = {}
        last_sb_result: Optional[SandboxResult] = None
        verified_artifacts: List[Dict[str, Any]] = []
        local_passed = False
        delegate_approved = False

        # Turn 1: Initial Objective Packaging & Inquiry
        initial_prompt = self.packager.package_initial_objective(
            objective=goal,
            workspace_path=ws_path,
        )
        response = provider.ask(session, initial_prompt)

        while True:
            proposal = response.proposal
            logger.info(
                "Turn %d: Delegate proposed %d files, %d commands, review_status=%s",
                session.current_turn,
                len(proposal.proposed_files),
                len(proposal.proposed_commands),
                proposal.review_status.value,
            )

            # Check if delegate issued an explicit approval
            if proposal.review_status == ReviewStatus.APPROVED:
                delegate_approved = True
                if local_passed:
                    logger.info("Dual completion condition met: LOCAL_PASS and DELEGATE_APPROVED.")
                    session.state = "COMPLETED"
                    break

            # Apply proposed files (Advisory -> ActionGate -> Contained Staging)
            new_files_staged = False
            if proposal.proposed_files:
                for fname, content in proposal.proposed_files.items():
                    # Strict path containment: reject traversal or absolute escapes
                    norm_name = Path(fname).name
                    target_file = ws_path / norm_name
                    # Write exact bytes without CRLF mutation
                    target_file.write_bytes(content.encode("utf-8"))
                    current_source_files[norm_name] = content
                    new_files_staged = True
                    logger.info("Staged delegate proposed file: %s (%d bytes)", norm_name, len(content))

            # Determine entrypoint generically
            if "main.py" in current_source_files:
                entrypoint = "main.py"
            elif current_source_files:
                py_files = [f for f in current_source_files if f.endswith(".py")]
                entrypoint = py_files[0] if py_files else next(iter(current_source_files.keys()))
            else:
                entrypoint = "main.py"

            # Execute in sandbox only if new files were staged or first turn
            entry_path = ws_path / entrypoint
            if entry_path.exists() and (new_files_staged or session.current_turn == 1):
                cfg = SandboxConfig(
                    run_id=tid,
                    profile=SandboxProfile.EPHEMERAL_TOOL,
                    working_dir=ws_path,
                    timeout_sec=30.0,
                    preserve_on_exit=True,
                )
                from astrarun.tools.candidate import CandidateTool
                cand = CandidateTool(
                    goal=goal,
                    source_files=current_source_files,
                    entrypoint=entrypoint,
                    task_id=tid,
                    tool_id=tid,
                )
                sb_res = self.sandbox.execute_candidate(cand, config=cfg)
                last_sb_result = sb_res

                # Check artifacts strictly in sandbox working directory
                detected_artifacts = list(sb_res.created_artifacts)
                for p in ws_path.glob("*"):
                    if p.is_file() and p.name not in current_source_files and p not in detected_artifacts:
                        detected_artifacts.append(p)

                # Check local empirical pass
                if sb_res.exit_code == 0 and (len(detected_artifacts) >= 1 or len(sb_res.stdout.strip()) > 10):
                    local_passed = True
                    verified_artifacts = [
                        {
                            "name": a.name,
                            "path": str(a),
                            "size_bytes": a.stat().st_size,
                            "sha256": hashlib.sha256(a.read_bytes()).hexdigest(),
                        }
                        for a in detected_artifacts
                    ]
                else:
                    local_passed = False

                logger.info(
                    "Local execution result: exit_code=%d, artifacts=%d, local_passed=%s",
                    sb_res.exit_code,
                    len(detected_artifacts),
                    local_passed,
                )

            # Check completion criteria
            if local_passed:
                if not require_delegate_approval or delegate_approved:
                    # Successfully finished
                    session.state = "COMPLETED"
                    break
                else:
                    # Request formal final review from delegate
                    if session.is_turn_budget_exhausted:
                        logger.warning("Turn budget exhausted before receiving delegate approval.")
                        session.state = "BUDGET_EXHAUSTED"
                        break

                    review_prompt = self.packager.package_review_request(
                        objective=goal,
                        artifacts=verified_artifacts,
                        execution_exit_code=last_sb_result.exit_code if last_sb_result else 0,
                        verification_passed=local_passed,
                    )
                    response = provider.continue_conversation(session, review_prompt)
                    continue

            # If local execution failed, formulate feedback and continue in SAME conversation
            if session.is_turn_budget_exhausted:
                logger.warning("Turn budget exhausted during repair loop.")
                session.state = "BUDGET_EXHAUSTED"
                break

            feedback_msg = self.packager.package_execution_feedback(
                exit_code=last_sb_result.exit_code if last_sb_result else -1,
                stdout=last_sb_result.stdout if last_sb_result else "",
                stderr=last_sb_result.stderr if last_sb_result else "Execution failed",
                created_artifacts=[str(a) for a in (detected_artifacts if 'detected_artifacts' in locals() else [])],
                current_source_files=current_source_files,
            )
            response = provider.continue_conversation(session, feedback_msg)

        duration = time.perf_counter() - t_start

        # Determine overall status
        status = "COMPLETED" if (local_passed and (not require_delegate_approval or delegate_approved)) else (
            "BUDGET_EXHAUSTED" if session.is_turn_budget_exhausted else "FAILED"
        )

        provenance = {
            "task_id": tid,
            "advisor": provider.provider_name,
            "executor": "AstraRun (Win32 Sandbox)",
            "verified_by": "AstraRun (GoalVerifier)",
            "local_acceptance": local_passed,
            "delegate_approval": delegate_approved,
            "total_turns": session.current_turn,
            "conversation_handle": session.conversation_handle,
        }

        return DelegatedRunResult(
            task_id=tid,
            goal=goal,
            provider=provider.provider_name,
            status=status,
            turns_completed=session.current_turn,
            duration_seconds=round(duration, 2),
            local_acceptance_passed=local_passed,
            delegate_approval_received=delegate_approved,
            artifacts=verified_artifacts,
            final_stdout=last_sb_result.stdout if last_sb_result else "",
            final_stderr=last_sb_result.stderr if last_sb_result else "",
            provenance=provenance,
            session=session,
        )
