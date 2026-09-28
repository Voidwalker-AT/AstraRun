"""LauncherPresentationController: Canonical orchestrator for AstraRun UI presentation.

Coordinates the top-center floating Command Bar (LauncherWindow), the decoupled
Floating Task HUD, Win32 foreground activation, monitor geometry resolution,
and telemetry diagnostics.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from typing import Any, Optional

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QGuiApplication, QScreen

from astrarun.core.logging import get_logger
from astrarun.ui.hud import FloatingTaskHUD
from astrarun.ui.positioning import compute_top_center_launcher_position, get_screen_for_hwnd
from astrarun.windows.policy import is_astrarun_window

logger = get_logger("astrarun.ui.presentation")


def force_foreground_activation(hwnd: int) -> bool:
    """
    Safely bring window to the absolute foreground on Windows 10/11,
    bypassing LockSetForegroundWindow restrictions via thread input attachment.
    """
    if sys.platform != "win32" or not hwnd:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Constants
    SW_SHOW = 5
    HWND_TOPMOST = -1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_SHOWWINDOW = 0x0040

    try:
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)

        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd and fg_hwnd != hwnd:
            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
            cur_thread = kernel32.GetCurrentThreadId()
            if fg_thread != cur_thread:
                user32.AttachThreadInput(cur_thread, fg_thread, True)
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                user32.AttachThreadInput(cur_thread, fg_thread, False)
            else:
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        return True
    except Exception as err:
        logger.debug("Error during force_foreground_activation: %s", err)
        return False


class LauncherPresentationController(QObject):
    """
    Canonical presentation controller shared across Global Hotkey (Alt+Space),
    System Tray activations, and headless test harnesses.
    """

    presentation_started = Signal(int)    # origin_hwnd
    presentation_finished = Signal()
    dismissal_finished = Signal()

    def __init__(
        self,
        launcher: Any,
        hud: Optional[FloatingTaskHUD] = None,
        app: Any = None,
        hotkey_manager: Any = None,
    ):
        super().__init__()
        self.launcher = launcher
        self.hud = hud
        self.app = app
        self.hotkey_manager = hotkey_manager

        # Telemetry & Diagnostic state
        self._last_origin_hwnd: int = 0
        self._last_origin_title: str = ""
        self._last_target_monitor: str = ""
        self._last_presentation_geometry: dict[str, int] = {}
        self._presentation_count: int = 0
        self._last_presentation_timestamp: float | None = None

    def present(self, origin_hwnd: int | None = None) -> None:
        """
        Bring the floating command bar to the top-center of the monitor hosting
        the origin window, focusing the search input immediately.
        """
        t0 = time.time()
        self._presentation_count += 1
        self._last_presentation_timestamp = t0

        # 1. Resolve origin window HWND and capture context
        active_hwnd = origin_hwnd
        if not active_hwnd and sys.platform == "win32":
            user32 = ctypes.windll.user32
            active_hwnd = user32.GetForegroundWindow() or 0

        # Don't capture our own launcher or HUD as the origin window
        if active_hwnd and is_astrarun_window(active_hwnd):
            active_hwnd = 0

        if self.app is not None:
            origin_entity = self.app.capture_origin_window()
            if origin_entity:
                active_hwnd = origin_entity.hwnd
                self._last_origin_title = origin_entity.title
            else:
                self._last_origin_title = ""

        self._last_origin_hwnd = active_hwnd or 0

        # 2. Determine target screen based on origin HWND or cursor
        target_screen = get_screen_for_hwnd(active_hwnd)
        if target_screen:
            self._last_target_monitor = target_screen.name()
        else:
            self._last_target_monitor = "Default"

        # 3. Compute top-center geometry on target screen
        pos, avail = compute_top_center_launcher_position(
            self.launcher.launcher_width,
            self.launcher.launcher_height,
            target_screen=target_screen,
            origin_hwnd=active_hwnd,
        )
        geom = QRect(pos.x(), pos.y(), self.launcher.launcher_width, self.launcher.launcher_height)
        self._last_presentation_geometry = {
            "x": geom.x(),
            "y": geom.y(),
            "width": geom.width(),
            "height": geom.height(),
        }

        logger.info(
            "Presenting launcher: Monitor '%s', Origin HWND %d ('%s'), Pos (%d, %d)",
            self._last_target_monitor, self._last_origin_hwnd, self._last_origin_title, pos.x(), pos.y()
        )

        # 4. Trigger animated presentation on the launcher window
        self.presentation_started.emit(self._last_origin_hwnd)
        self.launcher.present_animated(geom, target_screen=target_screen)

        # 5. Enforce foreground activation
        if sys.platform == "win32":
            force_foreground_activation(int(self.launcher.winId()))

        # 6. Ensure input focus
        self.launcher.input_field.setFocus()
        self.presentation_finished.emit()

    def dismiss(self) -> None:
        """Dismiss the command bar smoothly."""
        logger.debug("Dismissing launcher via presentation controller.")
        self.launcher.dismiss_animated()
        self.dismissal_finished.emit()

    def toggle_presentation(self, origin_hwnd: int | None = None) -> None:
        """Toggle launcher visibility based on active and visible state."""
        if self.launcher.isVisible() and self.launcher.isActiveWindow():
            self.dismiss()
        else:
            self.present(origin_hwnd=origin_hwnd)

    def get_diagnostics(self) -> dict[str, Any]:
        """Aggregate diagnostic state across hotkey, launcher, and HUD subsystems."""
        hotkey_diag = self.hotkey_manager.get_diagnostics() if self.hotkey_manager else {}
        hud_diag = self.hud.get_state() if self.hud else {}

        return {
            "hotkey": hotkey_diag,
            "presentation": {
                "presentation_count": self._presentation_count,
                "last_presentation_timestamp": self._last_presentation_timestamp,
                "last_origin_hwnd": self._last_origin_hwnd,
                "last_origin_title": self._last_origin_title,
                "last_target_monitor": self._last_target_monitor,
                "last_presentation_geometry": self._last_presentation_geometry,
            },
            "launcher": {
                "visible": self.launcher.isVisible(),
                "active": self.launcher.isActiveWindow(),
                "geometry": {
                    "x": self.launcher.x(),
                    "y": self.launcher.y(),
                    "width": self.launcher.width(),
                    "height": self.launcher.height(),
                },
            },
            "hud": hud_diag,
        }
