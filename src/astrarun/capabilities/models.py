"""Capability abstractions and structured result models for AstraRun v0.7."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from astrarun.core.models import ToolRisk


class CapabilityCategory(str, Enum):
    """Subsystem domains for workstation capabilities."""
    APPLICATION = "APPLICATION"
    FILE = "FILE"
    PROCESS = "PROCESS"
    WINDOW = "WINDOW"
    AUDIO = "AUDIO"
    PROJECT = "PROJECT"
    SYSTEM = "SYSTEM"
    NETWORK = "NETWORK"
    WORKFLOW = "WORKFLOW"
    INTERACTION = "INTERACTION"


class CapabilityPermission(str, Enum):
    """Execution permission levels."""
    AUTO = "AUTO"
    CONFIRM = "CONFIRM"
    BLOCK = "BLOCK"


class CapabilityHealth(str, Enum):
    """Availability status of capability adapter."""
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class CapabilityErrorCode(str, Enum):
    """Standard error codes across capabilities."""
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"
    STALE_ENTITY = "STALE_ENTITY"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    OS_ERROR = "OS_ERROR"
    TIMEOUT = "TIMEOUT"
    UNSUPPORTED_UI = "UNSUPPORTED_UI"
    FOCUS_FAILED = "FOCUS_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    NOT_SUPPORTED = "NOT_SUPPORTED"


@dataclass
class CapabilityResult:
    """Typed result contract emitted by all capability executions."""
    success: bool
    capability: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[CapabilityErrorCode] = None
    context_updates: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "capability": self.capability,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "error_code": self.error_code.value if self.error_code else None,
            "context_updates": self.context_updates,
            "provenance": self.provenance,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def ok(
        cls,
        capability: str,
        message: str,
        data: Optional[dict[str, Any]] = None,
        context_updates: Optional[list[dict[str, Any]]] = None,
        latency_ms: float = 0.0,
    ) -> CapabilityResult:
        """Helper to create a successful result."""
        return cls(
            success=True,
            capability=capability,
            message=message,
            data=data or {},
            context_updates=context_updates or [],
            latency_ms=latency_ms,
        )

    @classmethod
    def fail(
        cls,
        capability: str,
        message: str,
        error_code: CapabilityErrorCode = CapabilityErrorCode.OS_ERROR,
        error: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        latency_ms: float = 0.0,
    ) -> CapabilityResult:
        """Helper to create a failed result."""
        return cls(
            success=False,
            capability=capability,
            message=message,
            error=error or message,
            error_code=error_code,
            data=data or {},
            latency_ms=latency_ms,
        )


@dataclass
class Capability:
    """Metadata and execution contract for an OS capability."""
    id: str
    category: CapabilityCategory
    description: str
    args_schema: dict[str, Any]
    risk: ToolRisk = ToolRisk.LOW
    read_only: bool = True
    requires_confirmation: bool = False
    reversible: bool = False
    context_effects: list[str] = field(default_factory=list)
    handler: Callable[..., Any] = field(default=lambda **_: None)
    permission: CapabilityPermission = CapabilityPermission.AUTO
    health: CapabilityHealth = CapabilityHealth.AVAILABLE
    health_reason: str = ""
    outputs: list[str] = field(default_factory=list)
    security_metadata: Optional[Any] = None

    def get_security_metadata(self) -> Any:
        """Return authoritative CapabilitySecurityMetadata, creating a strict fallback if not set."""
        if self.security_metadata is not None:
            return self.security_metadata
        try:
            from astrarun.capabilities.manifest import get_authoritative_metadata
            meta = get_authoritative_metadata(self.id)
            if meta is not None:
                return meta
        except Exception:
            pass
        from astrarun.security.models import CapabilityOperationKind, CapabilitySecurityMetadata, RiskLevel
        risk_map = {
            ToolRisk.LOW: RiskLevel.LOW,
            ToolRisk.MEDIUM: RiskLevel.MEDIUM,
            ToolRisk.HIGH: RiskLevel.HIGH,
            ToolRisk.BLOCKED: RiskLevel.CRITICAL,
        }
        r = risk_map.get(self.risk, RiskLevel.LOW)
        op_kind = CapabilityOperationKind.OBSERVE_READ_ONLY if self.read_only else CapabilityOperationKind.UNKNOWN_CONSEQUENTIAL
        return CapabilitySecurityMetadata(
            operation_kind=op_kind,
            risk=r,
            mutates_state=not self.read_only,
            requires_confirmation=self.requires_confirmation or (self.permission == CapabilityPermission.CONFIRM),
            resource_scope=self.category.value.lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "description": self.description,
            "outputs": self.outputs,
            "args_schema": {k: getattr(v, "__name__", str(v)) for k, v in self.args_schema.items()},
            "risk": self.risk.value,
            "read_only": self.read_only,
            "requires_confirmation": self.requires_confirmation,
            "reversible": self.reversible,
            "context_effects": self.context_effects,
            "permission": self.permission.value,
            "health": self.health.value,
            "health_reason": self.health_reason,
        }


@dataclass
class Observation:
    """Structured fact observation captured from OS state."""
    type: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    freshness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp,
            "freshness": self.freshness,
        }


@dataclass
class ApplicationEntity:
    """Runtime application entity model."""
    app_id: str
    display_name: str
    executable: str
    pid: Optional[int] = None
    windows: list[int] = field(default_factory=list)
    running: bool = False
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "display_name": self.display_name,
            "executable": self.executable,
            "pid": self.pid,
            "windows": self.windows,
            "running": self.running,
            "path": self.path,
        }


@dataclass
class FileCandidate:
    """File candidate discovered through search."""
    path: str
    filename: str
    score: float = 1.0
    reason: str = ""
    modified_time: float = 0.0
    size: int = 0
    extension: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "filename": self.filename,
            "score": self.score,
            "reason": self.reason,
            "modified_time": self.modified_time,
            "size": self.size,
            "extension": self.extension,
        }


@dataclass
class PortInfo:
    """Port listening inspection model."""
    port: int
    protocol: str = "tcp"
    address: str = "127.0.0.1"
    state: str = "LISTEN"
    pid: Optional[int] = None
    process_name: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "protocol": self.protocol,
            "address": self.address,
            "state": self.state,
            "pid": self.pid,
            "process_name": self.process_name,
        }


@dataclass
class GitStatus:
    """Structured git repository status."""
    branch: str
    modified: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    ahead: int = 0
    behind: int = 0
    is_dirty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "modified": self.modified,
            "untracked": self.untracked,
            "ahead": self.ahead,
            "behind": self.behind,
            "is_dirty": self.is_dirty,
        }


@dataclass
class WindowEntity:
    """Top-level window entity model for discovery."""
    hwnd: int
    title: str
    pid: int
    app_id: str
    monitor: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    state: str = "normal"
    visible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "pid": self.pid,
            "app_id": self.app_id,
            "monitor": self.monitor,
            "bounds": list(self.bounds),
            "state": self.state,
            "visible": self.visible,
        }
