"""Unit and integration tests for AstraRun v0.9 Daily Driver Integration and Window Intelligence."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astrarun.app import AstraApplication, ExecutionResult
from astrarun.capabilities.models import CapabilityErrorCode, WindowEntity
from astrarun.core.models import ActionGateOutcome
from astrarun.tasks.models import TaskStatus
from astrarun.windows.controller import (
    arrange_desktop,
    close_window,
    focus_window,
    maximize_window,
    minimize_window,
    move_window,
    move_window_to_monitor,
    resize_window,
    restore_window,
    snap_window,
    snap_window_left,
    snap_window_right,
    undo_last_window_move,
)
from astrarun.windows.discovery import foreground_window, list_windows
from astrarun.windows.layouts import DesktopLayoutEngine
from astrarun.windows.models import LayoutType, MonitorEntity, WindowBounds, WindowLayoutSnapshot, WindowState
from astrarun.windows.monitors import enumerate_monitors, get_primary_monitor, resolve_monitor, set_mock_monitors
from astrarun.windows.policy import (
    clamp_geometry,
    is_astrarun_window,
    is_simulated_window_validation,
    register_astrarun_hwnd,
    set_simulated_window_validation,
    unregister_astrarun_hwnd,
    validate_window_identity,
)
from astrarun.windows.resolver import WindowResolution, WindowResolver
from astrarun.windows.undo import WindowRestoreStack


@pytest.fixture(autouse=True)
def setup_simulated_windows():
    """Ensure tests run safely in simulated window mode with clean mocks."""
    set_simulated_window_validation(True)
    yield
    set_simulated_window_validation(False)
    set_mock_monitors(None)


@pytest.fixture
def mock_origin_window() -> WindowEntity:
    return WindowEntity(
        hwnd=1002,
        title="Visual Studio Code - AstraRun",
        pid=1100,
        app_id="code.exe",
        bounds=(0, 0, 1920, 1080),
        state="maximized",
        visible=True,
    )


@pytest.fixture
def astra_app() -> AstraApplication:
    return AstraApplication()


# =========================================================================
# 1. WINDOW RESOLVER TESTS
# =========================================================================

def test_window_resolver_direct_match():
    resolver = WindowResolver()
    pool = [
        WindowEntity(hwnd=10, title="Google Chrome", pid=100, app_id="chrome.exe", bounds=(0, 0, 800, 600), state="normal", visible=True),
        WindowEntity(hwnd=20, title="Spotify Free", pid=200, app_id="spotify.exe", bounds=(0, 0, 800, 600), state="normal", visible=True),
    ]
    res = resolver.resolve("spotify", windows_override=pool)
    assert res.is_resolved
    assert res.window.hwnd == 20
    assert res.window.title == "Spotify Free"


def test_window_resolver_pronoun_to_origin(mock_origin_window):
    resolver = WindowResolver()
    for pronoun in ("this", "this window", "current window", "it", "active"):
        res = resolver.resolve(pronoun, origin_window=mock_origin_window)
        assert res.is_resolved
        assert res.window.hwnd == mock_origin_window.hwnd
        assert res.window.title == mock_origin_window.title


def test_window_resolver_context_anaphora():
    resolver = WindowResolver()
    ctx_win = WindowEntity(hwnd=30, title="Explorer - Documents", pid=300, app_id="explorer.exe", bounds=(0, 0, 800, 600), state="normal", visible=True)
    res = resolver.resolve("that window", context_last_window=ctx_win)
    assert res.is_resolved
    assert res.window.hwnd == 30

    res_empty = resolver.resolve("that window", context_last_window=None)
    assert res_empty.status == "NOT_FOUND"


def test_window_resolver_ambiguity_gating():
    resolver = WindowResolver()
    pool = [
        WindowEntity(hwnd=41, title="Chrome - Tab 1", pid=400, app_id="chrome.exe", bounds=(0, 0, 800, 600), state="normal", visible=True),
        WindowEntity(hwnd=42, title="Chrome - Tab 2", pid=400, app_id="chrome.exe", bounds=(0, 0, 800, 600), state="normal", visible=True),
    ]
    res = resolver.resolve("chrome", windows_override=pool)
    assert res.is_ambiguous
    assert len(res.candidates) == 2


def test_window_resolver_exact_title_break_ambiguity():
    resolver = WindowResolver()
    pool = [
        WindowEntity(hwnd=51, title="Terminal", pid=500, app_id="terminal.exe", bounds=(0, 0, 800, 600), state="normal", visible=True),
        WindowEntity(hwnd=52, title="Terminal - Server", pid=501, app_id="terminal.exe", bounds=(0, 0, 800, 600), state="normal", visible=True),
    ]
    res = resolver.resolve("Terminal", windows_override=pool)
    assert res.is_resolved
    assert res.window.hwnd == 51


# =========================================================================
# 2. DESKTOP LAYOUT ENGINE & TILING TESTS
# =========================================================================

def test_desktop_layout_engine_half_splits():
    work_area = (0, 0, 1920, 1080)
    left = DesktopLayoutEngine.compute_bounds(LayoutType.LEFT_HALF, work_area)
    assert left == (0, 0, 960, 1080)

    right = DesktopLayoutEngine.compute_bounds(LayoutType.RIGHT_HALF, work_area)
    assert right == (960, 0, 960, 1080)

    top = DesktopLayoutEngine.compute_bounds(LayoutType.TOP_HALF, work_area)
    assert top == (0, 0, 1920, 540)

    bottom = DesktopLayoutEngine.compute_bounds(LayoutType.BOTTOM_HALF, work_area)
    assert bottom == (0, 540, 1920, 540)


def test_desktop_layout_engine_quad_corners():
    work_area = (0, 0, 1920, 1080)
    tl = DesktopLayoutEngine.compute_bounds(LayoutType.TOP_LEFT, work_area)
    assert tl == (0, 0, 960, 540)

    tr = DesktopLayoutEngine.compute_bounds(LayoutType.TOP_RIGHT, work_area)
    assert tr == (960, 0, 960, 540)

    bl = DesktopLayoutEngine.compute_bounds(LayoutType.BOTTOM_LEFT, work_area)
    assert bl == (0, 540, 960, 540)

    br = DesktopLayoutEngine.compute_bounds(LayoutType.BOTTOM_RIGHT, work_area)
    assert br == (960, 540, 960, 540)


def test_desktop_layout_engine_two_thirds_and_one_third():
    work_area = (0, 0, 1920, 1080)
    twothirds = DesktopLayoutEngine.compute_bounds(LayoutType.LEFT_TWO_THIRDS, work_area)
    assert twothirds == (0, 0, 1280, 1080)

    onethird = DesktopLayoutEngine.compute_bounds(LayoutType.RIGHT_ONE_THIRD, work_area)
    assert onethird == (1280, 0, 640, 1080)


def test_geometry_clamping():
    # Normal bounds
    assert clamp_geometry(100, 100, 800, 600) == (100, 100, 800, 600)
    # Below minimum width/height
    assert clamp_geometry(0, 0, 50, 50) == (0, 0, 150, 100)
    # Extreme coordinate overflow clamping
    assert clamp_geometry(-999999, 999999, 800, 600) == (-50000, 50000, 800, 600)


# =========================================================================
# 3. WINDOW RESTORE UNDO STACK TESTS
# =========================================================================

def test_window_restore_stack_lifo():
    stack = WindowRestoreStack(max_depth=5)
    s1 = WindowLayoutSnapshot(hwnd=1, pid=10, title="App 1", bounds=(0, 0, 100, 100), state="normal", monitor_id=1)
    s2 = WindowLayoutSnapshot(hwnd=2, pid=20, title="App 2", bounds=(0, 0, 200, 200), state="normal", monitor_id=1)

    stack.push(s1)
    stack.push(s2)
    assert len(stack) == 2

    assert stack.peek().hwnd == 2
    popped = stack.pop()
    assert popped.hwnd == 2
    assert stack.pop().hwnd == 1
    assert stack.pop() is None


def test_window_restore_stack_bounded_depth():
    stack = WindowRestoreStack(max_depth=3)
    for i in range(10):
        stack.push(WindowLayoutSnapshot(hwnd=i, pid=100, title=f"W{i}", bounds=(0, 0, 10, 10), state="normal", monitor_id=1))
    assert len(stack) == 3
    assert stack.pop().hwnd == 9


def test_window_restore_stack_ttl_expiration():
    stack = WindowRestoreStack(max_depth=5, ttl_seconds=1.0)
    s = WindowLayoutSnapshot(hwnd=99, pid=10, title="Old", bounds=(0, 0, 10, 10), state="normal", monitor_id=1, timestamp=time.time() - 2.0)
    stack.push(s)
    # Pop triggers prune
    assert stack.pop() is None
    assert len(stack) == 0


# =========================================================================
# 4. SAFETY POLICY & SELF-PROTECTION INVARIANTS
# =========================================================================

def test_astrarun_self_window_protection():
    hwnd = 77777
    register_astrarun_hwnd(hwnd)
    assert is_astrarun_window(hwnd)

    valid, reason, code = validate_window_identity(hwnd)
    assert not valid
    assert code == CapabilityErrorCode.PERMISSION_DENIED
    assert "AstraRun UI" in reason

    unregister_astrarun_hwnd(hwnd)
    assert not is_astrarun_window(hwnd)


def test_validate_window_identity_null_or_negative():
    valid, reason, code = validate_window_identity(0)
    assert not valid
    assert code == CapabilityErrorCode.INVALID_ARGUMENT

    valid, reason, code = validate_window_identity(-5)
    assert not valid
    assert code == CapabilityErrorCode.INVALID_ARGUMENT


def test_validate_window_identity_toctou_pid_mismatch():
    set_simulated_window_validation(False)
    # When simulated validation is off, non-existent HWND returns NOT_FOUND
    valid, reason, code = validate_window_identity(99999999, expected_pid=1234)
    assert not valid
    set_simulated_window_validation(True)


# =========================================================================
# 5. MULTI-MONITOR RESOLUTION TESTS
# =========================================================================

def test_monitor_resolution_natural_language():
    m1 = MonitorEntity(monitor_id=1, device_name="DISP1", work_area=(0, 0, 1920, 1032), full_bounds=(0, 0, 1920, 1080), is_primary=True)
    m2 = MonitorEntity(monitor_id=2, device_name="DISP2", work_area=(1920, 0, 1920, 1032), full_bounds=(1920, 0, 1920, 1080), is_primary=False)
    set_mock_monitors([m1, m2])

    assert resolve_monitor("primary").monitor_id == 1
    assert resolve_monitor("secondary").monitor_id == 2
    assert resolve_monitor("left").monitor_id == 1
    assert resolve_monitor("right").monitor_id == 2
    assert resolve_monitor("other", current_monitor_id=1).monitor_id == 2
    assert resolve_monitor("other", current_monitor_id=2).monitor_id == 1
    assert resolve_monitor("monitor 1").monitor_id == 1
    assert resolve_monitor("monitor 2").monitor_id == 2


# =========================================================================
# 6. APPLICATION COMPOSITION ROOT & HANDLE_REQUEST TESTS
# =========================================================================

def test_astra_application_initialization(astra_app):
    assert len(astra_app.capability_registry.list_capabilities()) >= 59
    assert astra_app.single_instance is not None
    assert astra_app.restore_stack is not None
    assert astra_app.window_resolver is not None


def test_handle_request_fast_path(astra_app):
    res = astra_app.handle_request("calc", dry_run=True)
    assert res.type == "fast_path"
    assert res.success
    assert "calc" in res.message


def test_handle_request_direct_ui_commands(astra_app):
    assert astra_app.handle_request("history").message == "open_history"
    assert astra_app.handle_request("memory").message == "open_memory"
    assert astra_app.handle_request("skills").message == "open_skills"
    assert astra_app.handle_request("settings").message == "open_settings"
    assert astra_app.handle_request("diagnostics").message == "open_diagnostics"
    assert astra_app.handle_request("what can you do?").type == "list_result"


def test_handle_request_window_snapping_and_undo(astra_app, mock_origin_window):
    # Snap left
    res_snap = astra_app.handle_request("snap this window left", origin_window=mock_origin_window, dry_run=True)
    assert res_snap.success
    assert "left_half" in res_snap.message

    # Undo
    res_undo = astra_app.handle_request("undo", dry_run=True)
    assert res_undo.success
    assert "Restored window" in res_undo.message


def test_handle_request_system_inspection(astra_app):
    res_cpu = astra_app.handle_request("cpu status", dry_run=True)
    assert res_cpu.success
    assert "CPU Utilization" in res_cpu.message

    res_mem = astra_app.handle_request("memory status", dry_run=True)
    assert res_mem.success
    assert "RAM" in res_mem.message


def test_handle_request_safety_confirmation_gate(astra_app):
    # Terminate process requires confirmation or is blocked
    res = astra_app.handle_request("terminate process 1234", dry_run=True)
    assert not res.success
    assert res.type in ("confirm", "blocked")


def test_handle_request_reasoning_escalation(astra_app):
    res = astra_app.handle_request("why is the system slow?", dry_run=True)
    assert res.type == "reasoning_required"
    assert res.success
    assert "diagnostic" in res.message.lower() or "reasoning" in res.message.lower()


def test_handle_request_empty_query(astra_app):
    res = astra_app.handle_request("   ", dry_run=True)
    assert not res.success
    assert res.type == "error"
    assert "empty" in res.message.lower()


def test_single_instance_lock():
    from astrarun.app import SingleInstanceLock
    lock1 = SingleInstanceLock("AstraRun_Test_Mutex_1")
    assert lock1.acquire()

    # Second instance with same mutex should fail
    lock2 = SingleInstanceLock("AstraRun_Test_Mutex_1")
    assert not lock2.acquire()

    lock1.release()
    lock2.release()


def test_window_layout_snapshot_serialization():
    snap = WindowLayoutSnapshot(
        hwnd=1234,
        pid=5678,
        title="Test Window",
        bounds=(10, 20, 800, 600),
        state="normal",
        monitor_id=1,
    )
    d = snap.to_dict()
    assert d["hwnd"] == 1234
    assert d["pid"] == 5678
    assert d["title"] == "Test Window"
    assert d["bounds"] == (10, 20, 800, 600)
    assert d["state"] == "normal"
    assert d["monitor_id"] == 1
    assert not snap.is_expired(600.0)
    assert snap.is_expired(0.0)


def test_monitor_entity_serialization():
    mon = MonitorEntity(
        monitor_id=2,
        device_name="\\\\.\\DISPLAY2",
        work_area=(1920, 0, 1920, 1032),
        full_bounds=(1920, 0, 1920, 1080),
        is_primary=False,
        dpi=120,
    )
    d = mon.to_dict()
    assert d["monitor_id"] == 2
    assert d["device_name"] == "\\\\.\\DISPLAY2"
    assert not d["is_primary"]
    assert d["dpi"] == 120


def test_window_bounds_dataclass():
    wb = WindowBounds(x=50, y=60, width=800, height=600)
    assert wb.to_tuple() == (50, 60, 800, 600)
    assert wb.to_dict() == {"x": 50, "y": 60, "width": 800, "height": 600}


def test_layout_type_parsing_variations():
    assert DesktopLayoutEngine.parse_layout("snap_left") == LayoutType.LEFT_HALF
    assert DesktopLayoutEngine.parse_layout("right_half") == LayoutType.RIGHT_HALF
    assert DesktopLayoutEngine.parse_layout("top") == LayoutType.TOP_HALF
    assert DesktopLayoutEngine.parse_layout("bottom") == LayoutType.BOTTOM_HALF
    assert DesktopLayoutEngine.parse_layout("two_thirds") == LayoutType.LEFT_TWO_THIRDS
    assert DesktopLayoutEngine.parse_layout("one_third") == LayoutType.RIGHT_ONE_THIRD
    assert DesktopLayoutEngine.parse_layout("unknown_layout_xyz") == LayoutType.FULL


def test_window_restore_stack_clear():
    stack = WindowRestoreStack(max_depth=5)
    stack.push(WindowLayoutSnapshot(hwnd=1, pid=1, title="1", bounds=(0, 0, 10, 10), state="normal", monitor_id=1))
    stack.push(WindowLayoutSnapshot(hwnd=2, pid=2, title="2", bounds=(0, 0, 10, 10), state="normal", monitor_id=1))
    assert len(stack) == 2
    stack.clear()
    assert len(stack) == 0
    assert stack.pop() is None


def test_window_resolution_dataclass():
    win = WindowEntity(hwnd=99, title="App", pid=1, app_id="app.exe", bounds=(0, 0, 10, 10), state="normal", visible=True)
    res_ok = WindowResolution(status="RESOLVED", window=win)
    assert res_ok.is_resolved
    assert not res_ok.is_ambiguous

    res_amb = WindowResolution(status="AMBIGUOUS", candidates=[win, win])
    assert res_amb.is_ambiguous
    assert not res_amb.is_resolved


def test_controller_move_and_resize_simulation():
    res_move = move_window(hwnd=1002, x=200, y=150, pid=1100)
    assert res_move.success
    assert "Moved window 1002" in res_move.message

    res_resize = resize_window(hwnd=1002, width=1024, height=768, pid=1100)
    assert res_resize.success
    assert "1002" in res_resize.message


def test_controller_move_to_monitor_simulation():
    m1 = MonitorEntity(monitor_id=1, device_name="D1", work_area=(0, 0, 1920, 1032), full_bounds=(0, 0, 1920, 1080), is_primary=True)
    m2 = MonitorEntity(monitor_id=2, device_name="D2", work_area=(1920, 0, 1920, 1032), full_bounds=(1920, 0, 1920, 1080), is_primary=False)
    set_mock_monitors([m1, m2])

    res = move_window_to_monitor(hwnd=1002, monitor_spec=2, pid=1100)
    assert res.success
    assert "Monitor 2" in res.message


def test_controller_close_window_simulation():
    res = close_window(hwnd=1002, pid=1100)
    assert res.success
    assert "Sent WM_CLOSE" in res.message


def test_controller_arrange_desktop_simulation():
    res = arrange_desktop(plan=[{"hwnd": 1002, "layout": "left_half"}])
    assert res.success
    assert "Arranged" in res.message


def test_diagnostics_dialog_data_collection(astra_app):
    from astrarun.ui.diagnostics import DiagnosticsDialog
    from PySide6.QtWidgets import QApplication

    app_instance = QApplication.instance() or QApplication([])
    dialog = DiagnosticsDialog(app_instance=astra_app, start_time=time.time())
    assert dialog.windowTitle() == "AstraRun Diagnostics"
    assert dialog.app == astra_app
    dialog.close()


def test_settings_dialog_preferences_io(astra_app):
    from astrarun.ui.settings import SettingsDialog
    from PySide6.QtWidgets import QApplication

    app_instance = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(app_instance=astra_app)
    assert dialog.windowTitle() == "AstraRun Settings"
    assert hasattr(dialog, "startup_cb")
    assert hasattr(dialog, "learning_cb")
    assert hasattr(dialog, "export_cb")
    dialog.close()

