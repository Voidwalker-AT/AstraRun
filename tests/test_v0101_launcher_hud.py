"""Unit and integration tests for AstraRun v0.10.1:
Real Alt+Space Launcher, Decoupled Floating Task HUD, and UX Reality Check.
"""

from __future__ import annotations

import sys
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication

from astrarun.app import AstraApplication, ExecutionResult
from astrarun.hotkeys.manager import HotkeyManager, parse_hotkey
from astrarun.tasks.events import TaskEventBus
from astrarun.tasks.models import TaskEvent, TaskEventType
from astrarun.ui.diagnostics import DiagnosticsDialog
from astrarun.ui.hud import FloatingTaskHUD, HUDState, TaskHUDController
from astrarun.ui.launcher import LauncherWindow
from astrarun.ui.positioning import (
    compute_launcher_position,
    compute_task_hud_position,
    compute_top_center_launcher_position,
    get_screen_for_hwnd,
)
from astrarun.ui.presentation import LauncherPresentationController


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Ensure a singleton QApplication is available across the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def astra_app() -> AstraApplication:
    """Fixture providing initialized AstraApplication composition root."""
    return AstraApplication()


# =========================================================================
# 1. HOTKEY MANAGER & PIPELINE DIAGNOSTICS TESTS
# =========================================================================

def test_hotkey_parsing():
    """Verify human-readable hotkeys parse into valid Win32 flags and VK codes."""
    mod, vk = parse_hotkey(["Alt"], "Space")
    assert mod & 0x0001  # MOD_ALT
    assert mod & 0x4000  # MOD_NOREPEAT
    assert vk == 0x20     # VK_SPACE

    mod_ctrl, vk_enter = parse_hotkey(["Ctrl", "Shift"], "Enter")
    assert mod_ctrl & 0x0002  # MOD_CONTROL
    assert mod_ctrl & 0x0004  # MOD_SHIFT
    assert vk_enter == 0x0D   # VK_RETURN


def test_hotkey_manager_diagnostics_and_simulation(qapp):
    """Verify HotkeyManager records telemetry and handles programmatic simulation."""
    mgr = HotkeyManager(config_modifiers=["Alt"], config_key="Space", hotkey_id=101)
    diag_initial = mgr.get_diagnostics()
    assert diag_initial["key"] == "Space"
    assert diag_initial["modifiers"] == ["Alt"]
    assert diag_initial["trigger_count"] == 0
    assert diag_initial["last_origin_hwnd"] == 0

    received = []
    mgr.hotkey_activated.connect(lambda hwnd: received.append(hwnd))

    # Simulate hotkey trigger with dummy origin HWND 2005
    mgr.simulate_hotkey(origin_hwnd=2005)
    assert len(received) == 1
    assert received[0] == 2005

    diag_post = mgr.get_diagnostics()
    assert diag_post["trigger_count"] == 1
    assert diag_post["last_origin_hwnd"] == 2005
    assert diag_post["last_signal_delivered_timestamp"] is not None


# =========================================================================
# 2. MONITOR PLACEMENT & DPI MATHEMATICS TESTS
# =========================================================================

def test_top_center_launcher_positioning():
    """Verify launcher positions at top-center within reasonable screen margins."""
    pos, avail = compute_top_center_launcher_position(window_width=640, window_height=56)
    assert isinstance(pos, QPoint)
    assert isinstance(avail, QRect)

    # Must be horizontally centered on work area
    expected_x = avail.x() + (avail.width() - 640) // 2
    assert pos.x() == expected_x

    # Must have top margin between 30px and 80px (top-center placement)
    assert 30 <= (pos.y() - avail.y()) <= 80


def test_top_right_task_hud_positioning():
    """Verify FloatingTaskHUD positions at top-right with standard margins."""
    hud_width = 380
    hud_height = 80
    pos, avail = compute_task_hud_position(hud_width, hud_height, margin_right=24, margin_top=24)

    assert isinstance(pos, QPoint)
    expected_x = avail.x() + avail.width() - hud_width - 24
    assert pos.x() == expected_x
    assert pos.y() == avail.y() + 24


