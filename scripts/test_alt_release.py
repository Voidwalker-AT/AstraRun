"""Test what happens to LauncherWindow when physical/simulated Alt and Space are pressed and released.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from datetime import datetime

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication

from astrarun.app import AstraApplication
from astrarun.hotkeys.manager import HotkeyManager
from astrarun.ui.hud import FloatingTaskHUD
from astrarun.ui.launcher import LauncherWindow
from astrarun.ui.presentation import LauncherPresentationController


def main():
    qapp = QApplication(sys.argv)
    app = AstraApplication()
    hud = FloatingTaskHUD()
    launcher = LauncherWindow(app=app, hud=hud)
    hotkey = HotkeyManager(config_modifiers=["Alt"], config_key="Space")
    presentation = LauncherPresentationController(launcher=launcher, hud=hud, app=app, hotkey_manager=hotkey)

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S.%f")
        print(f"[{ts}] {msg} | vis={launcher.isVisible()} active={launcher.isActiveWindow()} focus={launcher.input_field.hasFocus()} anim={launcher._is_animating} has_act={launcher._has_been_active}", flush=True)

    # Instrument launcher events
    orig_change = launcher.changeEvent
    def changeEvent(ev):
        if ev.type() == QEvent.Type.ActivationChange:
            log(f"ActivationChange: isActiveWindow={launcher.isActiveWindow()}")
        orig_change(ev)
    launcher.changeEvent = changeEvent

    orig_key_press = launcher.keyPressEvent
    def keyPress(ev):
        log(f"keyPressEvent: key={ev.key()} text='{ev.text()}'")
        orig_key_press(ev)
    launcher.keyPressEvent = keyPress

    orig_key_rel = launcher.keyReleaseEvent
    def keyRelease(ev):
        log(f"keyReleaseEvent: key={ev.key()}")
        orig_key_rel(ev)
    launcher.keyReleaseEvent = keyRelease

    hotkey.hotkey_activated.connect(lambda hwnd: log(f"hotkey_activated! origin={hwnd}"))
    hotkey.hotkey_activated.connect(presentation.toggle_presentation)
    hotkey.start()

    log("Started. Presenting launcher now...")
    presentation.present()

    # Simulate releasing Alt key (VK_MENU = 0x12)
    def sim_alt_release():
        log("--- SIMULATING ALT KEY RELEASE (WM_KEYUP 0x12) ---")
        user32 = ctypes.windll.user32
        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

    # Also simulate focus loss
    def sim_focus_loss():
        log("--- SIMULATING TRANSIENT FOCUS LOSS ---")
        user32 = ctypes.windll.user32
        # Set foreground to desktop window
        h_desk = user32.GetDesktopWindow()
        user32.SetForegroundWindow(h_desk)

    QTimer.singleShot(250, sim_alt_release)
    QTimer.singleShot(500, sim_focus_loss)
    QTimer.singleShot(1500, qapp.quit)

    qapp.exec()
    hotkey.stop()


if __name__ == "__main__":
    main()
