"""Security data models and type definitions for AstraRun 1.0."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Operation(str, Enum):
    """Operation classes evaluated by the operation-aware ActionGate."""
    READ = "READ"
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    EXECUTE = "EXECUTE"
    PRIVILEGED_MODIFY = "PRIVILEGED_MODIFY"


class RiskLevel(str, Enum):
    """Risk tiers for operations and capabilities."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionGateVerdict(str, Enum):
    """Authoritative verdicts emitted by ActionGate."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


@dataclass(frozen=True)
class ActionRequest:
    """Structured authorization request submitted to ActionGate."""
    operation: Operation
    capability: str
    target: str
    parameters: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    authorization_scope: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionGateEvaluation:
    """Authoritative structured evaluation outcome emitted by ActionGate."""
    verdict: ActionGateVerdict
    reason: str
    risk: RiskLevel
    matched_policy: str = ""
    reversibility: bool = True
    action_summary: str = ""
    confirmation_token: Optional[str] = None
    audit_event: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def is_allowed(self) -> bool:
        return self.verdict == ActionGateVerdict.ALLOW

    @property
    def risk_level(self) -> RiskLevel:
        return self.risk

    @property
    def is_denied(self) -> bool:
        return self.verdict == ActionGateVerdict.DENY

    @property
    def requires_confirmation(self) -> bool:
        return self.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION
