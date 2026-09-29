"""Machine-readable capability schemas for AstraRun v0.11 agent runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from astrarun.capabilities.models import CapabilityCategory, CapabilityErrorCode, CapabilityResult
from astrarun.core.models import ToolRisk


class InteractionTier(str, Enum):
    """Execution tier hierarchy for Windows interactions."""
    TIER_A_NATIVE = "TIER_A_NATIVE"             # Native Win32 C APIs, WLAN API, PowrProf
    TIER_B_STRUCTURED_CLI = "TIER_B_STRUCTURED_CLI" # Structured CLI adapters (powercfg, ipconfig)
    TIER_C_UI_AUTOMATION = "TIER_C_UI_AUTOMATION"   # Windows UI Automation COM interfaces
    TIER_D_INPUT_EMULATION = "TIER_D_INPUT_EMULATION" # SendInput & accelerators
    TIER_E_VISUAL_FALLBACK = "TIER_E_VISUAL_FALLBACK" # Visual computer use (shadow / vision)


class CapabilityFamily(str, Enum):
    """High-level capability family classification."""
    SYSTEM_DIAGNOSTICS = "SYSTEM_DIAGNOSTICS"
    NETWORK_MANAGEMENT = "NETWORK_MANAGEMENT"
    WINDOW_CONTROL = "WINDOW_CONTROL"
    APPLICATION_LIFECYCLE = "APPLICATION_LIFECYCLE"
    UI_INTERACTION = "UI_INTERACTION"
    FILE_MANAGEMENT = "FILE_MANAGEMENT"
    DEVELOPER_TOOLS = "DEVELOPER_TOOLS"
    WORKFLOW_AUTOMATION = "WORKFLOW_AUTOMATION"


class SideEffect(str, Enum):
    """Declared side-effects of executing a capability."""
    READ_ONLY = "READ_ONLY"
    CREATES_FILE = "CREATES_FILE"
    MODIFIES_FILE = "MODIFIES_FILE"
    DELETES_FILE = "DELETES_FILE"
    MODIFIES_WINDOW = "MODIFIES_WINDOW"
    SPAWNS_PROCESS = "SPAWNS_PROCESS"
    TERMINATES_PROCESS = "TERMINATES_PROCESS"
    NETWORK_STATE = "NETWORK_STATE"
    SYSTEM_STATE = "SYSTEM_STATE"


class PrivilegeLevel(str, Enum):
    """Required privilege to execute capability."""
    STANDARD_USER = "STANDARD_USER"
    ELEVATED_ADMIN = "ELEVATED_ADMIN"
    PROTECTED_SYSTEM = "PROTECTED_SYSTEM"


class VerifierStrategy(str, Enum):
    """Strategy used by the agent runtime to verify step completion."""
    RETURN_CODE_ONLY = "RETURN_CODE_ONLY"
    FILE_EXISTS = "FILE_EXISTS"
    FILE_NON_EMPTY = "FILE_NON_EMPTY"
    FILE_CONTAINS = "FILE_CONTAINS"
    WINDOW_READY = "WINDOW_READY"
    WINDOW_CLOSED = "WINDOW_CLOSED"
    UI_ELEMENT_STATE = "UI_ELEMENT_STATE"
    NETWORK_SSID = "NETWORK_SSID"
    PROCESS_RUNNING = "PROCESS_RUNNING"
    PROCESS_EXITED = "PROCESS_EXITED"
    CUSTOM = "CUSTOM"


@dataclass
class RetryPolicy:
    """Retry policy for capability execution."""
    max_retries: int = 1
    backoff_factor: float = 1.5
    initial_delay_s: float = 0.2
    timeout_s: float = 15.0
    retryable_error_codes: list[CapabilityErrorCode] = field(default_factory=lambda: [
        CapabilityErrorCode.TIMEOUT,
        CapabilityErrorCode.FOCUS_FAILED,
        CapabilityErrorCode.UNAVAILABLE,
    ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "backoff_factor": self.backoff_factor,
            "initial_delay_s": self.initial_delay_s,
            "timeout_s": self.timeout_s,
            "retryable_error_codes": [code.value for code in self.retryable_error_codes],
        }


@dataclass
class ParameterSchema:
    """Typed parameter specification for capability schema."""
    name: str
    type_name: str  # "str", "int", "float", "bool", "dict", "list", "Path"
    description: str
    required: bool = True
    default: Any = None
    allowed_values: Optional[list[Any]] = None
    pattern: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type_name,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.allowed_values is not None:
            result["allowed_values"] = self.allowed_values
        if self.pattern is not None:
            result["pattern"] = self.pattern
        return result


@dataclass
class CapabilitySchema:
    """Machine-readable capability contract for agent planner and verifiers."""
    id: str
    family: CapabilityFamily
    category: CapabilityCategory
    interaction_tier: InteractionTier
    description: str
    parameters: list[ParameterSchema] = field(default_factory=list)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effects: list[SideEffect] = field(default_factory=lambda: [SideEffect.READ_ONLY])
    privilege_level: PrivilegeLevel = PrivilegeLevel.STANDARD_USER
    risk: ToolRisk = ToolRisk.LOW
    reversibility: bool = False
    expected_duration_ms: float = 100.0
    verifier_strategy: VerifierStrategy = VerifierStrategy.RETURN_CODE_ONLY
    default_verifier_params: dict[str, Any] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    prerequisites: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family.value,
            "category": self.category.value,
            "interaction_tier": self.interaction_tier.value,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "output_schema": self.output_schema,
            "side_effects": [s.value for s in self.side_effects],
            "privilege_level": self.privilege_level.value,
            "risk": self.risk.value,
            "reversibility": self.reversibility,
            "expected_duration_ms": self.expected_duration_ms,
            "verifier_strategy": self.verifier_strategy.value,
            "default_verifier_params": self.default_verifier_params,
            "retry_policy": self.retry_policy.to_dict(),
            "prerequisites": self.prerequisites,
        }

    def validate_arguments(self, kwargs: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate input arguments against parameter definitions."""
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return False, f"Missing required parameter: '{param.name}'"
            if param.name in kwargs:
                val = kwargs[param.name]
                if param.allowed_values and val not in param.allowed_values:
                    return False, f"Value '{val}' for '{param.name}' not in allowed values: {param.allowed_values}"
        return True, None
