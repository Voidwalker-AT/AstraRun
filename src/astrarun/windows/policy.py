"""Safety policies and validation invariants for Window Intelligence."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from typing import Set

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.windows.policy")

# Set of AstraRun HWNDs to protect against self-mutation
_ASTRARUN_HWNDS: Set[int] = set()

# Protected system window classes that AstraRun MUST NEVER close, minimize, or manipulate
PROTECTED_WINDOW_CLASSES = {
    "progman",                # Windows desktop manager
    "workerw",                # Desktop background wallpaper host
    "shell_traywnd",          # Primary Windows Taskbar
    "shell_secondarytraywnd", # Secondary monitor taskbars
}


_SIMULATED_WINDOW_VALIDATION: bool = False


def set_simulated_window_validation(enabled: bool) -> None:
    """Enable or disable simulated window validation for headless benchmarking."""
    global _SIMULATED_WINDOW_VALIDATION
    _SIMULATED_WINDOW_VALIDATION = enabled


def is_simulated_window_validation() -> bool:
    """Check if window validation is operating in simulated mode."""
    return _SIMULATED_WINDOW_VALIDATION


def register_astrarun_hwnd(hwnd: int) -> None:
    """Register an AstraRun window handle so it is immune to accidental manipulation."""
    if hwnd:
        _ASTRARUN_HWNDS.add(hwnd)
        logger.debug("Registered AstraRun self-protection HWND: %d", hwnd)


def unregister_astrarun_hwnd(hwnd: int) -> None:
    """Unregister an AstraRun window handle upon destruction."""
    _ASTRARUN_HWNDS.discard(hwnd)


def is_astrarun_window(hwnd: int) -> bool:
    """Check if the given HWND belongs to AstraRun's UI."""
    return hwnd in _ASTRARUN_HWNDS


def validate_window_identity(hwnd: int, expected_pid: int | None = None) -> tuple[bool, str, CapabilityErrorCode | None]:
    """
    Validate that an HWND is valid, alive, and optionally belongs to the expected PID.
    Guards against TOCTOU handle recycling races.
    """
    if not hwnd or hwnd <= 0:
        return False, "Invalid or null window handle (HWND <= 0).", CapabilityErrorCode.INVALID_ARGUMENT

    if is_astrarun_window(hwnd):
        return False, "Target window belongs to AstraRun UI and is protected from external manipulation.", CapabilityErrorCode.PERMISSION_DENIED

    if sys.platform != "win32" or _SIMULATED_WINDOW_VALIDATION:
        return True, "Simulated environment validation OK.", None

    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return False, f"Window handle {hwnd} is stale or no longer exists (STALE_ENTITY).", CapabilityErrorCode.NOT_FOUND

    # Check protected classes
    class_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buf, 256)
    class_name = class_buf.value.strip().lower()
    if class_name in PROTECTED_WINDOW_CLASSES:
        return False, f"Window '{class_name}' is a protected Windows shell component.", CapabilityErrorCode.BLOCKED

    # Check shell window handle
    shell_hwnd = user32.GetShellWindow()
    if shell_hwnd and hwnd == shell_hwnd:
        return False, "Target is the Windows Desktop Shell window.", CapabilityErrorCode.BLOCKED

    # Validate PID matches if specified
    if expected_pid is not None and expected_pid > 0:
        pid_buf = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
        current_pid = pid_buf.value
        if current_pid != expected_pid:
            return (
                False,
                f"Window handle {hwnd} recycled: expected PID {expected_pid}, found PID {current_pid} (TOCTOU).",
                CapabilityErrorCode.INVALID_ARGUMENT,
            )

    return True, "Window identity verified.", None


def clamp_geometry(x: int, y: int, width: int, height: int, min_w: int = 150, min_h: int = 100) -> tuple[int, int, int, int]:
    """Ensure dimensions are non-negative and satisfy reasonable minimum bounds."""
    w = max(min_w, width)
    h = max(min_h, height)
    # Clamp extreme bounds to prevent overflow (-100,000 to +100,000)
    cx = max(-50000, min(50000, x))
    cy = max(-50000, min(50000, y))
    return (cx, cy, w, h)
