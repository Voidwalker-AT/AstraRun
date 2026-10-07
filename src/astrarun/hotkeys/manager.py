"""Win32 native global hotkey manager for AstraRun.

Provides robust global hotkey registration, conflict detection, telemetry logging,
and live rebinding via Win32 RegisterHotKey and Qt native event filtering.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from typing import Any, Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, QThread, Signal
from PySide6.QtWidgets import QApplication, QWidget

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.hotkeys")

# Win32 Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# Common Win32 Error Codes
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
ERROR_HOTKEY_NOT_REGISTERED = 1419
ERROR_ACCESS_DENIED = 5

WIN32_ERROR_MESSAGES = {
    1409: "Hotkey is already registered by another application (e.g. PowerToys, Windows Shell, or another launcher).",
    1419: "Hotkey is not registered.",
    5: "Access denied registering hotkey.",
}

# Virtual Key Codes
VK_MAP: dict[str, int] = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "pause": 0x13,
    "printscreen": 0x2C,
    "\\": 0xDC,       # VK_OEM_5
    "backslash": 0xDC,
    "/": 0xBF,        # VK_OEM_2
    "slash": 0xBF,
    "`": 0xC0,        # VK_OEM_3
    "grave": 0xC0,
    "backquote": 0xC0,
    "-": 0xBD,        # VK_OEM_MINUS
    "=": 0xBB,        # VK_OEM_PLUS
    "[": 0xDB,        # VK_OEM_4
    "]": 0xDD,        # VK_OEM_6
    ";": 0xBA,        # VK_OEM_1
    "'": 0xDE,        # VK_OEM_7
}
for i in range(1, 13):
    VK_MAP[f"f{i}"] = 0x70 + (i - 1)


def _setup_win32_prototypes(user32: Any) -> None:
    """Explicitly configure 64-bit argument and return types for user32 calls."""
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL

    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL

    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL

    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL

    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL

    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL

    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND


def parse_hotkey(modifiers: list[str], key: str) -> tuple[int, int]:
    """Parse human-readable modifier list and key into Win32 flags and VK code."""
    mod_flag = MOD_NOREPEAT
    for m in modifiers:
        norm = m.strip().lower()
        if norm in ("alt", "menu"):
            mod_flag |= MOD_ALT
        elif norm in ("ctrl", "control"):
            mod_flag |= MOD_CONTROL
        elif norm == "shift":
            mod_flag |= MOD_SHIFT
        elif norm in ("win", "windows", "super"):
            mod_flag |= MOD_WIN

    norm_key = key.strip().lower()
    if norm_key in VK_MAP:
        vk = VK_MAP[norm_key]
    elif len(norm_key) == 1:
        vk = ord(norm_key.upper())
    else:
        logger.warning("Unrecognized key name '%s'; defaulting to Space", key)
        vk = VK_MAP["space"]

    return mod_flag, vk


def format_shortcut_name(modifiers: list[str], key: str) -> str:
    """Format human-readable shortcut string (e.g. 'Alt+Space', 'Ctrl+Space')."""
    mods = [m.title() if m.lower() != "ctrl" else "Ctrl" for m in modifiers]
    k = key.upper() if len(key) == 1 else key.title()
    return "+".join(mods + [k])


class _QtNativeHotkeyFilter(QAbstractNativeEventFilter):
    """Intercepts WM_HOTKEY in the main Qt application event loop."""

    def __init__(self, target_hwnd: int, on_hotkey_callback: Callable[[int, int], None]):
        super().__init__()
        self.target_hwnd = target_hwnd
        self.callback = on_hotkey_callback

    def nativeEventFilter(self, event_type: Any, message: Any) -> tuple[bool, int]:
        if event_type == b"windows_generic_MSG" and sys.platform == "win32":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    hotkey_id = int(msg.wParam)
                    lparam = int(msg.lParam)
                    self.callback(hotkey_id, lparam)
                    return True, 0
            except Exception as e:
                logger.debug("Error in nativeEventFilter for hotkey: %s", e)
        return False, 0


class HotkeyManager(QObject):
    """High-level hotkey manager facade with diagnostics, conflict detection, and live rebinding."""

    hotkey_activated = Signal(int)  # Emits origin_hwnd (int)
    hotkey_registered = Signal(str)  # Emits formatted shortcut string
    hotkey_conflict = Signal(str, int, str)  # Emits (shortcut, error_code, error_message)
    error_occurred = Signal(str)  # Backward compatibility string signal

    def __init__(
        self,
        config_modifiers: list[str] | None = None,
        config_key: str = "Space",
        hotkey_id: int = 101,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.modifiers = list(config_modifiers or ["Alt"])
        self.key = config_key
        self.hotkey_id = hotkey_id

        self.is_registered: bool = False
        self.last_error_code: int = 0
        self.last_error_message: str | None = None

        self._trigger_count: int = 0
        self._last_trigger_timestamp: float | None = None
        self._last_origin_hwnd: int = 0

        self._native_filter: _QtNativeHotkeyFilter | None = None
        self._dedicated_widget: QWidget | None = None
        self._hwnd: int = 0

        # Lazy DLL handle with last_error enabled
        self._user32 = None
        if sys.platform == "win32":
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            _setup_win32_prototypes(self._user32)

    @property
    def shortcut_name(self) -> str:
        """Formatted name of current shortcut."""
        return format_shortcut_name(self.modifiers, self.key)

    def _ensure_hwnd(self) -> int:
        """Create or return a persistent dedicated hidden QWidget HWND on the main thread."""
        if self._hwnd and self._dedicated_widget:
            return self._hwnd

        qapp = QApplication.instance()
        if qapp is not None:
            self._dedicated_widget = QWidget()
            # Calling winId forces native window handle creation
            self._hwnd = int(self._dedicated_widget.winId())
            self._dedicated_widget.hide()
            logger.debug("Dedicated hidden hotkey QWidget HWND initialized: %d", self._hwnd)
            return self._hwnd

        return 0

    def start(self) -> bool:
        """Start listening for the configured global hotkey."""
        if sys.platform != "win32":
            logger.warning("Native Win32 hotkeys are not supported on non-Windows platforms.")
            self.error_occurred.emit("Non-Windows platform")
            return False

        return self._register_current()

    def _register_current(self) -> bool:
        """Attempt to register the current modifier and key combination."""
        if self._user32 is None:
            return False

        shortcut = self.shortcut_name
        logger.info("[HOTKEY_REGISTER_ATTEMPT] modifiers=%s, key=%s ('%s')", self.modifiers, self.key, shortcut)

        hwnd = self._ensure_hwnd()
        target_hwnd = wintypes.HWND(hwnd) if hwnd else None

        mod_flag, vk = parse_hotkey(self.modifiers, self.key)

        # Ensure Qt native event filter is installed if running in GUI application
        qapp = QApplication.instance()
        if qapp is not None and self._native_filter is None:
            self._native_filter = _QtNativeHotkeyFilter(hwnd, self._on_native_hotkey)
            qapp.installNativeEventFilter(self._native_filter)

        # Invoke Win32 RegisterHotKey
        res = self._user32.RegisterHotKey(target_hwnd, self.hotkey_id, mod_flag, vk)
        if not res:
            err = ctypes.get_last_error()
            self.is_registered = False
            self.last_error_code = err
            err_desc = WIN32_ERROR_MESSAGES.get(err, f"Win32 error code {err}")
            self.last_error_message = f"Failed to register hotkey {shortcut}. {err_desc}"

            logger.error(
                "[HOTKEY_REGISTRATION_FAILED] modifiers=%s, key=%s, code=%d (%s)",
                self.modifiers, self.key, err, err_desc
            )
            self.hotkey_conflict.emit(shortcut, err, err_desc)
            self.error_occurred.emit(self.last_error_message)
            return False

        self.is_registered = True
        self.last_error_code = 0
        self.last_error_message = None

        logger.info(
            "[HOTKEY_REGISTERED] modifiers=%s, key=%s (Hotkey ID=%d, HWND=%s)",
            self.modifiers, self.key, self.hotkey_id, hwnd or "ThreadQueue"
        )
        self.hotkey_registered.emit(shortcut)
        return True

    def stop(self) -> None:
        """Unregister the global hotkey."""
        if not self.is_registered or self._user32 is None:
            return

        target_hwnd = wintypes.HWND(self._hwnd) if self._hwnd else None
        self._user32.UnregisterHotKey(target_hwnd, self.hotkey_id)
        self.is_registered = False
        logger.info("[HOTKEY_UNREGISTERED] %s (Hotkey ID=%d)", self.shortcut_name, self.hotkey_id)

    def test_registration(self, modifiers: list[str], key: str) -> tuple[bool, int, str]:
        """
        Test whether a modifier+key combination is available on this system.
        Temporarily registers and immediately unregisters using a dedicated test ID.
        Returns: (is_available, error_code, error_message)
        """
        if sys.platform != "win32" or self._user32 is None:
            return False, -1, "Non-Windows platform"

        test_id = 999
        hwnd = self._ensure_hwnd()
        target_hwnd = wintypes.HWND(hwnd) if hwnd else None
        mod_flag, vk = parse_hotkey(modifiers, key)

        res = self._user32.RegisterHotKey(target_hwnd, test_id, mod_flag, vk)
        if not res:
            err = ctypes.get_last_error()
            desc = WIN32_ERROR_MESSAGES.get(err, f"Win32 error {err}")
            return False, err, desc

        # Immediately release test registration
        self._user32.UnregisterHotKey(target_hwnd, test_id)
        return True, 0, "Available"

    def rebind(self, modifiers: list[str], key: str) -> tuple[bool, int, str]:
        """
        Dynamically unregister existing hotkey and rebind to a new combination.
        If registration fails, attempts to restore the previous hotkey.
        Returns: (success, error_code, error_message)
        """
        old_mods = list(self.modifiers)
        old_key = self.key

        # 1. Unregister existing
        self.stop()

        # 2. Update and attempt registration
        self.modifiers = list(modifiers)
        self.key = key
        success = self._register_current()

        if success:
            logger.info("[HOTKEY_REBOUND] Successfully changed hotkey to %s", self.shortcut_name)
            return True, 0, "Success"

        # Failed: attempt to restore previous hotkey
        err_code = self.last_error_code
        err_msg = self.last_error_message or "Registration failed"
        logger.warning("[HOTKEY_REBIND_FAILED] Reverting to previous hotkey %s", format_shortcut_name(old_mods, old_key))

        self.modifiers = old_mods
        self.key = old_key
        self._register_current()

        return False, err_code, err_msg

    def _on_native_hotkey(self, hotkey_id: int, lparam: int) -> None:
        """Handle WM_HOTKEY message dispatched from native event filter."""
        if hotkey_id != self.hotkey_id:
            return

        origin_hwnd = 0
        if self._user32 is not None:
            try:
                origin_hwnd = int(self._user32.GetForegroundWindow() or 0)
            except Exception as e:
                logger.debug("Failed to get foreground window: %s", e)

        self._trigger_count += 1
        self._last_trigger_timestamp = time.time()
        self._last_origin_hwnd = origin_hwnd

        logger.info(
            "[HOTKEY_TRIGGERED] id=%d, origin_hwnd=%d (count=%d)",
            hotkey_id, origin_hwnd, self._trigger_count
        )
        self.hotkey_activated.emit(origin_hwnd)

    def simulate_hotkey(self, origin_hwnd: int = 0) -> None:
        """Simulate a hotkey activation event (for testing and programmatic triggers)."""
        self._trigger_count += 1
        self._last_trigger_timestamp = time.time()
        self._last_origin_hwnd = origin_hwnd
        logger.info("[HOTKEY_TRIGGERED] (simulated) origin_hwnd=%d", origin_hwnd)
        self.hotkey_activated.emit(origin_hwnd)

    def get_diagnostics(self) -> dict[str, Any]:
        """Return structured runtime telemetry for diagnostics view."""
        return {
            "is_registered": self.is_registered,
            "modifiers": list(self.modifiers),
            "key": self.key,
            "shortcut": self.shortcut_name,
            "hotkey_id": self.hotkey_id,
            "hwnd": self._hwnd,
            "trigger_count": self._trigger_count,
            "last_trigger_timestamp": self._last_trigger_timestamp,
            "last_origin_hwnd": self._last_origin_hwnd,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
        }
