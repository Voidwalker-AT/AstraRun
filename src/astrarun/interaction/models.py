"""Models and data structures for UI Automation and Control Grounding (v0.10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple


class ControlType(str, Enum):
    """Semantic UI control types recognized by AstraRun."""
    BUTTON = "button"
    CHECK_BOX = "check_box"
    COMBO_BOX = "combo_box"
    EDIT = "edit"
    MENU_BAR = "menu_bar"
    MENU_ITEM = "menu_item"
    TAB = "tab"
    TAB_ITEM = "tab_item"
    RADIO_BUTTON = "radio_button"
    WINDOW = "window"
    PANE = "pane"
    DOCUMENT = "document"
    LIST = "list"
    LIST_ITEM = "list_item"
    HYPERLINK = "hyperlink"
    CUSTOM = "custom"
    UNKNOWN = "unknown"

    @classmethod
    def from_uia_type_id(cls, type_id: int) -> ControlType:
        """Map standard Microsoft UI Automation control type ID to AstraRun ControlType."""
        mapping = {
            50000: cls.BUTTON,
            50001: cls.BUTTON,          # Calendar / Button
            50002: cls.CHECK_BOX,
            50003: cls.COMBO_BOX,
            50004: cls.EDIT,
            50005: cls.HYPERLINK,
            50006: cls.UNKNOWN,         # Image
            50007: cls.LIST_ITEM,
            50008: cls.LIST,
            50010: cls.MENU_BAR,
            50011: cls.MENU_ITEM,
            50012: cls.UNKNOWN,         # ProgressBar
            50013: cls.RADIO_BUTTON,
            50014: cls.UNKNOWN,         # ScrollBar
            50015: cls.UNKNOWN,         # Slider
            50016: cls.UNKNOWN,         # Spinner
            50017: cls.UNKNOWN,         # StatusBar
            50018: cls.TAB,
            50019: cls.TAB_ITEM,
            50020: cls.UNKNOWN,         # Text
            50021: cls.UNKNOWN,         # ToolBar
            50022: cls.UNKNOWN,         # ToolTip
            50023: cls.UNKNOWN,         # Tree
            50024: cls.UNKNOWN,         # TreeItem
            50025: cls.CUSTOM,
            50026: cls.CUSTOM,          # Group
            50027: cls.UNKNOWN,         # Thumb
            50028: cls.UNKNOWN,         # DataGrid
            50029: cls.LIST_ITEM,       # DataItem
            50030: cls.DOCUMENT,
            50031: cls.UNKNOWN,         # SplitButton
            50032: cls.WINDOW,
            50033: cls.PANE,
            50034: cls.UNKNOWN,         # Header
            50035: cls.UNKNOWN,         # HeaderItem
            50036: cls.UNKNOWN,         # Table
            50037: cls.UNKNOWN,         # TitleBar
            50038: cls.UNKNOWN,         # Separator
        }
        return mapping.get(type_id, cls.UNKNOWN)


class ControlPattern(str, Enum):
    """Semantic UIA interaction patterns."""
    INVOKE = "invoke"
    VALUE = "value"
    TOGGLE = "toggle"
    SELECTION_ITEM = "selection_item"
    SCROLL = "scroll"
    EXPAND_COLLAPSE = "expand_collapse"
    FOCUS = "focus"


@dataclass
class UIElementRef:
    """
    Stale-resistant reference handle for a semantic UI element.
    Contains identification attributes, geometric bounds, and capabilities.
    """
    hwnd: int
    pid: int
    control_type: ControlType
    automation_id: str = ""
    name: str = ""
    class_name: str = ""
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, width, height
    runtime_id: Tuple[int, ...] = field(default_factory=tuple)
    is_enabled: bool = True
    is_offscreen: bool = False
    is_password: bool = False
    has_keyboard_focus: bool = False
    supported_patterns: list[str] = field(default_factory=list)
    depth: int = 0
    value: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "hwnd": self.hwnd,
            "pid": self.pid,
            "control_type": self.control_type.value,
            "automation_id": self.automation_id,
            "name": self.name,
            "class_name": self.class_name,
            "bounds": list(self.bounds),
            "is_enabled": self.is_enabled,
            "is_offscreen": self.is_offscreen,
            "is_password": self.is_password,
            "has_keyboard_focus": self.has_keyboard_focus,
            "supported_patterns": self.supported_patterns,
            "depth": self.depth,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UIElementRef:
        """Construct UIElementRef from dictionary."""
        ctype = data.get("control_type", "unknown")
        try:
            parsed_type = ControlType(ctype)
        except ValueError:
            parsed_type = ControlType.UNKNOWN

        bounds = data.get("bounds", [0, 0, 0, 0])
        return cls(
            hwnd=data.get("hwnd", 0),
            pid=data.get("pid", 0),
            control_type=parsed_type,
            automation_id=data.get("automation_id", ""),
            name=data.get("name", ""),
            class_name=data.get("class_name", ""),
            bounds=(bounds[0], bounds[1], bounds[2], bounds[3]) if len(bounds) >= 4 else (0, 0, 0, 0),
            runtime_id=tuple(data.get("runtime_id", ())),
            is_enabled=data.get("is_enabled", True),
            is_offscreen=data.get("is_offscreen", False),
            is_password=data.get("is_password", False),
            has_keyboard_focus=data.get("has_keyboard_focus", False),
            supported_patterns=data.get("supported_patterns", []),
            depth=data.get("depth", 0),
            value=data.get("value", ""),
        )


@dataclass
class KeyboardShortcut:
    """Strongly-typed representation of a keyboard shortcut."""
    modifiers: list[str] = field(default_factory=list)  # ctrl, shift, alt, win
    key: str = ""                                       # c, v, p, enter, f5, tab, etc.

    @property
    def canonical_string(self) -> str:
        """Return standardized representation, e.g. Ctrl+Shift+P."""
        parts = [m.capitalize() for m in self.modifiers]
        if self.key:
            parts.append(self.key.upper() if len(self.key) == 1 else self.key.capitalize())
        return "+".join(parts)


@dataclass
class ResolutionCandidate:
    """A scored element candidate during query resolution."""
    element: UIElementRef
    score: float
    match_reason: str


@dataclass
class ResolutionResult:
    """Outcome of resolving a natural language target query against UI elements."""
    element: Optional[UIElementRef]
    confidence: float
    match_reason: str
    candidates: list[ResolutionCandidate] = field(default_factory=list)
    ambiguous: bool = False
    clarification_prompt: Optional[str] = None

    @property
    def is_resolved(self) -> bool:
        """Return True if a unique unambiguous element was resolved."""
        return self.element is not None and not self.ambiguous
