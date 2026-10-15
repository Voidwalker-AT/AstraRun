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


class CapabilityOperationKind(str, Enum):
    """Authoritative semantic operation classifications."""
    OBSERVE_READ_ONLY = "OBSERVE_READ_ONLY"
    SYSTEM_DIAGNOSTIC = "SYSTEM_DIAGNOSTIC"
    APPLICATION_LAUNCH = "APPLICATION_LAUNCH"
    APPLICATION_CLOSE = "APPLICATION_CLOSE"
    PROCESS_KILL = "PROCESS_KILL"
    FILE_READ = "FILE_READ"
    FILE_CREATE = "FILE_CREATE"
    FILE_MODIFY = "FILE_MODIFY"
    FILE_DELETE = "FILE_DELETE"
    DYNAMIC_CODE_EXEC = "DYNAMIC_CODE_EXEC"
    SHELL_EXEC = "SHELL_EXEC"
    UI_INTERACTION = "UI_INTERACTION"
    NETWORK_INSPECT = "NETWORK_INSPECT"
    NETWORK_MUTATE = "NETWORK_MUTATE"
    BROWSER_NAVIGATE = "BROWSER_NAVIGATE"
    BROWSER_INTERACT = "BROWSER_INTERACT"
    BROWSER_EXTRACT = "BROWSER_EXTRACT"
    PRIVILEGED_SYSTEM = "PRIVILEGED_SYSTEM"
    UNKNOWN_CONSEQUENTIAL = "UNKNOWN_CONSEQUENTIAL"

class LocalAccessScope(str, Enum):
    """Authoritative boundaries for workstation and local filesystem access."""
    ACTIVE_FOREGROUND_RESOURCE = "ACTIVE_FOREGROUND_RESOURCE"
    AUTHORIZED_WORKSPACE = "AUTHORIZED_WORKSPACE"
    EXPLICITLY_AUTHORIZED_USER_DIRECTORIES = "EXPLICITLY_AUTHORIZED_USER_DIRECTORIES"
    SENSITIVE_PERSONAL_STORES = "SENSITIVE_PERSONAL_STORES"
    PROHIBITED_CREDENTIAL_SYSTEM_LOCATIONS = "PROHIBITED_CREDENTIAL_SYSTEM_LOCATIONS"

    @property
    def is_restricted(self) -> bool:
        return self in (
            LocalAccessScope.SENSITIVE_PERSONAL_STORES,
            LocalAccessScope.PROHIBITED_CREDENTIAL_SYSTEM_LOCATIONS,
        )

    @property
    def is_prohibited(self) -> bool:
        return self == LocalAccessScope.PROHIBITED_CREDENTIAL_SYSTEM_LOCATIONS


class EgressDisclosurePolicy(str, Enum):
    """Authoritative rules governing external transmission and model disclosure."""
    PUBLIC_SAFE = "PUBLIC_SAFE"
    LOCAL_ONLY = "LOCAL_ONLY"  # Default for all local / private content: never disclose externally
    SCRUBBED_SUMMARY_ONLY = "SCRUBBED_SUMMARY_ONLY"
    EXPLICIT_CONFIRMATION_REQUIRED = "EXPLICIT_CONFIRMATION_REQUIRED"

    @property
    def allows_external_transmission(self) -> bool:
        return self in (
            EgressDisclosurePolicy.PUBLIC_SAFE,
            EgressDisclosurePolicy.SCRUBBED_SUMMARY_ONLY,
        )

    @property
    def requires_confirmation(self) -> bool:
        return self == EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED


@dataclass(frozen=True)
class CapabilitySecurityMetadata:
    """Authoritative capability security specification defining immutable gating properties."""
    operation_kind: CapabilityOperationKind
    risk: RiskLevel = RiskLevel.LOW
    mutates_state: bool = False
    requires_confirmation: bool = False
    resource_scope: str = "local"
    local_access_scope: LocalAccessScope = LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE
    egress_disclosure_policy: EgressDisclosurePolicy = EgressDisclosurePolicy.LOCAL_ONLY
