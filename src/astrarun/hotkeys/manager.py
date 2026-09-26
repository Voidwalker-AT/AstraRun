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

    hotkey_pressed = Signal()
    registration_failed = Signal(str)

    def __init__(self, modifiers: list[str], key: str, hotkey_id: int = 101):
        super().__init__()
        self.modifiers = modifiers
        self.key = key
        self.hotkey_id = hotkey_id
        self._thread_id: int | None = None
        self.is_registered: bool = False
        self.registration_error: str | None = None

    def run(self) -> None:
        if sys.platform != "win32":
            logger.warning("Native Win32 hotkeys are not supported on non-Windows platforms.")
            self.registration_failed.emit("Non-Windows platform")
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()
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
            "Global hotkey registered: %s+%s (Thread ID=%d)",
            "+".join(self.modifiers), self.key, self._thread_id
        )

        msg = wintypes.MSG()
        # Message pump blocks cleanly in kernel until a message arrives
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                logger.debug("WM_HOTKEY received on thread %d", self._thread_id)
                self.hotkey_pressed.emit()

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
    """High-level hotkey manager facade."""

    hotkey_activated = Signal()
    error_occurred = Signal(str)

    def __init__(self, config_modifiers: list[str] | None = None, config_key: str = "Space"):
        super().__init__()
        self.modifiers = config_modifiers or ["Alt"]
        self.key = config_key
        self._thread: HotkeyListenerThread | None = None

    def start(self) -> None:
        """Start listening for the global hotkey."""
        self._thread = HotkeyListenerThread(self.modifiers, self.key)
        self._thread.hotkey_pressed.connect(self.hotkey_activated.emit)
        self._thread.registration_failed.connect(self.error_occurred.emit)
        self._thread.start()

    def stop(self) -> None:
        """Stop hotkey listening."""
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread = None
