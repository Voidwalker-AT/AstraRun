"""Central Action Gate for AstraRun v0.6.

Determines whether a ProposedAction may become an executable registered tool invocation.
Evaluates:
- Routing source (deterministic vs neural vs cascade)
- Intent and semantic confidence
- Multi-question ambiguity and consequence risk
- Model agreement and Jensen-Shannon divergence
- Entity resolution status and candidate scores
- Tool risk classification and user permission overrides
- Action-specific hard policy invariants
- TOCTOU verification and confirmation token binding
"""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import psutil

from astrarun.core.logging import get_logger
from astrarun.core.models import ActionGateOutcome, ActionGateResult, ToolRisk
from astrarun.routing.entity_resolver import (
    PROTECTED_PORT_MAX,
    PROTECTED_PROCESSES,
    ProposedAction,
)
from astrarun.tools.registry import ToolRegistry

logger = get_logger("astrarun.policy.action_gate")

# Initial production allowlist for autonomous execution (Section 8 & 38)
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
    expires_at: float = field(default_factory=lambda: time.time() + 60.0)  # 60 second TTL

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


@dataclass
class ActionGateConfig:
    """Configurable permission overrides and thresholds."""
    confidence_threshold: float = 0.70
    js_threshold: float = 0.25
    permissions: dict[str, str] = field(default_factory=lambda: {
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
    })


