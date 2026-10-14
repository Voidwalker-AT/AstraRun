"""Central Execution Authority for AstraRun.

Enforces that ALL consequential actions (applications, processes, filesystem,
scripts, UI mutations, network, and skills) pass through one authoritative boundary:
ActionProposal -> ExecutionBroker -> ActionGate -> Dispatch -> Audit.

Models and agent loops NEVER call execution implementations directly.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from astrarun.core.paths import AstraPaths
from astrarun.security.action_gate import ActionGate, ConfirmationToken
from astrarun.security.models import (
    ActionGateVerdict,
    ActionRequest,
    CapabilityOperationKind,
    CapabilitySecurityMetadata,
    Operation,
    RiskLevel,
)

logger = logging.getLogger("astrarun.security.execution_broker")

_broker_context = threading.local()


def is_broker_dispatch_active() -> bool:
    """Returns True if the current thread is executing under authoritative ExecutionBroker dispatch."""
    return getattr(_broker_context, "active", False)


class BrokerDispatchScope:
    """Context manager setting active broker dispatch flag for runtime instrumentation."""
    def __enter__(self):
        _broker_context.active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _broker_context.active = False


class ActionCategory(str, Enum):
    """Distinguishes consequential mutations (ACT) from passive read-only queries (OBSERVE)."""
    ACT = "ACT"
    OBSERVE = "OBSERVE"


class ActionProposal(BaseModel):
    """Proposal for an action requiring evaluation before dispatch."""
    category: ActionCategory = ActionCategory.ACT
    capability_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    source: str = "user"  # "user", "planner", "delegate", "dynamic_tool"
    task_id: Optional[str] = None
    plan_revision: int = 1
    step_id: Optional[str] = None
    dry_run: bool = False
    reason: Optional[str] = None


class ExecutionBrokerResult(BaseModel):
    """Standardized result returned by ExecutionBroker."""
    model_config = {"arbitrary_types_allowed": True}

    success: bool
    verdict: str  # "ALLOW", "CONFIRM", "BLOCK"
    execution_state: str = "EXECUTED"  # "EXECUTED", "SIMULATED", "DENIED", "CONFIRMATION_REQUIRED", "FAILED"
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    confirmation_token: Optional[str] = None
    blocked: bool = False
    requires_confirmation: bool = False
    duration_ms: float = 0.0
    audit_id: Optional[str] = None
    raw_result: Optional[Any] = None


class ExecutionBroker:
    """The authoritative execution choke-point for all Astra operations."""

    _instance: Optional[ExecutionBroker] = None

    @classmethod
    def get_instance(cls) -> ExecutionBroker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(
        self,
        action_gate: Optional[ActionGate] = None,
        capability_registry: Any = None,
    ) -> None:
        self.action_gate = action_gate or ActionGate.get_instance()
        if capability_registry is None:
            try:
                from astrarun.capabilities.registry import CapabilityRegistry
                self.capability_registry = CapabilityRegistry()
            except Exception:
                self.capability_registry = None
        else:
            self.capability_registry = capability_registry
        if self.capability_registry and not getattr(self.action_gate, "capability_registry", None):
            self.action_gate.capability_registry = self.capability_registry
        self._audit_trail: List[Dict[str, Any]] = []

    def submit(
        self,
        proposal: ActionProposal,
        confirmation_token: Optional[str] = None,
        executor_override: Optional[Callable[..., Any]] = None,
    ) -> ExecutionBrokerResult:
        """Alias for execute to satisfy workflow, exploration, and compound callers."""
        return self.execute(
            proposal=proposal,
            confirmation_token=confirmation_token,
            executor_override=executor_override,
        )

    def execute(
        self,
        proposal: ActionProposal,
        confirmation_token: Optional[str] = None,
        executor_override: Optional[Callable[..., Any]] = None,
    ) -> ExecutionBrokerResult:
        """Evaluate proposal against ActionGate and dispatch if allowed."""
        t_start = time.perf_counter()
        audit_id = f"exec_{int(time.time() * 1000)}"

        from astrarun.core.telemetry import CausalTelemetry, CausalEventType, compute_hash
        telem = CausalTelemetry.get_instance()
        input_h = compute_hash(proposal.parameters)
        prop_ev = telem.emit(
            event_type=CausalEventType.ACTION_PROPOSED.value,
            component="ExecutionBroker",
            capability=proposal.capability_id,
            task_id=proposal.task_id,
            input_hash=input_h,
            data={"source": proposal.source, "category": proposal.category.value, "step_id": proposal.step_id, "dry_run": proposal.dry_run},
        )

        # 0. Capability Registration Check (Requirement 3: Deny unknown by default)
        cap = self.capability_registry.get(proposal.capability_id) if self.capability_registry else None
        if not cap and not executor_override:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            msg = f"SECURITY_DENY: Unknown or unregistered capability '{proposal.capability_id}'. Consequential execution denied."
            logger.warning("ExecutionBroker BLOCKED unregistered capability '%s'", proposal.capability_id)
            self._record_audit(audit_id, proposal, "BLOCK", msg, success=False, duration_ms=duration_ms)
            telem.emit(
                event_type=CausalEventType.ACTION_BLOCKED.value,
                component="ExecutionBroker",
                parent_event_id=prop_ev.event_id,
                capability=proposal.capability_id,
                task_id=proposal.task_id,
                authorization_verdict="BLOCK",
                data={"reason": msg},
            )
            return ExecutionBrokerResult(
                success=False,
                verdict="BLOCK",
                blocked=True,
                message=msg,
                duration_ms=duration_ms,
                audit_id=audit_id,
            )

        # 1. Authoritative Category Derivation (Requirement 2: Caller cannot declare ACT vs OBSERVE)
        if cap:
            sec_meta = cap.get_security_metadata()
        else:
            from astrarun.capabilities.manifest import get_authoritative_metadata
            meta = get_authoritative_metadata(proposal.capability_id)
            if meta is not None:
                sec_meta = meta
            else:
                sec_meta = CapabilitySecurityMetadata(
                    operation_kind=CapabilityOperationKind.UNKNOWN_CONSEQUENTIAL,
                    risk=RiskLevel.HIGH,
                    mutates_state=True,
                    requires_confirmation=True,
                )

        observational_kinds = (
            CapabilityOperationKind.OBSERVE_READ_ONLY,
            CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
            CapabilityOperationKind.FILE_READ,
            CapabilityOperationKind.NETWORK_INSPECT,
            CapabilityOperationKind.BROWSER_EXTRACT,
        )

        is_mutation = (
            sec_meta.mutates_state
            or (cap and not cap.read_only)
            or (sec_meta.operation_kind not in observational_kinds)
        )

        if is_mutation:
            if proposal.category == ActionCategory.OBSERVE:
                logger.warning(
                    "SECURITY_ALERT: Caller attempted to spoof proposal category as OBSERVE for mutating capability '%s'. Forcing to ACT.",
                    proposal.capability_id,
                )
            effective_category = ActionCategory.ACT
        else:
            effective_category = ActionCategory.OBSERVE

        # 2. Unknown Consequential Check (Strict Deny)
        if sec_meta.operation_kind == CapabilityOperationKind.UNKNOWN_CONSEQUENTIAL:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            msg = f"SECURITY_DENY: Capability '{proposal.capability_id}' has unclassified consequential operations. Execution denied."
            logger.warning("ExecutionBroker BLOCKED UNKNOWN_CONSEQUENTIAL capability '%s'", proposal.capability_id)
            self._record_audit(audit_id, proposal, "BLOCK", msg, success=False, duration_ms=duration_ms)
            telem.emit(
                event_type=CausalEventType.ACTION_BLOCKED.value,
                component="ExecutionBroker",
                parent_event_id=prop_ev.event_id,
                capability=proposal.capability_id,
                task_id=proposal.task_id,
                authorization_verdict="BLOCK",
                data={"reason": msg},
            )
            return ExecutionBrokerResult(
                success=False,
                verdict="BLOCK",
                blocked=True,
                message=msg,
                duration_ms=duration_ms,
                audit_id=audit_id,
            )

        # 3. Passive Observations
        if effective_category == ActionCategory.OBSERVE:
            logger.debug("Passive observation permitted for %s", proposal.capability_id)
            telem.emit(
                event_type=CausalEventType.ACTION_AUTHORIZED.value,
                component="ExecutionBroker",
                parent_event_id=prop_ev.event_id,
                capability=proposal.capability_id,
                task_id=proposal.task_id,
                authorization_verdict="ALLOW",
                data={"category": "OBSERVE"},
            )
            telem.emit(
                event_type=CausalEventType.ACTION_DISPATCHED.value,
                component="ExecutionBroker",
                parent_event_id=prop_ev.event_id,
                capability=proposal.capability_id,
                task_id=proposal.task_id,
                data={"parameters": proposal.parameters},
            )
            return self._dispatch_execution(proposal, audit_id, t_start, executor_override, verdict="ALLOW")

        # 4. Map proposal to ActionGate Request via authoritative metadata
        gate_request = self._map_to_gate_request(proposal, sec_meta)

        # 4. Security Evaluation
        evaluation = self.action_gate.evaluate_request(gate_request)

        # If blocked by policy
        if evaluation.verdict == ActionGateVerdict.DENY:
            logger.warning(
                "ExecutionBroker BLOCKED proposal '%s': %s (Risk: %s)",
                proposal.capability_id,
                evaluation.reason,
                evaluation.risk.value,
            )
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            self._record_audit(audit_id, proposal, "BLOCK", evaluation.reason, success=False, duration_ms=duration_ms)
            telem.emit(
                event_type=CausalEventType.ACTION_BLOCKED.value,
                component="ExecutionBroker",
                parent_event_id=prop_ev.event_id,
                capability=proposal.capability_id,
                task_id=proposal.task_id,
                authorization_verdict="BLOCK",
                data={"reason": evaluation.reason, "risk": evaluation.risk.value},
            )
            return ExecutionBrokerResult(
                success=False,
                verdict="BLOCK",
                blocked=True,
                message=f"Action blocked by security policy: {evaluation.reason}",
                duration_ms=duration_ms,
                audit_id=audit_id,
            )

        # 5. Dry-Run Handling: Zero side-effects guarantee
        if proposal.dry_run:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            msg = f"SIMULATED: Dry-run execution of '{proposal.capability_id}' with zero host side-effects."
            logger.info(msg)
            self._record_audit(audit_id, proposal, "SIMULATE", msg, success=True, duration_ms=duration_ms)
            telem.emit(
                event_type=CausalEventType.ACTION_AUTHORIZED.value,
                component="ExecutionBroker",
                parent_event_id=prop_ev.event_id,
                capability=proposal.capability_id,
                task_id=proposal.task_id,
                authorization_verdict="ALLOW",
                data={"simulated": True},
            )
            return ExecutionBrokerResult(
                success=True,
                verdict="ALLOW",
                execution_state="SIMULATED",
                message=msg,
                data={"simulated": True, "capability_id": proposal.capability_id, "parameters": proposal.parameters},
                duration_ms=duration_ms,
                audit_id=audit_id,
            )

        # If user confirmation is required
        if evaluation.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION:
            if confirmation_token:
                valid, msg = self.action_gate.revalidate_confirmation(
                    token_str=confirmation_token,
                    tool_name=proposal.capability_id,
                    arguments=proposal.parameters,
                    task_id=proposal.task_id,
                    plan_revision=proposal.plan_revision,
                )
                if not valid:
                    logger.warning("ExecutionBroker invalid/expired confirmation token for '%s': %s", proposal.capability_id, msg)
                    duration_ms = (time.perf_counter() - t_start) * 1000.0
                    telem.emit(
                        event_type=CausalEventType.ACTION_BLOCKED.value,
                        component="ExecutionBroker",
                        parent_event_id=prop_ev.event_id,
                        capability=proposal.capability_id,
                        task_id=proposal.task_id,
                        authorization_verdict="BLOCK",
                        data={"reason": f"Confirmation token failed: {msg}"},
                    )
                    return ExecutionBrokerResult(
                        success=False,
                        verdict="CONFIRM",
                        execution_state="CONFIRMATION_REQUIRED",
                        requires_confirmation=True,
                        message=f"Confirmation token failed: {msg}",
                        duration_ms=duration_ms,
                        audit_id=audit_id,
                    )
                logger.info("ExecutionBroker confirmation verified for '%s'", proposal.capability_id)
            else:
                token_str = evaluation.confirmation_token
                logger.info("ExecutionBroker requesting confirmation for '%s' (Token: %s)", proposal.capability_id, token_str)
                duration_ms = (time.perf_counter() - t_start) * 1000.0
                telem.emit(
                    event_type=CausalEventType.ACTION_BLOCKED.value,
                    component="ExecutionBroker",
                    parent_event_id=prop_ev.event_id,
                    capability=proposal.capability_id,
                    task_id=proposal.task_id,
                    authorization_verdict="CONFIRM",
                    data={"reason": evaluation.reason, "confirmation_token": token_str},
                )
                return ExecutionBrokerResult(
                    success=False,
                    verdict="CONFIRM",
                    execution_state="CONFIRMATION_REQUIRED",
                    requires_confirmation=True,
                    confirmation_token=token_str,
                    message=f"Confirmation required: {evaluation.reason}",
                    duration_ms=duration_ms,
                    audit_id=audit_id,
                )

        # 6. ALLOW / Confirmed -> Dispatch under active broker authority scope
        telem.emit(
            event_type=CausalEventType.ACTION_AUTHORIZED.value,
            component="ExecutionBroker",
            parent_event_id=prop_ev.event_id,
            capability=proposal.capability_id,
            task_id=proposal.task_id,
            authorization_verdict="ALLOW",
            data={"category": "ACT"},
        )
        telem.emit(
            event_type=CausalEventType.ACTION_DISPATCHED.value,
            component="ExecutionBroker",
            parent_event_id=prop_ev.event_id,
            capability=proposal.capability_id,
            task_id=proposal.task_id,
            data={"parameters": proposal.parameters},
        )
        return self._dispatch_execution(proposal, audit_id, t_start, executor_override, verdict="ALLOW")

    def _dispatch_execution(
        self,
        proposal: ActionProposal,
        audit_id: str,
        t_start: float,
        executor_override: Optional[Callable[..., Any]] = None,
        verdict: str = "ALLOW",
    ) -> ExecutionBrokerResult:
        """Dispatch action to executor under BrokerDispatchScope and capture result."""
        from astrarun.core.telemetry import CausalTelemetry, CausalEventType, compute_hash
        telem = CausalTelemetry.get_instance()
        try:
            with BrokerDispatchScope():
                if executor_override:
                    res = executor_override(**proposal.parameters)
                elif self.capability_registry:
                    res = self.capability_registry.execute(
                        proposal.capability_id,
                        proposal.parameters,
                        task_id=proposal.task_id,
                    )
                else:
                    raise RuntimeError(f"No execution handler registered for '{proposal.capability_id}'")

            duration_ms = (time.perf_counter() - t_start) * 1000.0

            # Normalize capability result
            success = getattr(res, "success", True) if res is not None else True
            msg = getattr(res, "message", "Executed successfully") if res is not None else "Executed successfully"
            data = getattr(res, "data", {}) if res is not None else {}
            if not isinstance(data, dict):
                data = {"raw_result": str(data)}

            self._record_audit(audit_id, proposal, verdict, msg, success=success, duration_ms=duration_ms)
            telem.emit(
                event_type=CausalEventType.ACTION_RESULT.value,
                component="ExecutionBroker",
                capability=proposal.capability_id,
                task_id=proposal.task_id,
                output_hash=compute_hash(data),
                data={"success": success, "message": msg, "duration_ms": duration_ms},
            )

            return ExecutionBrokerResult(
                success=success,
                verdict=verdict,
                execution_state="EXECUTED",
                message=msg,
                data=data,
                duration_ms=duration_ms,
                audit_id=audit_id,
                raw_result=res,
            )
        except Exception as err:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            logger.error("ExecutionBroker dispatch error for '%s': %s", proposal.capability_id, err)
            self._record_audit(audit_id, proposal, verdict, str(err), success=False, duration_ms=duration_ms)
            telem.emit(
                event_type=CausalEventType.ACTION_RESULT.value,
                component="ExecutionBroker",
                capability=proposal.capability_id,
                task_id=proposal.task_id,
                output_hash="",
                data={"success": False, "error": str(err), "duration_ms": duration_ms},
            )
            return ExecutionBrokerResult(
                success=False,
                verdict=verdict,
                execution_state="FAILED",
                message=f"Execution failed: {err}",
                duration_ms=duration_ms,
                audit_id=audit_id,
            )

    def _map_to_gate_request(self, proposal: ActionProposal, sec_meta: CapabilitySecurityMetadata) -> ActionRequest:
        """Map generic proposal to typed ActionRequest using authoritative capability metadata."""
        op_kind = sec_meta.operation_kind
        params = proposal.parameters

        if op_kind == CapabilityOperationKind.APPLICATION_LAUNCH:
            op = Operation.EXECUTE
            tgt = params.get("app_name", params.get("app_id", params.get("target", "")))
        elif op_kind == CapabilityOperationKind.APPLICATION_CLOSE:
            op = Operation.MODIFY
            tgt = params.get("app_name", params.get("app_id", params.get("target", "")))
        elif op_kind == CapabilityOperationKind.PROCESS_KILL:
            op = Operation.PRIVILEGED_MODIFY
            tgt = params.get("process_name", params.get("pid", params.get("target", "process")))
        elif op_kind == CapabilityOperationKind.FILE_DELETE:
            op = Operation.DELETE
            tgt = params.get("path", params.get("target", ""))
        elif op_kind == CapabilityOperationKind.FILE_CREATE:
            op = Operation.CREATE
            tgt = params.get("path", params.get("output_path", params.get("target", "")))
        elif op_kind == CapabilityOperationKind.FILE_MODIFY:
            op = Operation.MODIFY
            tgt = params.get("path", params.get("target", ""))
        elif op_kind == CapabilityOperationKind.DYNAMIC_CODE_EXEC:
            op = Operation.EXECUTE
            tgt = params.get("goal", params.get("script_code", params.get("code", "dynamic_tool")))
        elif op_kind == CapabilityOperationKind.SHELL_EXEC:
            op = Operation.EXECUTE
            tgt = params.get("command", "")
        elif op_kind in (CapabilityOperationKind.UI_INTERACTION, CapabilityOperationKind.BROWSER_INTERACT):
            op = Operation.MODIFY
            tgt = params.get("target", params.get("element_id", "ui"))
        elif op_kind == CapabilityOperationKind.BROWSER_NAVIGATE:
            op = Operation.EXECUTE
            tgt = params.get("url", "browser")
        elif op_kind == CapabilityOperationKind.NETWORK_MUTATE:
            op = Operation.MODIFY
            tgt = params.get("ssid", params.get("target", "network"))
        elif op_kind == CapabilityOperationKind.PRIVILEGED_SYSTEM:
            op = Operation.PRIVILEGED_MODIFY
            tgt = params.get("target", "system")
        elif op_kind in (CapabilityOperationKind.OBSERVE_READ_ONLY, CapabilityOperationKind.SYSTEM_DIAGNOSTIC, CapabilityOperationKind.FILE_READ, CapabilityOperationKind.NETWORK_INSPECT, CapabilityOperationKind.BROWSER_EXTRACT):
            op = Operation.READ
            tgt = proposal.capability_id
        else:
            op = Operation.PRIVILEGED_MODIFY
            tgt = proposal.capability_id

        return ActionRequest(
            operation=op,
            capability=proposal.capability_id,
            target=str(tgt),
            parameters=params,
            task_id=proposal.task_id or f"task_{int(time.time())}",
        )

    def _record_audit(
        self,
        audit_id: str,
        proposal: ActionProposal,
        verdict: str,
        message: str,
        success: bool,
        duration_ms: float = 0.0,
    ) -> None:
        """Record structured security audit log entry in memory and durable disk JSONL."""
        import json
        import re

        # Sensitive scrubbing pattern
        secret_pattern = re.compile(r"(key|token|password|secret|auth)[\"':=\s]+[\"']?([A-Za-z0-9_-]{8,})[\"']?", re.IGNORECASE)

        sanitized_params = {}
        for k, v in proposal.parameters.items():
            val_str = str(v)[:200]
            val_str = secret_pattern.sub(r"\1: [REDACTED]", val_str)
            sanitized_params[k] = val_str

        entry = {
            "audit_id": audit_id,
            "timestamp": time.time(),
            "capability_id": proposal.capability_id,
            "category": proposal.category.value,
            "source": proposal.source,
            "task_id": proposal.task_id,
            "parameters": sanitized_params,
            "verdict": verdict,
            "success": success,
            "message": secret_pattern.sub(r"\1: [REDACTED]", str(message)[:300]),
            "duration_ms": duration_ms,
        }
        self._audit_trail.append(entry)
        if len(self._audit_trail) > 1000:
            self._audit_trail = self._audit_trail[-1000:]

        # Durable audit persistence (survives restarts)
        try:
            audit_dir = AstraPaths.data_dir() / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            audit_file = audit_dir / "execution_broker.jsonl"
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as audit_err:
            logger.warning("Failed to append durable audit log: %s", audit_err)

    def get_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._audit_trail[-limit:]