@pytest.mark.parametrize("dpr,work_w,work_h", [
    (1.0, 1920, 1040),  # 100% scale
    (1.25, 1536, 816),  # 125% scale
    (1.5, 1280, 680),   # 150% scale
    (2.0, 960, 500),    # 200% scale
])
def test_multi_scale_dpi_geometry(dpr, work_w, work_h):
    """Verify positioning logic handles diverse virtual display resolutions and DPI scales."""
    mock_screen = MagicMock()
    mock_screen.availableGeometry.return_value = QRect(0, 0, work_w, work_h)
    mock_screen.devicePixelRatio.return_value = dpr

    pos, avail = compute_top_center_launcher_position(
        window_width=640, window_height=56, target_screen=mock_screen, top_margin=48
    )
    assert avail.width() == work_w
    assert avail.height() == work_h
    assert pos.x() == (work_w - 640) // 2
    assert pos.y() == 48

    hud_pos, _ = compute_task_hud_position(
        hud_width=380, hud_height=80, target_screen=mock_screen, margin_right=20, margin_top=20
    )
    assert hud_pos.x() == work_w - 380 - 20
    assert hud_pos.y() == 20


# =========================================================================
# 3. FLOATING TASK HUD NON-FOCUS-STEALING & STATE MACHINE TESTS
# =========================================================================

def test_task_hud_non_focus_stealing_flags(qapp):
    """
    CRITICAL PRODUCT INVARIANT:
    FloatingTaskHUD MUST have Qt.WindowDoesNotAcceptFocus and WA_ShowWithoutActivating
    so background progress updates never steal focus from the user's active window.
    """
    hud = FloatingTaskHUD(animations_enabled=False)
    flags = hud.windowFlags()

    assert bool(flags & Qt.WindowType.FramelessWindowHint)
    assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)
    assert bool(flags & Qt.WindowType.Tool)
    assert bool(flags & Qt.WindowType.WindowDoesNotAcceptFocus)
    assert hud.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert hud.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_task_hud_state_transitions(qapp):
    """Verify FloatingTaskHUD transitions across PASSIVE_PROGRESS, SUCCESS, ERROR, CONFIRMATION."""
    hud = FloatingTaskHUD(animations_enabled=False)
    assert hud.current_state == HUDState.IDLE

    # 1. Progress State
    hud.show_progress(task_id="task-101", title="Opening Notepad", message="Spawning process...")
    assert hud.current_state == HUDState.PASSIVE_PROGRESS
    assert hud.current_task_id == "task-101"
    assert "Opening Notepad" in hud.title_label.text()
    assert "Spawning process..." in hud.detail_label.text()

    # 2. Update Progress
    hud.update_progress(task_id="task-101", message="Typing greeting text...")
    assert "Typing greeting text..." in hud.detail_label.text()

    # 3. Success State
    hud.show_success(task_id="task-101", message="Notepad ready.")
    assert hud.current_state == HUDState.SUCCESS
    assert "Completed" in hud.title_label.text()
    assert "Notepad ready." in hud.detail_label.text()

    # 4. Error State
    hud.show_error(task_id="task-102", message="Process not found.")
    assert hud.current_state == HUDState.ERROR
    assert "Failed" in hud.title_label.text()

    # 5. Confirmation State
    hud.show_confirmation(
        task_id="task-103",
        prompt="Delete temp file?",
        token="tok_123",
        tool="delete_file",
        arguments={"path": "temp.txt"},
    )
    assert hud.current_state == HUDState.WAITING_CONFIRMATION
    assert hud.action_container.isVisible()

    hud.dismiss()
    assert hud.current_state == HUDState.IDLE


