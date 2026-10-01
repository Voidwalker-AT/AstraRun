"""Execution data models and typed observation schemas for AstraRun 1.0."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionStatus(str, Enum):
    """Lifecycle status of a runtime execution request."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    DENIED = "DENIED"


@dataclass
class ResourceUsage:
    """Hardware resource telemetry recorded during process execution."""
    peak_memory_bytes: int = 0
    user_time_ms: float = 0.0
    kernel_time_ms: float = 0.0


@dataclass(frozen=True)
class ExecutionRequest:
    """Strongly typed execution request submitted to DynamicExecutionRuntime."""
    executable: str
    args: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    environment: Optional[Dict[str, str]] = None
    timeout: float = 30.0
    memory_limit_bytes: Optional[int] = None  # None for default workstation limit
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    ownership: str = "astra_owned"
    authorization_ref: Optional[str] = None
    stealth: bool = True  # CREATE_NO_WINDOW = 0x08000000
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionObservation:
    """
    Standardized, typed execution observation returned to TaskRuntime and models.
    All stdout/stderr streams are cryptographically scrubbed by SecretBroker.
    """
    status: ExecutionStatus
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: float
    timeout: bool
    killed: bool
    resource_usage: ResourceUsage
    redaction_occurred: bool
    redaction_metadata: Dict[str, Any]
    task_id: str
    audit_event: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS and self.exit_code == 0
