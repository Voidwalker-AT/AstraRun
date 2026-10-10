"""Desktop World State Abstraction for AstraRun ComputerUse."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class WindowObservation:
    """Detailed observation of a desktop top-level or child window."""
    hwnd: int
    pid: int
    process_creation_time: float = 0.0
    application_identity: str = ""
    title: str = ""
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)  # (left, top, width, height)
    is_visible: bool = True
    is_minimized: bool = False
    is_maximized: bool = False
    is_foreground: bool = False
    owner_hwnd: int = 0
    is_modal: bool = False
    is_dialog: bool = False
    dialog_type: str = ""  # "#32770", "file_dialog", "message_box", "app_modal", ""
    astra_owned: bool = False
    task_id: Optional[str] = None
    uia_available: bool = False
    last_observed: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def app_name(self) -> str:
        return self.application_identity


@dataclass
class DialogObservation:
    """Observation of an application dialog or modal prompt."""
    hwnd: int
    owner_hwnd: int
    title: str
    dialog_class: str
    dialog_type: str  # "file_save", "file_open", "error", "confirmation", "custom"
    prompt_text: str = ""
    buttons: List[str] = field(default_factory=list)
    astra_owned: bool = False
    task_id: Optional[str] = None
    last_observed: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessObservation:
    """Observation of an OS process relevant to tasks."""
    pid: int
    create_time: float
    name: str
    exe_path: str = ""
    cmdline: List[str] = field(default_factory=list)
    astra_owned: bool = False
    task_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DesktopWorldState:
    """
    Canonical live ComputerUse world-state representation.
    Maintains ambient vs. Astra-owned desktop state across windows, dialogs,
    processes, focused controls, and user takeover indicators.
    """
    timestamp: float = field(default_factory=time.time)
    foreground_window: Optional[WindowObservation] = None
    cursor_position: Optional[Tuple[int, int]] = None
    monitors: List[Dict[str, Any]] = field(default_factory=list)
    visible_windows: List[WindowObservation] = field(default_factory=list)
    dialogs: List[DialogObservation] = field(default_factory=list)
    processes: List[ProcessObservation] = field(default_factory=list)
    astra_owned_resources: List[Dict[str, Any]] = field(default_factory=list)
    user_owned_resources: List[Dict[str, Any]] = field(default_factory=list)
    focused_control: Optional[Dict[str, Any]] = None
    browser_sessions: List[Dict[str, Any]] = field(default_factory=list)
    user_takeover_active: bool = False
    observation_freshness: float = field(default_factory=time.time)
    observation_latency_ms: float = 0.0

    def compute_state_hash(self) -> str:
        """
        Compute deterministic SHA-256 state hash for divergence detection and causal audit.
        """
        payload = {
            "fg": self.foreground_window.hwnd if self.foreground_window else 0,
            "fg_title": self.foreground_window.title if self.foreground_window else "",
            "windows": [
                {
                    "hwnd": w.hwnd,
                    "title": w.title,
                    "bounds": w.bounds,
                    "min": w.is_minimized,
                    "modal": w.is_modal,
                }
                for w in sorted(self.visible_windows, key=lambda x: x.hwnd)
            ],
            "dialogs": [d.hwnd for d in sorted(self.dialogs, key=lambda x: x.hwnd)],
            "astra_resources": len(self.astra_owned_resources),
            "takeover": self.user_takeover_active,
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def find_window_by_app(self, app_name: str) -> Optional[WindowObservation]:
        """Find the top-most visible window belonging to the given application name."""
        stem = app_name.lower().replace(".exe", "")
        for w in self.visible_windows:
            if stem in w.application_identity.lower() or stem in w.title.lower():
                return w
        return None

    def find_dialog_for_hwnd(self, owner_hwnd: int) -> Optional[DialogObservation]:
        """Find active dialog owned by the given window handle."""
        for d in self.dialogs:
            if d.owner_hwnd == owner_hwnd:
                return d
        return None

    @property
    def active_dialogs(self) -> List[DialogObservation]:
        """Active dialogs observed on desktop."""
        return self.dialogs

    def has_astra_debris(self) -> bool:
        """Check whether any Astra-owned windows or dialogs remain open."""
        for w in self.visible_windows:
            if w.astra_owned:
                return True
        for d in self.dialogs:
            if d.astra_owned:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state summary for logging and audit."""
        return {
            "timestamp": self.timestamp,
            "state_hash": self.compute_state_hash(),
            "foreground_window": self.foreground_window.to_dict() if self.foreground_window else None,
            "cursor_position": self.cursor_position,
            "visible_window_count": len(self.visible_windows),
            "dialog_count": len(self.dialogs),
            "dialogs": [d.to_dict() for d in self.dialogs],
            "astra_owned_count": len(self.astra_owned_resources),
            "user_takeover_active": self.user_takeover_active,
            "observation_latency_ms": self.observation_latency_ms,
        }
