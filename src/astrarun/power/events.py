"""Power and Session Lifecycle Events for AstraRun 1.0."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class PowerState(str, Enum):
    """Current operating power state of the resident runtime."""
    RUNNING = "RUNNING"
    SUSPENDING = "SUSPENDING"
    SUSPENDED = "SUSPENDED"
    RESUMING = "RESUMING"


class PowerEventType(str, Enum):
    """Canonical power lifecycle events recorded in ledger and telemetry."""
    SYSTEM_SUSPENDING = "SYSTEM_SUSPENDING"
    TASK_SUSPENDED = "TASK_SUSPENDED"
    SYSTEM_RESUMED = "SYSTEM_RESUMED"
    MACHINE_STATE_REFRESHED = "MACHINE_STATE_REFRESHED"
    TASK_RESUME_STARTED = "TASK_RESUME_STARTED"
    TASK_RESUMED = "TASK_RESUMED"
    TASK_RESUME_BLOCKED = "TASK_RESUME_BLOCKED"
    TASK_REPLANNED_AFTER_RESUME = "TASK_REPLANNED_AFTER_RESUME"
    DISPLAY_STATE_CHANGED = "DISPLAY_STATE_CHANGED"
    SESSION_ENDING = "SESSION_ENDING"


class DisplayState(str, Enum):
    """Observed physical display monitor power state."""
    OFF = "OFF"
    ON = "ON"
    DIM = "DIM"
    UNKNOWN = "UNKNOWN"


class ResumeVerdict(str, Enum):
    """Post-wake recovery assessment for an interrupted or suspended task."""
    UNCHANGED = "UNCHANGED"
    RECOVERABLE_DRIFT = "RECOVERABLE_DRIFT"
    REQUIRES_REPLAN = "REQUIRES_REPLAN"
    REQUIRES_USER = "REQUIRES_USER"
    FAILED_EXTERNAL = "FAILED_EXTERNAL"


@dataclass(frozen=True)
class PowerEvent:
    """Immutable record of a system power or session event."""
    event_type: PowerEventType
    timestamp: float = field(default_factory=time.time)
    monotonic_time: float = field(default_factory=time.monotonic)
    task_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
