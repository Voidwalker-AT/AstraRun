"""Central ActionGate Security Kernel for AstraRun 1.0."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import psutil

from astrarun.core.logging import get_logger
from astrarun.core.models import ActionGateOutcome, ActionGateResult, ToolRisk
from astrarun.routing.entity_resolver import ProposedAction
from astrarun.security.models import (
    ActionGateEvaluation,
    ActionGateVerdict,
    ActionRequest,
    Operation,
    RiskLevel,
)
from astrarun.security.policies import ASTCodePolicy, CommandPolicy, PathPolicy
from astrarun.tools.registry import ToolRegistry

logger = get_logger("astrarun.security.action_gate")

INITIAL_PRODUCTION_ALLOWLIST = {
    "open_project",
    "open_project_folder",
    "open_project_in_vscode",
    "open_app",
    "open_folder",
    "open_url",
    "inspect_port",
    "inspect_process",
    "refresh_apps",
}


@dataclass
class ConfirmationToken:
    """Cryptographically bound confirmation record preventing TOCTOU replay or race conditions."""
    token: str
    tool: str
    arguments: dict[str, Any]
    entity_id: str
    pid: Optional[int] = None
    expected_create_time: float = 0.0
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 60.0)  # 60s TTL
    task_id: Optional[str] = None
    plan_revision: int = 1

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


@dataclass
class ActionGateConfig:
    """Configurable permission overrides and safety thresholds."""
    confidence_threshold: float = 0.70
    js_threshold: float = 0.25
    permissions: dict[str, str] = field(default_factory=lambda: {
        "file_system": "AUTO",
        "execution_runtime": "AUTO",
        "open_project": "AUTO",
        "open_project_folder": "AUTO",
        "open_project_in_vscode": "AUTO",
        "open_app": "AUTO",
        "open_folder": "AUTO",
        "open_url": "AUTO",
        "inspect_port": "AUTO",
        "inspect_process": "AUTO",
        "refresh_apps": "AUTO",
        "terminate_process": "CONFIRM",
        "system_shutdown": "CONFIRM",
        "system_restart": "CONFIRM",
        "system_restart_pc": "BLOCK",
        "execute_dynamic_tool": "AUTO",
        "consult_delegate": "AUTO",
    })


class ActionGate:
    """
    Central safety and authorization kernel for AstraRun 1.0.
    Enforces deterministic operation-aware policies across filesystem mutations,
    shell commands, and AST code execution.
    Small language models possess ZERO intrinsic execution authority;
    every action must obtain an ActionGate verdict before dispatch.
    """

    _instance: Optional[ActionGate] = None

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        config: Optional[ActionGateConfig] = None,
        capability_registry: Any = None,
        path_policy: Optional[PathPolicy] = None,
        command_policy: Optional[CommandPolicy] = None,
        ast_policy: Optional[ASTCodePolicy] = None,
    ) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        self.capability_registry = capability_registry
        self.config = config or ActionGateConfig()
        self.path_policy = path_policy or PathPolicy()
        self.command_policy = command_policy or CommandPolicy()
        self.ast_policy = ast_policy or ASTCodePolicy()
        self._active_tokens: dict[str, ConfirmationToken] = {}

    @classmethod
    def get_instance(cls) -> ActionGate:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # =========================================================================
    # Operation-Aware 1.0 Evaluation Pipeline
    # =========================================================================

    def evaluate_request(self, request: ActionRequest) -> ActionGateEvaluation:
        """
        Evaluate a structured, operation-aware ActionRequest against all security policies.
        Returns: ActionGateEvaluation (ALLOW, DENY, or REQUIRE_CONFIRMATION).
        """
        t0 = time.perf_counter()
        action_id = f"act_{secrets.token_hex(6)}"

        # 1. Path Policy Evaluation
        path_verdict, path_reason, path_risk = self.path_policy.evaluate(request)
        if path_verdict == ActionGateVerdict.DENY:
            lat = (time.perf_counter() - t0) * 1000.0
            audit = self._build_audit_event(request, action_id, ActionGateVerdict.DENY, path_risk, path_reason, "PathPolicy")
            return ActionGateEvaluation(
                verdict=ActionGateVerdict.DENY,
                reason=path_reason,
                risk=path_risk,
                matched_policy="PathPolicy",
                reversibility=False,
                action_summary=f"DENIED {request.operation.value} on {request.target}",
                audit_event=audit,
                latency_ms=lat,
            )

        # 2. Command Policy Evaluation (for shell command EXECUTE operations)
        if request.operation == Operation.EXECUTE and ("command" in request.parameters or request.capability in ("run_project_command", "shell_exec")):
            cmd_str = request.parameters.get("command") or request.target or ""
            cmd_verdict, cmd_reason, cmd_risk = self.command_policy.evaluate_command_string(cmd_str)
            if cmd_verdict == ActionGateVerdict.DENY:
                lat = (time.perf_counter() - t0) * 1000.0
                audit = self._build_audit_event(request, action_id, ActionGateVerdict.DENY, cmd_risk, cmd_reason, "CommandPolicy")
                return ActionGateEvaluation(
                    verdict=ActionGateVerdict.DENY,
                    reason=cmd_reason,
                    risk=cmd_risk,
                    matched_policy="CommandPolicy",
                    reversibility=False,
                    action_summary=f"DENIED command: {cmd_str}",
                    audit_event=audit,
                    latency_ms=lat,
                )
            elif cmd_verdict == ActionGateVerdict.REQUIRE_CONFIRMATION:
                token_str = secrets.token_hex(16)
                token_obj = ConfirmationToken(
                    token=token_str,
                    tool=request.capability,
                    arguments=request.parameters,
                    entity_id=request.target,
                )
                self._active_tokens[token_str] = token_obj
                lat = (time.perf_counter() - t0) * 1000.0
                audit = self._build_audit_event(request, action_id, ActionGateVerdict.REQUIRE_CONFIRMATION, cmd_risk, cmd_reason, "CommandPolicy")
                return ActionGateEvaluation(
                    verdict=ActionGateVerdict.REQUIRE_CONFIRMATION,
                    reason=cmd_reason,
                    risk=cmd_risk,
                    matched_policy="CommandPolicy",
                    reversibility=False,
                    action_summary=f"Execute command: {cmd_str}",
                    confirmation_token=token_str,
                    audit_event=audit,
                    latency_ms=lat,
                )

            # 3. AST Inspection for Python code execution
            script_code = request.parameters.get("script_code") or request.parameters.get("code") or ""
            if script_code:
                ast_verdict, ast_reason, ast_risk = self.ast_policy.evaluate_code(script_code)
                if ast_verdict == ActionGateVerdict.DENY:
                    lat = (time.perf_counter() - t0) * 1000.0
                    audit = self._build_audit_event(request, action_id, ActionGateVerdict.DENY, ast_risk, ast_reason, "ASTCodePolicy")
                    return ActionGateEvaluation(
                        verdict=ActionGateVerdict.DENY,
                        reason=ast_reason,
                        risk=ast_risk,
                        matched_policy="ASTCodePolicy",
                        reversibility=False,
                        action_summary="DENIED dangerous Python script AST",
                        audit_event=audit,
                        latency_ms=lat,
                    )
                elif ast_verdict == ActionGateVerdict.REQUIRE_CONFIRMATION:
                    token_str = secrets.token_hex(16)
                    token_obj = ConfirmationToken(
                        token=token_str,
                        tool=request.capability,
                        arguments=request.parameters,
                        entity_id=request.target,
                    )
                    self._active_tokens[token_str] = token_obj
                    lat = (time.perf_counter() - t0) * 1000.0
                    audit = self._build_audit_event(request, action_id, ActionGateVerdict.REQUIRE_CONFIRMATION, ast_risk, ast_reason, "ASTCodePolicy")
                    return ActionGateEvaluation(
                        verdict=ActionGateVerdict.REQUIRE_CONFIRMATION,
                        reason=ast_reason,
                        risk=ast_risk,
                        matched_policy="ASTCodePolicy",
                        reversibility=True,
                        action_summary="Execute dynamic Python script with dynamic features",
                        confirmation_token=token_str,
                        audit_event=audit,
                        latency_ms=lat,
                    )

        # 4. Handle Path Policy Confirmation (e.g. DELETE, out-of-scope mutation)
        if path_verdict == ActionGateVerdict.REQUIRE_CONFIRMATION:
            token_str = secrets.token_hex(16)
            token_obj = ConfirmationToken(
                token=token_str,
                tool=request.capability,
                arguments=request.parameters,
                entity_id=request.target,
            )
            self._active_tokens[token_str] = token_obj
            lat = (time.perf_counter() - t0) * 1000.0
            reversibility = (request.operation != Operation.DELETE)
            audit = self._build_audit_event(request, action_id, ActionGateVerdict.REQUIRE_CONFIRMATION, path_risk, path_reason, "PathPolicy")
            return ActionGateEvaluation(
                verdict=ActionGateVerdict.REQUIRE_CONFIRMATION,
                reason=path_reason,
                risk=path_risk,
                matched_policy="PathPolicy",
                reversibility=reversibility,
                action_summary=f"{request.operation.value} on {request.target}",
                confirmation_token=token_str,
                audit_event=audit,
                latency_ms=lat,
            )

        # 5. Check Operation Privileged Boundaries
        if request.operation == Operation.PRIVILEGED_MODIFY:
            token_str = secrets.token_hex(16)
            token_obj = ConfirmationToken(
                token=token_str,
                tool=request.capability,
                arguments=request.parameters,
                entity_id=request.target,
            )
            self._active_tokens[token_str] = token_obj
            lat = (time.perf_counter() - t0) * 1000.0
            audit = self._build_audit_event(request, action_id, ActionGateVerdict.REQUIRE_CONFIRMATION, RiskLevel.CRITICAL, "Privileged modification", "PrivilegedOperationPolicy")
            return ActionGateEvaluation(
                verdict=ActionGateVerdict.REQUIRE_CONFIRMATION,
                reason="Privileged modification requires explicit user authorization",
                risk=RiskLevel.CRITICAL,
                matched_policy="PrivilegedOperationPolicy",
                reversibility=False,
                action_summary=f"Privileged modify on {request.target}",
                confirmation_token=token_str,
                audit_event=audit,
                latency_ms=lat,
            )

        # 6. Consequential Mutation Policy Check (Requirement 9)
        if request.operation in (Operation.MODIFY, Operation.CREATE, Operation.DELETE, Operation.EXECUTE, Operation.PRIVILEGED_MODIFY):
            from astrarun.capabilities.models import CapabilityPermission
            from astrarun.core.models import ToolRisk

            cap_registered = False
            is_auto = False
            if self.capability_registry and self.capability_registry.has_capability(request.capability):
                cap = self.capability_registry.get(request.capability)
                cap_registered = True
                is_auto = (cap.permission == CapabilityPermission.AUTO and cap.risk in (ToolRisk.LOW, ToolRisk.MEDIUM))
            elif request.capability in self.config.permissions:
                perm = self.config.permissions.get(request.capability, "BLOCK")
                cap_registered = True
                is_auto = (perm == "AUTO")

            if not cap_registered:
                lat = (time.perf_counter() - t0) * 1000.0
                reason = f"Unknown consequential operation on capability '{request.capability}' denied by default security policy."
                audit = self._build_audit_event(request, action_id, ActionGateVerdict.DENY, RiskLevel.HIGH, reason, "DefaultDenyPolicy")
                return ActionGateEvaluation(
                    verdict=ActionGateVerdict.DENY,
                    reason=reason,
                    risk=RiskLevel.HIGH,
                    matched_policy="DefaultDenyPolicy",
                    reversibility=False,
                    action_summary=f"DENIED unknown mutation {request.operation.value} on {request.target}",
                    audit_event=audit,
                    latency_ms=lat,
                )

            if not is_auto:
                token_str = secrets.token_hex(16)
                token_obj = ConfirmationToken(
                    token=token_str,
                    tool=request.capability,
                    arguments=request.parameters,
                    entity_id=request.target,
                )
                self._active_tokens[token_str] = token_obj
                lat = (time.perf_counter() - t0) * 1000.0
                audit = self._build_audit_event(request, action_id, ActionGateVerdict.REQUIRE_CONFIRMATION, RiskLevel.MEDIUM, "Consequential mutation requires user confirmation", "MutationConfirmationPolicy")
                return ActionGateEvaluation(
                    verdict=ActionGateVerdict.REQUIRE_CONFIRMATION,
                    reason=f"Consequential action '{request.capability}' requires explicit confirmation.",
                    risk=RiskLevel.MEDIUM,
                    matched_policy="MutationConfirmationPolicy",
                    reversibility=True,
                    action_summary=f"Require confirmation for {request.operation.value} {request.capability}",
                    confirmation_token=token_str,
                    audit_event=audit,
                    latency_ms=lat,
                )

        # 7. Cleared as ALLOW (known safe or read-only operations)
        lat = (time.perf_counter() - t0) * 1000.0
        audit = self._build_audit_event(request, action_id, ActionGateVerdict.ALLOW, RiskLevel.LOW, "Cleared by ActionGate policies", "DefaultAllow")
        return ActionGateEvaluation(
            verdict=ActionGateVerdict.ALLOW,
            reason="Action verified and authorized by ActionGate security kernel",
            risk=RiskLevel.LOW,
            matched_policy="DefaultAllow",
            reversibility=True,
            action_summary=f"{request.operation.value} {request.capability} on {request.target}",
            audit_event=audit,
            latency_ms=lat,
        )

    def _build_audit_event(
        self,
        request: ActionRequest,
        action_id: str,
        verdict: ActionGateVerdict,
        risk: RiskLevel,
        reason: str,
        policy: str,
    ) -> dict[str, Any]:
        """Construct structured, secret-scrubbed audit event."""
        return {
            "task_id": request.task_id,
            "action_id": action_id,
            "operation": request.operation.value,
            "capability": request.capability,
            "target": request.target,
            "policy_verdict": verdict.value,
            "risk": risk.value,
            "reason": reason,
            "matched_policy": policy,
            "timestamp": time.time(),
        }

    # =========================================================================
    # Backward-Compatible v0.6–v0.11 evaluate() Interface
    # =========================================================================

    def evaluate(
        self,
        proposed_action: ProposedAction,
        routing_source: str = "deterministic",
        semantic_confidence: float = 1.0,
        ambiguity_verdict: str = "safe_to_resolve",
        risk_verdict: str = "LOW",
        model_agreement: bool = True,
        jsd: float = 0.0,
        context: Optional[dict[str, Any]] = None,
    ) -> ActionGateResult:
        """
        Legacy ActionGate adapter for AstraRun v0.6–v0.11 compatibility.
        """
        t0 = time.perf_counter()
        req_query = proposed_action.raw_query
        intent = proposed_action.action_type

        # Hard blocked
        if not proposed_action.policy_allowed or proposed_action.status == "blocked":
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.BLOCK,
                reason=proposed_action.block_reason or "Prohibited by hard security policy",
                tool=None,
                arguments={},
                source=routing_source,
                policy_allowed=False,
                risk=ToolRisk.BLOCKED,
                latency_ms=lat,
            )

        if risk_verdict == "BLOCKED":
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.BLOCK,
                reason="Prohibited by risk assessment policy",
                tool=None,
                arguments={},
                source=routing_source,
                policy_allowed=False,
                risk=ToolRisk.BLOCKED,
                latency_ms=lat,
            )

        # Ambiguous / Low Confidence
        if proposed_action.status == "ambiguous" or ambiguity_verdict == "ambiguous":
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.CLARIFY,
                reason=f"Ambiguous query '{req_query}'; multiple candidates found",
                tool=None,
                arguments={},
                source=routing_source,
                candidates=proposed_action.candidate_matches,
                latency_ms=lat,
            )

        if semantic_confidence < self.config.confidence_threshold and routing_source != "deterministic":
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.CLARIFY,
                reason=f"Semantic confidence {semantic_confidence:.2f} below safety threshold {self.config.confidence_threshold}",
                tool=None,
                arguments={},
                source=routing_source,
                candidates=proposed_action.candidate_matches,
                latency_ms=lat,
            )

        if not model_agreement or jsd > self.config.js_threshold:
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.CLARIFY,
                reason=f"Model disagreement detected (JSD={jsd:.2f} > {self.config.js_threshold})",
                tool=None,
                arguments={},
                source=routing_source,
                candidates=proposed_action.candidate_matches,
                latency_ms=lat,
            )

        # Map to registered tool
        tool_name = proposed_action.tool
        tool_args = dict(proposed_action.arguments)

        if not tool_name:
            if intent in ("open_app", "open_application"):
                tool_name = "open_app"
                tool_args = {"app_name": proposed_action.target}
            elif intent in ("open_folder",):
                tool_name = "open_folder"
                tool_args = {"folder_path": proposed_action.target}
            elif intent in ("open_project",):
                tool_name = "open_project_folder"
                tool_args = {"project_id": proposed_action.target}
            elif intent in ("open_url",):
                tool_name = "open_url"
                tool_args = {"url": proposed_action.target}
            elif intent in ("inspect_port",):
                port_val = proposed_action.metadata.get("port")
                tool_name = "inspect_port"
                tool_args = {"port": port_val}
            elif intent in ("inspect_process",):
                pid_val = proposed_action.arguments.get("pid")
                tool_name = "inspect_process"
                tool_args = {"pid": pid_val}
            elif intent in ("process_action", "semantic_process"):
                tool_name = "terminate_process"
                tool_args = dict(proposed_action.arguments)

        if not tool_name and proposed_action.target in ("system:shutdown", "system:restart"):
            token_str = secrets.token_hex(16)
            token_obj = ConfirmationToken(
                token=token_str,
                tool="system_action",
                arguments={},
                entity_id=proposed_action.target,
            )
            self._active_tokens[token_str] = token_obj
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.CONFIRM,
                reason=f"System operation '{proposed_action.target}' requires explicit user confirmation",
                tool=None,
                arguments={},
                source=routing_source,
                confirmation_token=token_str,
                requires_confirmation=True,
                policy_allowed=True,
                risk=ToolRisk.HIGH,
                latency_ms=lat,
            )

        if not tool_name:
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.CLARIFY,
                reason=f"No registered tool mapped for intent '{intent}'",
                tool=None,
                arguments={},
                source=routing_source,
                latency_ms=lat,
            )

        tool_meta = self.tool_registry.get(tool_name) if hasattr(self.tool_registry, "get") else None
        if not tool_meta and self.capability_registry and hasattr(self.capability_registry, "get"):
            tool_meta = self.capability_registry.get(tool_name)

        if not tool_meta:
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.BLOCK,
                reason=f"Target tool '{tool_name}' is not registered",
                tool=tool_name,
                arguments=tool_args,
                source=routing_source,
                policy_allowed=False,
                latency_ms=lat,
            )

        # Check configured permission
        configured_perm = self.config.permissions.get(tool_name)
        if configured_perm is None:
            if hasattr(tool_meta, "permission"):
                configured_perm = "AUTO" if getattr(tool_meta.permission, "value", str(tool_meta.permission)).upper() == "AUTO" else "CONFIRM"
            elif getattr(tool_meta, "risk", ToolRisk.LOW) == ToolRisk.LOW:
                configured_perm = "AUTO"
            else:
                configured_perm = "CONFIRM"

        tool_risk = getattr(tool_meta, "risk", ToolRisk.LOW)
        tool_req_confirm = getattr(tool_meta, "requires_confirmation", False)
        needs_confirm = (
            tool_risk == ToolRisk.HIGH
            or tool_req_confirm
            or proposed_action.requires_confirmation
            or configured_perm == "CONFIRM"
            or "kill" in intent
            or "terminate" in intent
            or "shutdown" in intent
            or "restart" in intent
        )

        lat = (time.perf_counter() - t0) * 1000.0

        if needs_confirm:
            token_str = secrets.token_hex(16)
            pid_val = tool_args.get("pid")
            create_time_val = tool_args.get("expected_create_time", 0.0)

            if pid_val and create_time_val == 0.0 and psutil.pid_exists(pid_val):
                try:
                    p = psutil.Process(pid_val)
                    create_time_val = p.create_time()
                    tool_args["expected_create_time"] = create_time_val
                    tool_args["expected_name"] = p.name()
                except Exception:
                    pass

            token_obj = ConfirmationToken(
                token=token_str,
                tool=tool_name,
                arguments=tool_args,
                entity_id=proposed_action.entity_id or str(proposed_action.target),
                pid=pid_val,
                expected_create_time=create_time_val,
            )
            self._active_tokens[token_str] = token_obj

            return ActionGateResult(
                status=ActionGateOutcome.CONFIRM,
                reason=f"Action '{tool_name}' is high-risk or requires user confirmation",
                tool=tool_name,
                arguments=tool_args,
                source=routing_source,
                confirmation_token=token_str,
                requires_confirmation=True,
                policy_allowed=True,
                risk=tool_meta.risk,
                latency_ms=lat,
                metadata={"entity_id": token_obj.entity_id, "pid": pid_val},
            )

        if tool_name not in INITIAL_PRODUCTION_ALLOWLIST and configured_perm != "AUTO":
            return ActionGateResult(
                status=ActionGateOutcome.CONFIRM,
                reason=f"Tool '{tool_name}' is not in production auto-allowlist",
                tool=tool_name,
                arguments=tool_args,
                source=routing_source,
                requires_confirmation=True,
                policy_allowed=True,
                risk=tool_meta.risk,
                latency_ms=lat,
            )

        return ActionGateResult(
            status=ActionGateOutcome.ALLOW,
            reason=f"Action '{tool_name}' verified and cleared by ActionGate",
            tool=tool_name,
            arguments=tool_args,
            source=routing_source,
            requires_confirmation=False,
            policy_allowed=True,
            risk=tool_meta.risk,
            latency_ms=lat,
            metadata={"entity_id": proposed_action.entity_id or str(proposed_action.target)},
        )

    # =========================================================================
    # TOCTOU Token Verification
    # =========================================================================

    def revalidate_confirmation(
        self,
        token_str: str | None = None,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
        task_id: str | None = None,
        plan_revision: int | None = None,
        **kwargs: Any,
    ) -> Tuple[bool, str]:
        """
        Revalidate confirmation token before execution (TOCTOU protection).
        """
        tok = token_str or kwargs.get("token") or ""
        tl = tool_name or kwargs.get("tool") or ""
        args = arguments if arguments is not None else kwargs.get("arguments", {})
        tid = task_id if task_id is not None else kwargs.get("task_id")
        prev = plan_revision if plan_revision is not None else kwargs.get("plan_revision")

        token_obj = self._active_tokens.get(tok)
        if not token_obj:
            return False, "Invalid or missing confirmation token"

        if token_obj.is_expired:
            self._active_tokens.pop(tok, None)
            return False, "Confirmation token has expired (TTL 60s); please retry"

        if token_obj.tool != tl:
            return False, f"Confirmation token tool mismatch ('{token_obj.tool}' != '{tl}')"

        if token_obj.task_id and tid and token_obj.task_id != tid:
            return False, f"Confirmation token task_id mismatch ('{token_obj.task_id}' != '{tid}')"

        if token_obj.plan_revision is not None and prev is not None and token_obj.plan_revision != prev:
            return False, f"Confirmation token plan_revision mismatch ({token_obj.plan_revision} != {prev})"

        if token_obj.arguments:
            for k, expected_v in token_obj.arguments.items():
                if k in args and args[k] != expected_v:
                    return False, f"Confirmation token arguments mismatch on '{k}' (tampering detected)"

        if tl == "terminate_process" and token_obj.pid:
            pid = token_obj.pid
            if not psutil.pid_exists(pid):
                self._active_tokens.pop(tok, None)
                return False, f"TOCTOU Check Failed: Process PID {pid} has already terminated"

            try:
                proc = psutil.Process(pid)
                if token_obj.expected_create_time > 0.0:
                    current_ctime = proc.create_time()
                    if abs(current_ctime - token_obj.expected_create_time) > 1.0:
                        self._active_tokens.pop(tok, None)
                        return False, f"TOCTOU Check Failed: PID {pid} was recycled by the OS"

                exp_name = token_obj.arguments.get("expected_name", "").lower()
                if exp_name and exp_name not in (proc.name().lower(), proc.name().lower().replace(".exe", "")):
                    self._active_tokens.pop(tok, None)
                    return False, f"TOCTOU Check Failed: Process name changed for PID {pid}"
            except Exception as err:
                self._active_tokens.pop(tok, None)
                return False, f"TOCTOU Check Failed: Error querying PID {pid}: {err}"

        self._active_tokens.pop(tok, None)
        return True, "Revalidation successful"
