"""Data models and observation structures for the AstraRun ComputerUse subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ActionBackend(str, Enum):
    UIA = "UIA"
    WIN32 = "WIN32"
    CDP = "CDP"
    PHYSICAL = "PHYSICAL"
    CV = "CV"


class ControlType(str, Enum):
    BUTTON = "BUTTON"
    EDIT = "EDIT"
    DOCUMENT = "DOCUMENT"
    CHECKBOX = "CHECKBOX"
    RADIO = "RADIO"
    COMBOBOX = "COMBOBOX"
    LIST = "LIST"
    LIST_ITEM = "LIST_ITEM"
    TAB = "TAB"
    TAB_ITEM = "TAB_ITEM"
    MENU = "MENU"
    MENU_ITEM = "MENU_ITEM"
    HYPERLINK = "HYPERLINK"
    WINDOW = "WINDOW"
    PANE = "PANE"
    UNKNOWN = "UNKNOWN"


@dataclass
class UIElement:
    """Normalized accessible UI element descriptor."""
    automation_id: str
    name: str
    control_type: ControlType
    hwnd: int
    bounds: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height)
    patterns: List[str] = field(default_factory=list)
    is_enabled: bool = True
    is_focused: bool = False
    value: Optional[str] = None
    backend: ActionBackend = ActionBackend.UIA

    @property
    def center_coords(self) -> Optional[Tuple[int, int]]:
        if self.bounds and len(self.bounds) == 4:
            x, y, w, h = self.bounds
            if w > 0 and h > 0:
                return (x + w // 2, y + h // 2)
        return None


@dataclass
class UIAction:
    """Action request dispatched to ComputerUse.interact()."""
    action_type: str  # "click", "type", "shortcut", "scroll", "select", "focus", "toggle"
    target: Optional[str] = None
    text: Optional[str] = None
    shortcut: Optional[str] = None
    hwnd: Optional[int] = None
    element: Optional[UIElement] = None
    coordinates: Optional[Tuple[int, int]] = None
    force: bool = False
    task_id: Optional[str] = None


@dataclass
class ComputerUseObservation:
    """Normalized observation structure conforming to universal computer-use contract."""
    timestamp: float = field(default_factory=time.time)
    application_identity: Optional[str] = None
    window_identity: Optional[int] = None  # HWND
    window_title: str = ""
    focused_element: Optional[Dict[str, Any]] = None
    interactable_elements: List[Dict[str, Any]] = field(default_factory=list)
    available_actions: List[str] = field(default_factory=list)
    browser_sessions: List[Dict[str, Any]] = field(default_factory=list)
    user_taking_over: bool = False
    source_backend: ActionBackend = ActionBackend.UIA
    confidence: float = 1.0
    freshness: float = field(default_factory=time.time)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def is_stale(self, max_age_seconds: float = 2.0) -> bool:
        return (time.time() - self.freshness) > max_age_seconds


@dataclass
class VerificationCondition:
    """Condition to be verified in ComputerUse.verify()."""
    condition_type: str  # "window_visible", "process_running", "text_present", "element_state"
    expected_value: Any = None
    target: Optional[str] = None
    hwnd: Optional[int] = None
    timeout_seconds: float = 2.0


@dataclass
class VerificationResult:
    """Outcome of environmental side-effect verification."""
    verified: bool
    condition_type: str
    observed_value: Any = None
    message: str = ""
    latency_ms: float = 0.0


@dataclass
class RecoveryAction:
    """Bounded recovery action produced by ComputerUse.recover()."""
    action: str  # "retry", "reobserve", "dismiss_dialog", "relaunch", "fail"
    reason: str
    attempt_number: int = 1
    max_attempts: int = 3
