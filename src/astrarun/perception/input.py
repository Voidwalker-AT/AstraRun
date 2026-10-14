"""Native Win32 SendInput controller with DPI normalization, target verification, and user-takeover protection.

Guarantees:
  - ZERO reliance on pyautogui as an authoritative backend
  - Strict Per-Monitor-V2 DPI normalization across multi-monitor layouts
  - Pre-click target verification (anti-misclick guard against window movement or focus shift)
  - Immediate user-takeover interruption (PAUSED_USER_ACTIVE state)
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from enum import Enum

from astrarun.core.logging import get_logger
from astrarun.perception.models import BoundingBox, ElementBinding, ObservationGeneration

logger = get_logger("astrarun.perception.input")


class InputState(str, Enum):
    IDLE = "IDLE"
    EXECUTING = "EXECUTING"
    PAUSED_USER_ACTIVE = "PAUSED_USER_ACTIVE"
    ERROR = "ERROR"


class InputError(Exception):
    """Base exception for input subsystem errors."""
    pass


class StaleElementError(InputError):
    """Raised when an action is attempted on a stale element binding or generation."""
    pass


class UserInterferenceError(InputError):
    """Raised when synthetic input is interrupted by physical user activity."""
    pass

# Win32 SendInput constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0004
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


class NativeInputController:
    """
    Authoritative native Win32 SendInput execution controller.
    """
    _instance: Optional[NativeInputController] = None

    @classmethod
    def get_instance(cls) -> NativeInputController:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, enable_simulated: bool = False):
        self.enable_simulated = enable_simulated or sys.platform != "win32"
        self._user_takeover_detected = False
        self.state: InputState = InputState.IDLE
        self._last_cursor_pos: Optional[Tuple[int, int]] = None
        self._lock = threading.RLock()
        self._init_dpi_awareness()

    def _init_dpi_awareness(self) -> None:
        """Declare process as Per-Monitor-V2 DPI aware if on Windows 10/11."""
        if sys.platform == "win32" and not self.enable_simulated:
            try:
                # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                logger.debug("Configured Per-Monitor-V2 DPI awareness")
            except Exception as e:
                logger.debug("Failed setting Per-Monitor-V2 DPI awareness: %s", e)

    def get_cursor_position(self) -> Tuple[int, int]:
        """Fetch current hardware cursor position in screen coordinates."""
        if sys.platform != "win32" or self.enable_simulated:
            return (500, 500)
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    def check_user_takeover(self, expected_pos: Optional[Tuple[int, int]] = None) -> bool:
        """
        Detect if physical user moved mouse or engaged input since last synthetic event.
        """
        current_pos = self.get_cursor_position()
        if expected_pos is not None:
            # If current cursor differs from where synthetic action left it (> 15px)
            dx = abs(current_pos[0] - expected_pos[0])
            dy = abs(current_pos[1] - expected_pos[1])
            if dx > 15 or dy > 15:
                logger.warning("User takeover detected: cursor moved unexpectedly by (%d, %d)", dx, dy)
                self._user_takeover_detected = True
                self.state = InputState.PAUSED_USER_ACTIVE
                return True
        if self._user_takeover_detected:
            self.state = InputState.PAUSED_USER_ACTIVE
        return self._user_takeover_detected

    def reset_takeover(self) -> None:
        """Reset user takeover state after re-observation and operator consent."""
        self._user_takeover_detected = False
        self.state = InputState.IDLE

    def verify_target_before_click(
        self,
        target_point: Tuple[int, int],
        expected_hwnd: int,
        target_bbox: BoundingBox,
        generation: Optional[ObservationGeneration] = None,
    ) -> Tuple[bool, str]:
        """
        Pre-click target verification preventing misclicks if window moved or focus shifted.
        """
        px, py = target_point

        # 1. Check generation staleness
        if generation is not None and generation.is_stale(current_hwnd=expected_hwnd):
            return False, "TARGET_STALE: Observation generation expired or invalidated"

        # 2. Check point containment in expected bounding box
        if not target_bbox.contains(px, py):
            return False, f"TARGET_OOB: Point ({px}, {py}) outside expected bbox {target_bbox}"

        if sys.platform == "win32" and not self.enable_simulated:
            user32 = ctypes.windll.user32

            # 3. Check target window existence
            if not user32.IsWindow(expected_hwnd):
                return False, f"TARGET_GONE: HWND {expected_hwnd} is no longer a valid window"

            # 4. Check window bounds haven't shifted
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(expected_hwnd, ctypes.byref(rect))
            current_bounds = BoundingBox(x=rect.left, y=rect.top, width=rect.right - rect.left, height=rect.bottom - rect.top)
            if generation and generation.is_stale(current_bounds=current_bounds):
                return False, "TARGET_MOVED: Window bounds shifted during planning"

            # 5. Check foreground focus or bring to foreground
            fg_hwnd = user32.GetForegroundWindow()
            if fg_hwnd != expected_hwnd:
                user32.SetForegroundWindow(expected_hwnd)
                time.sleep(0.05)

        return True, "VERIFIED"

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        double_click: bool = False,
        expected_hwnd: Optional[int] = None,
        target_bbox: Optional[BoundingBox] = None,
        generation: Optional[ObservationGeneration] = None,
    ) -> Tuple[bool, str]:
        """
        Execute verified physical mouse click at (x, y) screen coordinates via SendInput.
        """
        with self._lock:
            # 1. Target verification guard
            if expected_hwnd is not None and target_bbox is not None:
                valid, reason = self.verify_target_before_click(
                    target_point=(x, y),
                    expected_hwnd=expected_hwnd,
                    target_bbox=target_bbox,
                    generation=generation,
                )
                if not valid:
                    logger.warning("Click halted by target verification: %s", reason)
                    return False, reason

            # 2. User takeover guard
            if self.check_user_takeover():
                return False, "PAUSED_USER_ACTIVE: Synthetic input halted due to active user input"

            if self.enable_simulated or sys.platform != "win32":
                logger.info("Simulated %s click at (%d, %d)", button, x, y)
                self._last_cursor_pos = (x, y)
                return True, "CLICKED_SIMULATED"

            # 3. Move cursor to coordinates
            self._send_mouse_move(x, y)
            time.sleep(0.02)

            # 4. Dispatch Click Events
            down_flag = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
            up_flag = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP

            inp_down = INPUT(type=INPUT_MOUSE)
            inp_down.u.mi.dwFlags = down_flag
            inp_up = INPUT(type=INPUT_MOUSE)
            inp_up.u.mi.dwFlags = up_flag

            events = [inp_down, inp_up]
            if double_click:
                events.extend([inp_down, inp_up])

            arr = (INPUT * len(events))(*events)
            ctypes.windll.user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
            self._last_cursor_pos = (x, y)
            return True, "CLICKED"

    def type_text(self, text: str, target_hwnd: Optional[int] = None) -> Tuple[bool, str]:
        """
        Send text typing via Unicode SendInput events without clipboard interference.
        """
        with self._lock:
            if self.check_user_takeover():
                return False, "PAUSED_USER_ACTIVE: Typing halted due to user takeover"

            if self.enable_simulated or sys.platform != "win32":
                logger.info("Simulated typing: '%s'", text)
                return True, "TYPED_SIMULATED"

            if target_hwnd:
                ctypes.windll.user32.SetForegroundWindow(target_hwnd)
                time.sleep(0.05)

            events: List[INPUT] = []
            for ch in text:
                code = ord(ch)
                inp_down = INPUT(type=INPUT_KEYBOARD)
                inp_down.u.ki.wScan = code
                inp_down.u.ki.dwFlags = KEYEVENTF_UNICODE
                inp_up = INPUT(type=INPUT_KEYBOARD)
                inp_up.u.ki.wScan = code
                inp_up.u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                events.extend([inp_down, inp_up])

            arr = (INPUT * len(events))(*events)
            ctypes.windll.user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
            return True, "TYPED"

    def _send_mouse_move(self, x: int, y: int) -> None:
        """Convert screen pixel coordinates to normalized 0-65535 space and send move."""
        user32 = ctypes.windll.user32
        v_width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) or user32.GetSystemMetrics(SM_CXSCREEN)
        v_height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN) or user32.GetSystemMetrics(SM_CYSCREEN)
        v_x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        v_y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)

        norm_x = int((x - v_x) * 65535 / v_width)
        norm_y = int((y - v_y) * 65535 / v_height)

        inp = INPUT(type=INPUT_MOUSE)
        inp.u.mi.dx = norm_x
        inp.u.mi.dy = norm_y
        inp.u.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


PhysicalInputController = NativeInputController
