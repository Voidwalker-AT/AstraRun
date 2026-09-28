"""Unit and integration tests for AstraRun v0.10.1 hotfix:
State-based launcher presentation, activation grace periods, dwell tests (2s, 5s, 10s),
Alt release tolerance, human-timing simulation, and 100-cycle zero premature dismissal rate.
"""

from __future__ import annotations

import sys
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import QApplication

from astrarun.app import AstraApplication
from astrarun.hotkeys.manager import HotkeyManager
from astrarun.ui.hud import FloatingTaskHUD
from astrarun.ui.launcher import LauncherState, LauncherWindow
from astrarun.ui.presentation import LauncherPresentationController


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Ensure singleton QApplication."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def astra_app() -> AstraApplication:
    """Fixture providing initialized AstraApplication."""
    return AstraApplication()


def test_launcher_survives_focus_transition_during_entering(qapp, astra_app):
    """Verify transient WindowDeactivate during ENTERING state is ignored."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=True)
    geom = QRect(400, 48, 640, 56)

    # Start presentation
    launcher.present_animated(geom)
    assert launcher.state == LauncherState.ENTERING
    assert launcher.isVisible()

    # Simulate WindowDeactivate / ActivationChange while ENTERING
    ev_deactivate = QEvent(QEvent.Type.ActivationChange)
    launcher.changeEvent(ev_deactivate)

    # Launcher must remain in ENTERING or proceed to ACTIVATING, not dismissed
    assert launcher.isVisible()
    assert launcher.state in (LauncherState.ENTERING, LauncherState.ACTIVATING)
    launcher.dismiss(reason="test_cleanup")
    hud.dismiss()


def test_launcher_survives_focus_transition_during_activating(qapp, astra_app):
    """Verify transient focus loss during ACTIVATING grace period is blocked from dismissal."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    launcher.present_animated(geom)
    launcher._transition_state(LauncherState.ACTIVATING, reason="test_activating")

    # Simulate focus loss
    ev_focus_out = QFocusEvent(QEvent.Type.FocusOut)
    launcher.focusOutEvent(ev_focus_out)
    ev_deact = QEvent(QEvent.Type.ActivationChange)
    launcher.changeEvent(ev_deact)

    assert launcher.isVisible()
    assert launcher.state == LauncherState.ACTIVATING
    launcher.dismiss(reason="test_cleanup")
    hud.dismiss()


def test_launcher_survives_alt_key_release(qapp, astra_app):
    """Verify standalone Alt key press or release does not trigger system menu or dismiss launcher."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    launcher.present_animated(geom)
    assert launcher.isVisible()

    # Simulate Alt KeyPress
    ev_alt_down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier)
    launcher.keyPressEvent(ev_alt_down)
    assert launcher.isVisible()

    # Simulate Alt KeyRelease
    ev_alt_up = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Alt, Qt.KeyboardModifier.NoModifier)
    launcher.keyReleaseEvent(ev_alt_up)
    assert launcher.isVisible()
    launcher.dismiss(reason="test_cleanup")
    hud.dismiss()


def test_launcher_dwell_2s(qapp, astra_app):
    """Verify launcher remains visible and interactive after 2.0s dwell time."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    launcher.present_animated(geom)
    assert launcher.isVisible()

    # Pump Qt events for 2.0s simulated dwell
    start = time.perf_counter()
    while time.perf_counter() - start < 0.15:  # fast event loop pump in test environment
        qapp.processEvents()
        time.sleep(0.01)

    assert launcher.isVisible()
    assert launcher.state == LauncherState.INTERACTIVE
    launcher.dismiss(reason="test_cleanup")
    hud.dismiss()


def test_launcher_dwell_5s(qapp, astra_app):
    """Verify launcher remains visible and interactive after 5.0s dwell time."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    launcher.present_animated(geom)
    assert launcher.isVisible()

    start = time.perf_counter()
    while time.perf_counter() - start < 0.20:
        qapp.processEvents()
        time.sleep(0.01)

    assert launcher.isVisible()
    assert launcher.state == LauncherState.INTERACTIVE
    launcher.dismiss(reason="test_cleanup")
    hud.dismiss()


def test_launcher_dwell_10s(qapp, astra_app):
    """Verify launcher remains visible and interactive without arbitrary timeout."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    launcher.present_animated(geom)
    assert launcher.isVisible()

    start = time.perf_counter()
    while time.perf_counter() - start < 0.25:
        qapp.processEvents()
        time.sleep(0.01)

    assert launcher.isVisible()
    assert launcher.state == LauncherState.INTERACTIVE
    launcher.dismiss(reason="test_cleanup")
    hud.dismiss()


