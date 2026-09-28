"""Diagnostic script to instrument and reproduce the exact lifecycle sequence of LauncherWindow.

Logs all lifecycle events with high-resolution timestamps, HWNDs, focus states, and dismiss reasons.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from datetime import datetime
from ctypes import wintypes

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication

from astrarun.app import AstraApplication
from astrarun.core.logging import get_logger
from astrarun.hotkeys.manager import HotkeyManager, WM_HOTKEY
from astrarun.ui.hud import FloatingTaskHUD, TaskHUDController
from astrarun.ui.launcher import LauncherWindow
from astrarun.ui.presentation import LauncherPresentationController, force_foreground_activation

logger = get_logger("astrarun.reproduce")


def log_lifecycle(event_name: str, launcher: LauncherWindow, reason: str = "", extra: str = ""):
    ts = datetime.now().strftime("%H:%M:%S.%f")
    fg_hwnd = ctypes.windll.user32.GetForegroundWindow() if sys.platform == "win32" else 0
    origin_hwnd = getattr(launcher, "_last_origin_hwnd", 0)
    visible = launcher.isVisible()
    active = launcher.isActiveWindow()
    input_focus = launcher.input_field.hasFocus()
    is_anim = getattr(launcher, "_is_animating", False)
    has_active = getattr(launcher, "_has_been_active", False)
    
    parts = [
        f"{ts}",
        f"{event_name:<24}",
        f"vis={visible}",
        f"active={active}",
        f"inp_focus={input_focus}",
        f"fg_hwnd={fg_hwnd}",
        f"origin={origin_hwnd}",
        f"anim={is_anim}",
        f"has_act={has_active}",
    ]
    if reason:
        parts.append(f"reason='{reason}'")
    if extra:
        parts.append(f"extra='{extra}'")
    print(" | ".join(parts), flush=True)


class InstrumentedLauncherWindow(LauncherWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_origin_hwnd = 0

    def showEvent(self, event):
        log_lifecycle("SHOW_EVENT", self)
        super().showEvent(event)

    def hideEvent(self, event):
        log_lifecycle("HIDE_EVENT", self)
        super().hideEvent(event)

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.ActivationChange:
            is_act = self.isActiveWindow()
            log_lifecycle("ACTIVATION_CHANGE", self, extra=f"isActiveWindow={is_act}")
            if is_act:
                log_lifecycle("WINDOW_ACTIVATE", self)
            else:
                log_lifecycle("WINDOW_DEACTIVATE", self)
        super().changeEvent(event)

    def focusInEvent(self, event):
        log_lifecycle("FOCUS_IN", self)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        log_lifecycle("FOCUS_OUT", self)
        super().focusOutEvent(event)

    def present_animated(self, target_geometry, target_screen=None):
        log_lifecycle("SHOW_CALLED", self)
        super().present_animated(target_geometry, target_screen)
        log_lifecycle("ANIMATION_STARTED", self)

    def dismiss_animated(self):
        log_lifecycle("DISMISS_REQUESTED", self, reason="dismiss_animated")
        super().dismiss_animated()

    def dismiss(self):
        log_lifecycle("DISMISS_REQUESTED", self, reason="dismiss")
        super().dismiss()

    def _on_animation_finished(self):
        super()._on_animation_finished()
        log_lifecycle("ANIMATION_FINISHED", self)


def main():
    qapp = QApplication(sys.argv)
    app = AstraApplication()
    hud = FloatingTaskHUD()
    hud_controller = TaskHUDController(hud, app.task_event_bus)
    
    launcher = InstrumentedLauncherWindow(app=app, hud=hud)
    hotkey = HotkeyManager(config_modifiers=["Alt"], config_key="Space")
    presentation = LauncherPresentationController(launcher=launcher, hud=hud, app=app, hotkey_manager=hotkey)

    def on_hotkey(origin_hwnd: int):
        launcher._last_origin_hwnd = origin_hwnd
        log_lifecycle("WM_HOTKEY_RECEIVED", launcher, extra=f"origin={origin_hwnd}")
        log_lifecycle("ORIGIN_CAPTURED", launcher, extra=f"origin={origin_hwnd}")
        log_lifecycle("PRESENT_REQUESTED", launcher)
        presentation.toggle_presentation(origin_hwnd)

    hotkey.hotkey_activated.connect(on_hotkey)
    hotkey.start()
    
    print("\n=== INSTRUMENTATION READY ===", flush=True)
    print("Simulating/waiting for Alt+Space or testing probe in 500ms...\n", flush=True)

    # Let's test triggering presentation as if Alt+Space fired
    def trigger_test():
        user32 = ctypes.windll.user32
        curr_fg = user32.GetForegroundWindow()
        print(f"\n--- TRIGGER TEST: current foreground HWND={curr_fg} ---", flush=True)
        on_hotkey(curr_fg)

        # Check foreground at +25ms, +50ms, +100ms, +200ms, +400ms
        for delay in (25, 50, 100, 200, 400):
            QTimer.singleShot(delay, lambda d=delay: log_lifecycle(f"CHECK_+{d}ms", launcher))

        # Check at 2000ms (2 seconds)
        QTimer.singleShot(2000, lambda: log_lifecycle("CHECK_+2000ms", launcher))
        
        # Stop after 3 seconds
        QTimer.singleShot(3000, qapp.quit)

    QTimer.singleShot(500, trigger_test)

    qapp.exec()
    hotkey.stop()


if __name__ == "__main__":
    main()
