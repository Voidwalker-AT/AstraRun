"""ApplicationSession abstraction for AstraRun ComputerUse."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class SessionState(str, Enum):
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DETACHED = "DETACHED"
    TERMINATED = "TERMINATED"


@dataclass
class ApplicationSession:
    """
    Represents an active application or window context managed by ComputerUse.
    Maintains strict lifecycle ownership and interaction state.
    """
    session_id: str
    app_name: str
    pid: Optional[int] = None
    hwnd: Optional[int] = None
    task_id: Optional[str] = None
    state: SessionState = SessionState.INITIALIZING
    created_at: float = field(default_factory=time.time)
    ledger_resource_id: Optional[str] = None
    user_interacted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_alive(self) -> bool:
        if self.state in (SessionState.TERMINATED, SessionState.DETACHED):
            return False
        if self.pid:
            import psutil
            return psutil.pid_exists(self.pid)
        return True
