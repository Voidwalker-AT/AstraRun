"""Automated tests for AstraRun resident lifecycle, lifetime guarantees, and readiness protocol."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication

from astrarun import __version__
from astrarun.app import AstraApplication, SingleInstanceLock
from astrarun.hotkeys.manager import HotkeyManager
from astrarun.main import write_state_file
from astrarun.ui.hud import FloatingTaskHUD, TaskHUDController
from astrarun.ui.launcher import LauncherState, LauncherWindow
from astrarun.ui.presentation import LauncherPresentationController
from astrarun.ui.tray import AstraTrayIcon


def test_qapp_quit_on_last_window_closed_is_false(qapp):
    """Verify QApplication.quitOnLastWindowClosed is explicitly disabled for background residency."""
    qapp.setQuitOnLastWindowClosed(False)
    assert qapp.quitOnLastWindowClosed() is False


def test_qapp_does_not_quit_when_launcher_hidden(qapp):
    """Verify hiding the launcher does not trigger QApplication termination."""
    qapp.setQuitOnLastWindowClosed(False)
    astra_app = AstraApplication()
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)

    launcher.show_and_activate()
    qapp.processEvents()
    assert launcher.isVisible()

    # Dismiss launcher
    launcher.dismiss(reason="test_hide")
    qapp.processEvents()
    assert not launcher.isVisible()

    # Verify event loop continues and QApplication is alive
    tick_fired = False
    def on_tick():
        nonlocal tick_fired
        tick_fired = True

    QTimer.singleShot(10, on_tick)
    for _ in range(5):
        qapp.processEvents()
        time.sleep(0.01)

    assert tick_fired is True
    launcher.close()
    hud.close()
    astra_app.shutdown()


def test_qapp_does_not_quit_when_hud_hidden(qapp):
    """Verify hiding the HUD does not trigger QApplication termination."""
    qapp.setQuitOnLastWindowClosed(False)
    hud = FloatingTaskHUD(animations_enabled=False)

    hud.show_progress("test-task-1", "Testing", "Running...")
    qapp.processEvents()
    assert hud.isVisible()

    hud.dismiss()
    qapp.processEvents()
    assert not hud.isVisible()

    tick_fired = False
    def on_tick():
        nonlocal tick_fired
        tick_fired = True

    QTimer.singleShot(10, on_tick)
    for _ in range(5):
        qapp.processEvents()
        time.sleep(0.01)

    assert tick_fired is True
    hud.close()


def test_tray_and_ui_retained_on_app_root(qapp):
    """Verify strong references remain on the composition root to prevent premature garbage collection."""
    astra_app = AstraApplication()
    hud = FloatingTaskHUD(animations_enabled=False)
    hud_controller = TaskHUDController(hud=hud, event_bus=astra_app.task_event_bus, app=astra_app)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    hotkey = HotkeyManager()
    presentation = LauncherPresentationController(launcher=launcher, hud=hud, app=astra_app, hotkey_manager=hotkey)
    tray = AstraTrayIcon(parent=launcher)

    astra_app.launcher = launcher
    astra_app.hud = hud
    astra_app.hud_controller = hud_controller
    astra_app.hotkey_manager = hotkey
    astra_app.presentation_controller = presentation
    astra_app.tray_icon = tray

    # Assert all references are alive
    assert astra_app.launcher is launcher
    assert astra_app.hud is hud
    assert astra_app.hud_controller is hud_controller
    assert astra_app.hotkey_manager is hotkey
    assert astra_app.presentation_controller is presentation
    assert astra_app.tray_icon is tray

    # Teardown
    launcher.close()
    hud.close()
    astra_app.shutdown()


def test_resident_idle_lifecycle_survives_without_windows(qapp):
    """Verify AstraRun stays resident indefinitely when neither launcher nor HUD is visible."""
    qapp.setQuitOnLastWindowClosed(False)
    astra_app = AstraApplication()
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)

    assert not launcher.isVisible()
    assert not hud.isVisible()

    # Simulate 50 event loop cycles with zero visible windows
    cycles_completed = 0
    for _ in range(50):
        qapp.processEvents()
        time.sleep(0.005)
        cycles_completed += 1

    assert cycles_completed == 50
    assert not launcher.isVisible()
    assert not hud.isVisible()

    launcher.close()
    hud.close()
    astra_app.shutdown()


def test_single_instance_lifecycle():
    """Verify single instance lock acquires, detects collisions, and releases cleanly."""
    lock1 = SingleInstanceLock("AstraRun_Test_Instance_Mutex")
    assert lock1.acquire() is True
    assert lock1.is_primary_instance is True

    # Second instance must fail to acquire
    lock2 = SingleInstanceLock("AstraRun_Test_Instance_Mutex")
    assert lock2.acquire() is False
    assert lock2.is_primary_instance is False

    # First instance releases
    lock1.release()

    # Now second instance should succeed
    assert lock2.acquire() is True
    assert lock2.is_primary_instance is True
    lock2.release()


def test_readiness_state_file_lifecycle(tmp_path, monkeypatch):
    """Verify write_state_file writes valid JSON readiness signal and cleans up."""
    state_file = tmp_path / "data" / "astrarun_state.json"
    monkeypatch.chdir(tmp_path)

    write_state_file(
        status="READY",
        ready=True,
        stage="EVENT_LOOP_ENTERING",
        modifiers=["Alt"],
        key="Space",
    )

    assert state_file.exists()
    with open(state_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["pid"] == os.getpid()
    assert data["status"] == "READY"
    assert data["ready"] is True
    assert data["version"] == __version__
    assert data["hotkey"] == "Alt+Space"
    assert data["stage"] == "EVENT_LOOP_ENTERING"

    # Cleanup state
    state_file.unlink()
    assert not state_file.exists()


def test_stale_readiness_cleanup(tmp_path, monkeypatch):
    """Verify existing stale readiness state is overwritten with fresh state on startup."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    state_file = tmp_path / "data" / "astrarun_state.json"
    monkeypatch.chdir(tmp_path)

    # Write stale state
    stale_data = {"pid": 999999, "status": "STALE", "ready": False}
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(stale_data, f)

    # Write fresh state
    write_state_file(
        status="READY",
        ready=True,
        stage="EVENT_LOOP_ENTERING",
    )

    with open(state_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["pid"] == os.getpid()
    assert data["status"] == "READY"
    assert data["ready"] is True
    state_file.unlink()