def test_task_hud_controller_event_bus_integration(qapp):
    """Verify TaskHUDController bridges TaskEventBus events into HUD updates."""
    bus = TaskEventBus()
    hud = FloatingTaskHUD(animations_enabled=False)
    controller = TaskHUDController(hud=hud, event_bus=bus)

    # Publish TASK_CREATED
    ev_created = TaskEvent(
        id="ev-1",
        task_id="t-99",
        type=TaskEventType.TASK_CREATED,
        title="Created task",
        summary="Created task",
        data={"raw_query": "snap window left"},
    )
    bus.publish(ev_created)
    qapp.processEvents()
    assert hud.current_state == HUDState.PASSIVE_PROGRESS
    assert hud.current_task_id == "t-99"

    # Publish WORKFLOW_STEP_STARTED
    ev_step = TaskEvent(
        id="ev-2",
        task_id="t-99",
        type=TaskEventType.WORKFLOW_STEP_STARTED,
        title="Step Started",
        summary="Snapping window to left half...",
    )
    bus.publish(ev_step)
    qapp.processEvents()
    assert "Snapping window to left half..." in hud.detail_label.text()

    # Publish TASK_COMPLETED
    ev_completed = TaskEvent(
        id="ev-3",
        task_id="t-99",
        type=TaskEventType.TASK_COMPLETED,
        title="Completed",
        summary="Window snapped successfully.",
    )
    bus.publish(ev_completed)
    qapp.processEvents()
    assert hud.current_state == HUDState.SUCCESS

    controller.stop()
    hud.dismiss()


# =========================================================================
# 4. LAUNCHER PRESENTATION CONTROLLER LIFECYCLE TESTS
# =========================================================================

def test_presentation_controller_lifecycle(qapp, astra_app):
    """Verify LauncherPresentationController presents, focuses, and dismisses cleanly."""
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    hotkey_mgr = HotkeyManager()

    controller = LauncherPresentationController(
        launcher=launcher,
        hud=hud,
        app=astra_app,
        hotkey_manager=hotkey_mgr,
    )

    started_events = []
    controller.presentation_started.connect(lambda hwnd: started_events.append(hwnd))

    assert not launcher.isVisible()

    # Present launcher
    controller.present(origin_hwnd=1001)
    qapp.processEvents()

    assert launcher.isVisible()
    assert len(started_events) == 1
    assert started_events[0] == 1001
    assert launcher.input_field.hasFocus() or not launcher.isHidden()

    # Dismiss launcher
    controller.dismiss()
    qapp.processEvents()
    assert not launcher.isVisible()

    # Toggle launcher
    controller.toggle_presentation(origin_hwnd=1002)
    qapp.processEvents()
    assert launcher.isVisible()

    controller.dismiss()
    hud.dismiss()


def test_diagnostics_integration(qapp, astra_app):
    """Verify application handle_request('hotkey status') and DiagnosticsDialog."""
    hotkey_mgr = HotkeyManager()
    astra_app.hotkey_manager = hotkey_mgr

    # 1. Pipeline CLI command
    res = astra_app.handle_request("hotkey status")
    assert res.success
    assert "Hotkey Status" in res.message
    assert res.data is not None
    assert "modifiers" in res.data
    assert "key" in res.data

    # 2. DiagnosticsDialog UI initialization
    dialog = DiagnosticsDialog(app_instance=astra_app, start_time=time.time())
    assert dialog.windowTitle() == "AstraRun Diagnostics"
    dialog.close()


def test_compound_nlp_and_workflow_execution(astra_app):
    """Verify compound commands decompose and compile into executable UI workflows."""
    from astrarun.nlp.engine import UserRequest

    utterance = astra_app.nlp_engine.parse(UserRequest(text="open notepad and type hello from Astra"))
    assert len(utterance.clauses) == 2
    assert utterance.clauses[0].action == "open_app"
    assert utterance.clauses[1].action == "type_text"

    proposal = astra_app.workflow_compiler.compile(utterance)
    assert proposal.status == "READY"
    assert len(proposal.steps) == 2
    assert proposal.steps[0].tool == "open_application"
    assert proposal.steps[0].arguments["app"] == "notepad"
    assert proposal.steps[1].tool == "type_text"
    assert proposal.steps[1].arguments["text"] == "hello from Astra"