class ActionGate:
    """
    Central safety arbiter in the AstraRun execution pipeline.
    
    Transforms (Semantic Decision + Entity Resolution) -> ActionGateResult
    Outcomes:
      - ALLOW: Low-risk, fully verified action on production allowlist.
      - CONFIRM: Verified action requiring explicit user confirmation.
      - CLARIFY: Ambiguous intent, multiple candidates, or unresolved target.
      - BLOCK: Hard security policy violation or prohibited tool.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        config: Optional[ActionGateConfig] = None,
    ) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        self.config = config or ActionGateConfig()
        self._active_tokens: dict[str, ConfirmationToken] = {}

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
        Evaluate a proposed action against multi-tier safety policies.
        No single confidence value grants execution authority.
        """
        t0 = time.perf_counter()
        req_query = proposed_action.raw_query
        intent = proposed_action.action_type

        # ---------------------------------------------------------------------
        # Tier 0: Hard Policy Checks (Unconditional BLOCK)
        # ---------------------------------------------------------------------
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
                reason="Semantic risk assessment classified action as BLOCKED",
                tool=None,
                arguments={},
                source=routing_source,
                policy_allowed=False,
                risk=ToolRisk.BLOCKED,
                latency_ms=lat,
            )

        # ---------------------------------------------------------------------
        # Tier 1: Ambiguity and Uncertainty Checks (CLARIFY)
        # ---------------------------------------------------------------------
        if proposed_action.status == "ambiguous":
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.CLARIFY,
                reason="Multiple candidate entities match the request; user disambiguation required",
                tool=None,
                arguments={},
                source=routing_source,
                candidates=proposed_action.candidate_matches,
                policy_allowed=True,
                risk=ToolRisk.LOW,
                latency_ms=lat,
            )

        if proposed_action.status == "unresolved" or not proposed_action.target:
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.CLARIFY,
                reason=f"Could not resolve a concrete workstation entity for intent '{intent}'",
                tool=None,
                arguments={},
                source=routing_source,
                policy_allowed=True,
                risk=ToolRisk.LOW,
                latency_ms=lat,
            )

        if ambiguity_verdict == "ambiguous":
            lat = (time.perf_counter() - t0) * 1000.0
            return ActionGateResult(
                status=ActionGateOutcome.CLARIFY,
                reason="Semantic decision layer flagged request as ambiguous",
                tool=None,
                arguments={},
                source=routing_source,
                policy_allowed=True,
                risk=ToolRisk.LOW,
                latency_ms=lat,
            )

        # For neural routing sources, enforce statistical consensus
        if routing_source.startswith("laya") or routing_source.startswith("ensemble"):
            if not model_agreement or jsd > self.config.js_threshold:
                lat = (time.perf_counter() - t0) * 1000.0
                return ActionGateResult(
                    status=ActionGateOutcome.CLARIFY,
                    reason=f"Decision models disagreed on intent (JSD={jsd:.4f} > {self.config.js_threshold})",
                    tool=None,
                    arguments={},
                    source=routing_source,
                    policy_allowed=True,
                    risk=ToolRisk.LOW,
                    latency_ms=lat,
                )
            if semantic_confidence < self.config.confidence_threshold:
                lat = (time.perf_counter() - t0) * 1000.0
                return ActionGateResult(
                    status=ActionGateOutcome.CLARIFY,
                    reason=f"Semantic confidence ({semantic_confidence:.2f}) below threshold ({self.config.confidence_threshold})",
                    tool=None,
                    arguments={},
                    source=routing_source,
                    policy_allowed=True,
                    risk=ToolRisk.LOW,
                    latency_ms=lat,
                )

        # ---------------------------------------------------------------------
        # Tier 2: Tool Selection and Policy Mapping
        # ---------------------------------------------------------------------
        tool_name = proposed_action.tool
        tool_args = dict(proposed_action.arguments)

        # Map generic intents to specific tool if not already mapped
        if not tool_name:
            if intent in ("open_project", "semantic_project"):
                pid = proposed_action.metadata.get("project_id") or proposed_action.target
                tool_name = "open_project_in_vscode"
                tool_args = {"project_id": pid}
            elif intent in ("open_app", "semantic_app"):
                tool_name = "open_app"
                tool_args = {"app": proposed_action.target, "path": proposed_action.target}
            elif intent in ("open_folder", "semantic_folder"):
                tool_name = "open_folder"
                tool_args = {"folder": proposed_action.target}
            elif intent in ("open_url", "semantic_browser"):
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
                confirmation_token=token_obj,
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

        tool_meta = self.tool_registry.get(tool_name)
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
        configured_perm = self.config.permissions.get(tool_name, "CONFIRM")

        # ---------------------------------------------------------------------
        # Tier 3: Confirmation vs. Direct Allowance
        # ---------------------------------------------------------------------
        # Actions requiring confirmation:
        # 1. Any HIGH risk tool (e.g. terminate_process)
        # 2. Any tool explicitly declaring requires_confirmation
        # 3. Any tool configured as CONFIRM
        # 4. Any power action (shutdown, restart)
        needs_confirm = (
            tool_meta.risk == ToolRisk.HIGH
            or tool_meta.requires_confirmation
            or proposed_action.requires_confirmation
            or configured_perm == "CONFIRM"
            or "kill" in intent
            or "terminate" in intent
            or "shutdown" in intent
            or "restart" in intent
        )

        lat = (time.perf_counter() - t0) * 1000.0

        if needs_confirm:
            # Generate cryptographic confirmation token bound to arguments
            token_str = secrets.token_hex(16)
            pid_val = tool_args.get("pid")
            create_time_val = tool_args.get("expected_create_time", 0.0)
            
            # If PID is known but create_time is not yet recorded, inspect it now for TOCTOU binding
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

        # ---------------------------------------------------------------------
        # Tier 4: Direct ALLOW
        # ---------------------------------------------------------------------
        # Tool must be in initial production allowlist
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

    def revalidate_confirmation(
        self,
        token_str: str | None = None,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Tuple[bool, str]:
        """
        Revalidate confirmation token before execution (TOCTOU protection).
        Verifies:
        1. Token exists and is not expired.
        2. Tool and arguments match the bound token.
        3. If targeting a process PID, verifies the process has not been killed or recycled.
        """
        tok = token_str or kwargs.get("token") or ""
        tl = tool_name or kwargs.get("tool") or ""
        args = arguments if arguments is not None else kwargs.get("arguments", {})

        token_obj = self._active_tokens.get(tok)
        if not token_obj:
            return False, "Invalid or missing confirmation token"

        if token_obj.is_expired:
            self._active_tokens.pop(tok, None)
            return False, "Confirmation token has expired (TTL 60s); please retry"

        if token_obj.tool != tl:
            return False, f"Confirmation token tool mismatch ('{token_obj.tool}' != '{tl}')"

        # Verify arguments match to prevent tampering
        if token_obj.arguments:
            for k, expected_v in token_obj.arguments.items():
                if k in args and args[k] != expected_v:
                    return False, f"Confirmation token arguments mismatch on '{k}' (tampering detected)"

        # TOCTOU Process Revalidation
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

        # Consume token on successful validation
        self._active_tokens.pop(tok, None)
        return True, "Revalidation successful"
