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

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
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

    try:
        from astrarun.windows.discovery import _ensure_desktop_attached
        _ensure_desktop_attached()
    except Exception:
        pass

    # Constants
    SW_SHOW = 5
    SW_RESTORE = 9
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_SHOWWINDOW = 0x0040

    try:
        if not user32.IsWindow(hwnd):
            return False

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)

        cur_thread = kernel32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)

        attached_fg = False
        attached_target = False
        if fg_thread and fg_thread != cur_thread:
            attached_fg = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))
        if target_thread and target_thread != cur_thread:
            attached_target = bool(user32.AttachThreadInput(cur_thread, target_thread, True))

        user32.AllowSetForegroundWindow(-1)
        res = user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.SetFocus(hwnd)

        if not res:
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SetFocus(hwnd)

        if attached_fg:
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        if attached_target:
            user32.AttachThreadInput(cur_thread, target_thread, False)

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
        self.launcher._last_origin_hwnd = self._last_origin_hwnd
        self.launcher.present_animated(geom, target_screen=target_screen)

        # 5. Enforce foreground activation
        if sys.platform == "win32":
            force_foreground_activation(int(self.launcher.winId()))

        # 6. Ensure input focus
        self.launcher.input_field.setFocus()
        self.presentation_finished.emit()

        # 7. Verification probes (Section 7: immediately, +25ms, +50ms, +100ms, +200ms, +400ms)
        self._schedule_activation_probes()

    def _schedule_activation_probes(self) -> None:
        """Schedule verification probes to detect transient foreground returns."""
        for delay in (0, 25, 50, 100, 200, 400):
            if delay == 0:
                self._record_probe(0)
            else:
                QTimer.singleShot(delay, lambda d=delay: self._record_probe(d))

    def _record_probe(self, delay_ms: int) -> None:
        if sys.platform != "win32":
            return
        try:
            user32 = ctypes.windll.user32
            fg_hwnd = user32.GetForegroundWindow() or 0
            win_id = int(self.launcher.winId()) if self.launcher else 0
            qapp = QGuiApplication.instance()
            act_win = qapp.activeWindow() if hasattr(qapp, "activeWindow") else None
            is_act = self.launcher.isActiveWindow() if self.launcher else False
            has_focus = self.launcher.input_field.hasFocus() if self.launcher else False
            msg = (
                f"[PROBE +{delay_ms:>3}ms] fg_hwnd={fg_hwnd:<8} (match={fg_hwnd == win_id}) "
                f"activeWin={act_win is not None} is_active={is_act} input_focus={has_focus}"
            )
            logger.debug(msg)
            if getattr(self.launcher, "launcher_debug", False):
                print(msg, flush=True)

            if delay_ms >= 400:
                try:
                    import os
                    from astrarun.ui.attestation import attest_window_visibility
                    attestation = attest_window_visibility(win_id, expected_pid=os.getpid())
                    if attestation["is_visible"]:
                        logger.info("[LAUNCHER_VISIBLE] hwnd=%d facts=%s", win_id, attestation["facts"])
                    else:
                        logger.warning("[LAUNCHER_VISIBILITY_FAILED] hwnd=%d reasons=%s", win_id, attestation["failure_reasons"])
                except Exception as att_err:
                    logger.debug("Attestation error: %s", att_err)
        except Exception as e:
            logger.debug("Probe error at +%dms: %s", delay_ms, e)

    def dismiss(self, reason: str = "presentation_controller") -> None:
        """Dismiss the command bar smoothly."""
        logger.debug("Dismissing launcher via presentation controller (reason=%s).", reason)
        self.launcher.dismiss_animated(reason=reason)
        self.dismissal_finished.emit()

    def toggle_presentation(self, origin_hwnd: int | None = None) -> None:
        """Toggle launcher visibility based on explicit state machine."""
        from astrarun.ui.launcher import LauncherState
        if hasattr(self.launcher, "state"):
            if self.launcher.state == LauncherState.INTERACTIVE and self.launcher.isVisible():
                self.dismiss(reason="hotkey_toggle")
            elif self.launcher.state in (LauncherState.ENTERING, LauncherState.ACTIVATING):
                logger.debug("Hotkey received during presentation state; ignoring duplicate toggle.")
            else:
                self.present(origin_hwnd=origin_hwnd)
        else:
            if self.launcher.isVisible() and self.launcher.isActiveWindow():
                self.dismiss(reason="hotkey_toggle")
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
