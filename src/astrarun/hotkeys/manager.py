"""Win32 native global hotkey manager for AstraRun."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

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

# Virtual Key Codes
VK_MAP = {
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
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


class HotkeyListenerThread(QThread):
    """Dedicated background thread running the Win32 message pump for WM_HOTKEY."""

    hotkey_pressed = Signal(int)  # Emits origin_hwnd (int)
    registration_failed = Signal(str)

    def __init__(self, modifiers: list[str], key: str, hotkey_id: int = 101):
        super().__init__()
        self.modifiers = modifiers
        self.key = key
        self.hotkey_id = hotkey_id
        self._thread_id: int | None = None
        self.is_registered: bool = False
        self.registration_error: str | None = None
        self.trigger_count: int = 0
        self.last_trigger_timestamp: float | None = None
        self.last_origin_hwnd: int = 0

    def run(self) -> None:
        if sys.platform != "win32":
            logger.warning("Native Win32 hotkeys are not supported on non-Windows platforms.")
            self.registration_failed.emit("Non-Windows platform")
            return

        import time
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Configure ctypes 64-bit safety
        _setup_win32_prototypes(user32)

        # Ensure current thread is attached to the interactive desktop
        try:
            from astrarun.interaction.discovery import _ensure_desktop_attached
            _ensure_desktop_attached()
        except Exception as e:
            logger.debug("Desktop attachment check: %s", e)

        self._thread_id = kernel32.GetCurrentThreadId()

        # Prime the thread message queue before registering hotkey
        dummy_msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(dummy_msg), None, 0, 0, 0)

        mod_flag, vk = parse_hotkey(self.modifiers, self.key)

        res = user32.RegisterHotKey(None, self.hotkey_id, mod_flag, vk)
        if not res:
            err = ctypes.get_last_error()
            err_msg = (
                f"Failed to register hotkey {'+'.join(self.modifiers)}+{self.key}. "
                f"Win32 error: {err}. It may already be in use by another application."
            )
            logger.error(err_msg)
            self.registration_error = err_msg
            self.registration_failed.emit(err_msg)
            return

        self.is_registered = True
        logger.info(
            "Global hotkey registered: %s+%s (Thread ID=%d, Hotkey ID=%d)",
            "+".join(self.modifiers), self.key, self._thread_id, self.hotkey_id
        )

        msg = wintypes.MSG()
        # Message pump blocks cleanly in kernel until a message arrives
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                # Pre-capture origin window HWND immediately on the listener thread
                origin_hwnd = user32.GetForegroundWindow() or 0
                self.trigger_count += 1
                self.last_trigger_timestamp = time.time()
                self.last_origin_hwnd = origin_hwnd
                logger.debug(
                    "WM_HOTKEY received on thread %d (count=%d, origin_hwnd=%d)",
                    self._thread_id, self.trigger_count, origin_hwnd
                )
                self.hotkey_pressed.emit(origin_hwnd)

        # Clean unregistration
        user32.UnregisterHotKey(None, self.hotkey_id)
        self.is_registered = False
        logger.info("Global hotkey unregistered.")

    def stop(self) -> None:
        """Post WM_QUIT to terminate the Win32 message pump gracefully."""
        if self._thread_id and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self.wait(1500)


class HotkeyManager(QObject):
    """High-level hotkey manager facade with diagnostics and telemetry."""

    hotkey_activated = Signal(int)  # Emits origin_hwnd (int)
    error_occurred = Signal(str)

    def __init__(self, config_modifiers: list[str] | None = None, config_key: str = "Space", hotkey_id: int = 101):
        super().__init__()
        self.modifiers = config_modifiers or ["Alt"]
        self.key = config_key
        self.hotkey_id = hotkey_id
        self._thread: HotkeyListenerThread | None = None
        self._last_signal_delivered_timestamp: float | None = None
        self._last_origin_hwnd: int = 0
        self._trigger_count: int = 0

    def start(self) -> None:
        """Start listening for the global hotkey."""
        self._thread = HotkeyListenerThread(self.modifiers, self.key, self.hotkey_id)
        self._thread.hotkey_pressed.connect(self._on_thread_hotkey)
        self._thread.registration_failed.connect(self.error_occurred.emit)
        self._thread.start()

    def _on_thread_hotkey(self, origin_hwnd: int) -> None:
        """Handle hotkey event on main thread."""
        import time
        self._last_signal_delivered_timestamp = time.time()
        self._last_origin_hwnd = origin_hwnd
        self._trigger_count += 1
        self.hotkey_activated.emit(origin_hwnd)

    def stop(self) -> None:
        """Stop hotkey listening."""
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread = None

    def simulate_hotkey(self, origin_hwnd: int = 0) -> None:
        """Simulate a hotkey activation event (for testing and programmatic triggers)."""
        import time
        self._last_signal_delivered_timestamp = time.time()
        self._last_origin_hwnd = origin_hwnd
        self._trigger_count += 1
        self.hotkey_activated.emit(origin_hwnd)

    def get_diagnostics(self) -> dict[str, Any]:
        """Return structured runtime telemetry for diagnostics view."""
        is_reg = self._thread.is_registered if self._thread else False
        reg_err = self._thread.registration_error if self._thread else None
        thread_id = self._thread._thread_id if self._thread else None
        last_trig = self._thread.last_trigger_timestamp if self._thread else None

        return {
            "is_registered": is_reg,
            "modifiers": list(self.modifiers),
            "key": self.key,
            "hotkey_id": self.hotkey_id,
            "thread_id": thread_id,
            "trigger_count": self._trigger_count,
            "last_trigger_timestamp": last_trig,
            "last_signal_delivered_timestamp": self._last_signal_delivered_timestamp,
            "last_origin_hwnd": self._last_origin_hwnd,
            "last_error": reg_err,
        }