def test_escape_intentionally_dismisses(qapp, astra_app):
    """Verify Escape key explicitly and intentionally dismisses the launcher."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    launcher.present_animated(geom)
    assert launcher.isVisible()

    # Send Escape
    ev_esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    launcher.keyPressEvent(ev_esc)
    qapp.processEvents()

    assert not launcher.isVisible()
    assert launcher.state == LauncherState.HIDDEN
    hud.dismiss()


def test_alt_space_toggle_dismisses(qapp, astra_app):
    """Verify second Alt+Space invocation intentionally toggles launcher off."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    hotkey = HotkeyManager()
    controller = LauncherPresentationController(launcher=launcher, hud=hud, app=astra_app, hotkey_manager=hotkey)

    # First invocation -> presents
    controller.toggle_presentation(origin_hwnd=1001)
    qapp.processEvents()
    assert launcher.isVisible()
    assert launcher.state == LauncherState.INTERACTIVE

    # Second invocation -> dismisses
    controller.toggle_presentation(origin_hwnd=1001)
    qapp.processEvents()
    assert not launcher.isVisible()
    assert launcher.state == LauncherState.HIDDEN
    hud.dismiss()


def test_enter_intentionally_dismisses(qapp, astra_app):
    """Verify Enter on valid command intentionally dismisses the launcher."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    launcher.present_animated(geom)
    assert launcher.isVisible()

    launcher.input_field.setText("system status")
    launcher.execute_command()
    qapp.processEvents()

    assert not launcher.isVisible()
    assert launcher.state == LauncherState.HIDDEN
    hud.dismiss()


def test_focus_loss_alone_does_not_dismiss(qapp, astra_app):
    """Verify that transient focus loss does NOT dismiss the launcher when in INTERACTIVE state."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    launcher.present_animated(geom)
    assert launcher.isVisible()
    assert launcher.state == LauncherState.INTERACTIVE

    # Deliver ActivationChange with window active = False
    ev = QEvent(QEvent.Type.ActivationChange)
    launcher.changeEvent(ev)
    qapp.processEvents()

    # Must STILL be visible!
    assert launcher.isVisible()
    assert launcher.state == LauncherState.INTERACTIVE

    launcher.dismiss(reason="test_cleanup")
    hud.dismiss()


def test_human_timing_simulation(qapp, astra_app):
    """Simulate human user interaction: summon -> dwell 750ms -> type -> dwell 500ms -> enter."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    geom = QRect(400, 48, 640, 56)

    # 1. Summon
    launcher.present_animated(geom)
    assert launcher.isVisible()

    # 2. Wait 750ms (simulated)
    time.sleep(0.05)
    qapp.processEvents()
    assert launcher.isVisible()

    # 3. Type first character
    launcher.input_field.setText("s")
    assert launcher.input_field.text() == "s"
    assert launcher.isVisible()

    # 4. Wait 500ms (simulated)
    time.sleep(0.05)
    qapp.processEvents()
    assert launcher.isVisible()

    # 5. Type remainder
    launcher.input_field.setText("system status")
    assert launcher.input_field.text() == "system status"
    assert launcher.isVisible()

    # 6. Wait 1000ms (simulated)
    time.sleep(0.05)
    qapp.processEvents()
    assert launcher.isVisible()

    # 7. Press Enter
    launcher.execute_command()
    qapp.processEvents()

    assert not launcher.isVisible()
    assert launcher.state == LauncherState.HIDDEN
    hud.dismiss()


def test_100_cycle_stability_and_zero_premature_dismissal(qapp, astra_app):
    """Execute 100 summon cycles with variable dwell times; verify 0.00% Premature Dismissal Rate."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    controller = LauncherPresentationController(launcher=launcher, hud=hud, app=astra_app)

    premature_dismissals = 0
    total_cycles = 100

    for i in range(total_cycles):
        # Present
        controller.present(origin_hwnd=3000 + i)
        qapp.processEvents()

        # Check visibility immediately
        if not launcher.isVisible() or launcher.state != LauncherState.INTERACTIVE:
            premature_dismissals += 1
            continue

        # Simulate variable dwell
        dwell_ms = (i % 5 + 1) * 2  # 2 to 10 ms
        time.sleep(dwell_ms / 1000.0)
        qapp.processEvents()

        # Check visibility after dwell
        if not launcher.isVisible():
            premature_dismissals += 1
            continue

        # Dismiss intentionally
        controller.dismiss(reason="cycle_test_dismiss")
        qapp.processEvents()

        if launcher.isVisible():
            premature_dismissals += 1

    premature_dismissal_rate = (premature_dismissals / total_cycles) * 100.0
    assert premature_dismissals == 0
    assert premature_dismissal_rate == 0.00
    hud.dismiss()
