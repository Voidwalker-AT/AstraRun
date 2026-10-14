"""Safety policies, password privacy, and destructive control classification for UI interaction."""

from __future__ import annotations

import re
from typing import Optional, Set, Tuple

from astrarun.capabilities.models import CapabilityErrorCode
from astrarun.core.logging import get_logger
from astrarun.interaction.models import ControlType, UIElementRef
from astrarun.windows.policy import is_astrarun_window

logger = get_logger("astrarun.interaction.policy")

# Protected system window classes that AstraRun MUST NEVER interact with destructively
PROTECTED_WINDOW_CLASSES: Set[str] = {
    "progman",
    "workerw",
    "shell_traywnd",
    "shell_secondarytraywnd",
}

# Destructive keyword patterns that require explicit user confirmation
DESTRUCTIVE_KEYWORDS: Set[str] = {
    "delete",
    "remove",
    "destroy",
    "format",
    "drop",
    "truncate",
    "erase",
    "purge",
    "uninstall",
    "wipe",
    "reset",
    "factory reset",
    "clear all",
    "purchase",
    "buy",
    "buy now",
    "transfer funds",
    "transfer money",
    "terminate",
    "empty recycle bin",
    "empty trash",
    "reinstall",
    "overwrite",
}

_SIMULATED_INTERACTION_VALIDATION: bool = False


def set_simulated_interaction_validation(enabled: bool) -> None:
    """Enable or disable simulated interaction validation for headless testing."""
    global _SIMULATED_INTERACTION_VALIDATION
    _SIMULATED_INTERACTION_VALIDATION = enabled


def is_simulated_interaction_validation() -> bool:
    """Check if interaction validation is running in simulated mode."""
    return _SIMULATED_INTERACTION_VALIDATION


def is_destructive_action(name: str, action: str = "click", control_type: ControlType | str = ControlType.BUTTON) -> Tuple[bool, str]:
    """
    Evaluate whether interacting with a given UI control constitutes a destructive action.
    Returns (is_destructive, reason).
    """
    clean_name = (name or "").lower().strip()
    clean_action = (action or "").lower().strip()

    # Cancel, Close, or Dismiss buttons are safe navigation actions, not destructive
    safe_exceptions = {"cancel", "close", "dismiss", "back", "abort", "ignore", "reset zoom", "reset view"}
    if clean_name in safe_exceptions:
        return False, "Safe navigation action"

    for keyword in DESTRUCTIVE_KEYWORDS:
        # Check word boundaries
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, clean_name) or re.search(pattern, clean_action):
            return True, f"Target action matches high-risk pattern '{keyword}' and requires user confirmation."

    return False, "Safe operation"


def is_password_element(element: UIElementRef) -> bool:
    """Check if an element is a password or secret input field."""
    if element.is_password:
        return True

    indicators = ("password", "passwd", "pwd", "pin", "secret")
    ident_str = f"{element.name} {element.automation_id} {element.class_name}".lower()
    return any(ind in ident_str for ind in indicators)


def redact_sensitive_content(text: str, is_password: bool = False) -> str:
    """Redact passwords and secrets to protect privacy in task ledger and telemetry."""
    if is_password:
        return "[REDACTED_PASSWORD]"

    if not text:
        return ""

    # Redact common tokens / keys
    redacted = re.sub(r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]{16,}", r"\1[REDACTED_TOKEN]", text)
    redacted = re.sub(r"(?i)(api[_-]?key\s*[:=]\s*)[a-zA-Z0-9_\-\.]{16,}", r"\1[REDACTED_API_KEY]", redacted)
    redacted = re.sub(r"\b(?:\d[ -]*?){13,16}\b", "[REDACTED_CARD]", redacted)
    return redacted


def _ensure_desktop_attached() -> None:
    """Ensure current thread is attached to the interactive input desktop."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)

        h_desk = user32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId())
        if h_desk:
            buf_desk = ctypes.create_unicode_buffer(256)
            if user32.GetUserObjectInformationW(h_desk, 2, buf_desk, 256, None) and buf_desk.value.lower() == "default":
                return

        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.OpenDesktopW.restype = ctypes.c_void_p
        user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]
        user32.SetThreadDesktop.restype = wintypes.BOOL
        DESKTOP_ALL = 0x01FF
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_ALL)
        if not hdesk:
            hdesk = user32.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def validate_interaction_target(hwnd: int, pid: Optional[int] = None) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """
    Validate that a target window handle is alive, interactive, and safe to manipulate.
    """
    if is_simulated_interaction_validation():
        return True, "Target window validated (simulated).", None

    if hwnd == 0:
        return False, "Window handle is NULL (0).", CapabilityErrorCode.NOT_FOUND

    if is_astrarun_window(hwnd):
        return False, "Target HWND belongs to AstraRun itself (self-manipulation blocked).", CapabilityErrorCode.BLOCKED

    _ensure_desktop_attached()

    import ctypes
    user32 = ctypes.windll.user32

    if not user32.IsWindow(hwnd):
        return False, f"Window HWND {hwnd} is dead or invalid.", CapabilityErrorCode.STALE_ENTITY

    class_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buf, 256)
    wnd_class = class_buf.value.lower().strip()

    if wnd_class in PROTECTED_WINDOW_CLASSES:
        return False, f"Target window belongs to protected system class '{wnd_class}'.", CapabilityErrorCode.BLOCKED

    return True, "Window handle is valid and interactive.", None
