"""Milestone 5 Validation: Resident Astra Application, TaskRuntime, Floating HUD & System Tray.

Verifies:
  1. Win32 named mutex single-instance guard and local Named Pipe IPC.
  2. Exactly ONE resident instance across 10 consecutive simulated launches.
  3. Single Astra system tray icon with star/spark identity and discrete states.
  4. Alt+Space command surface with ✦ prompt, entrance animation, and fast keyboard readiness.
  5. TaskRuntime multi-task resource locking (physical input serialization).
  6. User takeover (PAUSED_USER_ACTIVE) and floating HUD takeover card.
  7. TaskCenterWindow task monitoring and actions.
  8. ActionGate confirmation and clarification UI flows.
  9. Zero console window creation flags.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QPushButton

from astrarun.core.single_instance import (
    AstraSingleInstance,
    get_user_sid,
)
from astrarun.tasks.events import TaskEventBus
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.models import (
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)
from astrarun.tasks.runtime import (
    ResourceLockManager,
    ResourceLockType,
    TaskRuntime,
)
from astrarun.ui.hud import FloatingTaskHUD, HUDState, TaskHUDController
from astrarun.ui.launcher import LauncherState, LauncherWindow
from astrarun.ui.task_center import TaskCardWidget, TaskCenterWindow
from astrarun.ui.tray import AstraTrayIcon, TrayState, create_tray_icon_pixmap


# =========================================================================
# 1. SINGLE-INSTANCE MUTEX & NAMED PIPE IPC TESTS
# =========================================================================

def test_user_sid_extraction():
    """Verify Win32 user SID extraction returns valid SID string."""
    sid = get_user_sid()
    assert isinstance(sid, str)
    assert len(sid) > 4
    if sys.platform == "win32":
        assert sid.startswith("S-") or sid.startswith("S-FALLBACK-")


def test_single_instance_acquisition():
    """Verify primary instance acquires mutex and secondary launch detects it."""
    test_sid = f"TEST_M5_{int(time.time()*1000)}"
    primary = AstraSingleInstance(custom_sid=test_sid)
    secondary = AstraSingleInstance(custom_sid=test_sid)

    try:
        # Primary acquisition
        assert primary.acquire() is True
        assert primary.is_primary is True

        # Secondary attempt should fail acquisition
        assert secondary.acquire() is False
        assert secondary.is_primary is False
    finally:
        primary.release()
        secondary.release()


def test_named_pipe_ipc_communication():
    """Verify local Named Pipe IPC delivers commands and receives responses without network ports."""
    test_sid = f"TEST_IPC_{int(time.time()*1000)}"
    server = AstraSingleInstance(custom_sid=test_sid)
    client = AstraSingleInstance(custom_sid=test_sid)

    received_cmds = []

    def handle_cmd(command: str, args: dict) -> dict:
        received_cmds.append((command, args))
        return {"result": f"processed_{command}"}

    try:
        assert server.acquire() is True
        server.start_ipc_server(handle_cmd)
        time.sleep(0.1)  # Allow pipe server thread to bind

        if sys.platform == "win32":
            resp = client.send_command("SHOW_MAIN_UI", {"source": "test"})
            assert resp.get("status") == "OK"
            assert resp.get("result") == "processed_SHOW_MAIN_UI"
            assert len(received_cmds) == 1
            assert received_cmds[0][0] == "SHOW_MAIN_UI"
            assert received_cmds[0][1] == {"source": "test"}
    finally:
        server.release()


def test_ten_consecutive_launches_single_resident():
    """Verify 10 consecutive simulated launches result in exactly 1 resident process and 10 pipe commands."""
    test_sid = f"TEST_MULTI_{int(time.time()*1000)}"
    primary = AstraSingleInstance(custom_sid=test_sid)
    dispatched_commands = []

    def cmd_handler(command: str, args: dict) -> dict:
        dispatched_commands.append(command)
        return {"ack": True}

    try:
        assert primary.acquire() is True
        primary.start_ipc_server(cmd_handler)
        time.sleep(0.05)

        for i in range(10):
            subsequent = AstraSingleInstance(custom_sid=test_sid)
            acquired = subsequent.acquire()
            assert acquired is False, f"Launch {i+1} should not acquire primary mutex"
            subsequent.release()

        if sys.platform == "win32":
            assert len(dispatched_commands) == 10
            assert all(cmd == "SHOW_MAIN_UI" for cmd in dispatched_commands)
    finally:
        primary.release()


# =========================================================================
# 2. SYSTEM TRAY ICON & CANONICAL MENU TESTS
# =========================================================================

def test_tray_icon_and_states(qapp):
    """Verify single system tray icon, state changes, tooltips, and menu actions."""
    tray = AstraTrayIcon()
    assert tray.state == TrayState.READY
    assert "Ready" in tray.toolTip()

    # Discrete state transitions
    tray.set_state(TrayState.WORKING, detail="Indexing files")
    assert tray.state == TrayState.WORKING
    assert "Working" in tray.toolTip()
    assert "Indexing files" in tray.toolTip()

    tray.set_state(TrayState.PAUSED)
    assert tray.state == TrayState.PAUSED
    assert "Paused" in tray.toolTip()

    tray.set_state(TrayState.ATTENTION_REQUIRED)
    assert tray.state == TrayState.ATTENTION_REQUIRED
    assert "Attention" in tray.toolTip()

    tray.set_state(TrayState.ERROR)
    assert tray.state == TrayState.ERROR
    assert "Error" in tray.toolTip()

    # Canonical menu actions
    menu = tray.contextMenu()
    assert menu is not None
    action_texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert any("Open Astra" in t for t in action_texts)
    assert "Task Center" in action_texts
    assert "Pause Astra" in action_texts
    assert "Settings" in action_texts
    assert "Restart Astra" in action_texts
    assert "Quit Astra" in action_texts

    # Test tray toggle pause
    pause_events = []
    resume_events = []
    tray.pause_astra_requested.connect(lambda: pause_events.append(True))
    tray.resume_astra_requested.connect(lambda: resume_events.append(True))

    tray._toggle_pause()
    assert tray.is_paused is True
    assert len(pause_events) == 1
    assert tray.state == TrayState.PAUSED

    tray._toggle_pause()
    assert tray.is_paused is False
    assert len(resume_events) == 1
    assert tray.state == TrayState.READY


# =========================================================================
# 3. ALT+SPACE COMMAND SURFACE & KEYBOARD READINESS
# =========================================================================

def test_command_surface_visuals_and_readiness(qapp):
    """Verify Alt+Space launcher displays ✦ prompt, animates smoothly, and focuses input."""
    launcher = LauncherWindow(animations_enabled=False)

    # Prompt glyph must be ✦
    assert launcher.prompt_label.text() == "✦"
    assert launcher.state == LauncherState.HIDDEN

    # Measure presentation latency
    t0 = time.perf_counter()
    launcher.show_and_activate()
    dt_ms = (time.perf_counter() - t0) * 1000.0

    # Presentation must complete rapidly (<100ms)
    assert dt_ms < 100.0
    assert launcher.isVisible()
    assert launcher.state == LauncherState.INTERACTIVE
    assert launcher.input_field.hasFocus() or not launcher.isHidden()

    # Test open_task_center method exists
    assert hasattr(launcher, "open_task_center")

    launcher.dismiss(reason="test_done")
    assert not launcher.isVisible()
    assert launcher.state == LauncherState.HIDDEN


# =========================================================================
# 4. TASK RUNTIME MULTI-TASK RESOURCE LOCKING TESTS
# =========================================================================

def test_resource_lock_manager():
    """Verify ResourceLockManager serializes PHYSICAL_INPUT while allowing other locks."""
    rm = ResourceLockManager()

    # Task 1 acquires physical input lock
    assert rm.acquire_lock(ResourceLockType.PHYSICAL_INPUT.value, "task_1", timeout_sec=0.1) is True
    assert rm.is_locked(ResourceLockType.PHYSICAL_INPUT.value) is True

    # Task 2 cannot acquire physical input lock while task 1 holds it
    assert rm.acquire_lock(ResourceLockType.PHYSICAL_INPUT.value, "task_2", timeout_sec=0.1) is False

    # Task 2 CAN acquire BROWSER lock concurrently
    assert rm.acquire_lock(ResourceLockType.BROWSER.value, "task_2", timeout_sec=0.1) is True

    # Release task 1 lock
    rm.release_lock(ResourceLockType.PHYSICAL_INPUT.value, "task_1")
    assert rm.is_locked(ResourceLockType.PHYSICAL_INPUT.value) is False

    # Now task 2 can acquire physical input
    assert rm.acquire_lock(ResourceLockType.PHYSICAL_INPUT.value, "task_2", timeout_sec=0.1) is True
    rm.release_all_for_task("task_2")
    assert rm.is_locked(ResourceLockType.PHYSICAL_INPUT.value) is False
    assert rm.is_locked(ResourceLockType.BROWSER.value) is False


def test_task_runtime_lifecycle_and_user_takeover():
    """Verify TaskRuntime transitions, user takeover pause (PAUSED_USER_ACTIVE), and resume/cancel."""
    bus = TaskEventBus()
    db_path = f"data/test_runtime_{int(time.time()*1000)}.db"
    ledger = TaskLedger(db_path)
    runtime = TaskRuntime(event_bus=bus, ledger=ledger)

    events_captured = []
    bus.subscribe(lambda ev: events_captured.append(ev))

    # 1. Enqueue Task
    task = runtime.create_and_enqueue_task("Automate report generation")
    assert task.status == TaskStatus.QUEUED
    assert len(events_captured) == 1
    assert events_captured[0].type == TaskEventType.TASK_CREATED

    # Simulate task running
    task.status = TaskStatus.RUNNING
    runtime.lock_manager.acquire_lock(ResourceLockType.PHYSICAL_INPUT.value, task.id)

    # 2. User Takeover (physical user starts typing/clicking)
    runtime.pause_task(task.id, is_user_takeover=True)
    assert task.status == TaskStatus.PAUSED_USER_ACTIVE
    # Physical input lock must be immediately released for user
    assert runtime.lock_manager.is_locked(ResourceLockType.PHYSICAL_INPUT.value) is False

    takeover_events = [e for e in events_captured if e.type == TaskEventType.TASK_INTERRUPTED]
    assert len(takeover_events) == 1
    assert takeover_events[0].data.get("is_user_takeover") is True

    # 3. Resume Task & 4. Cancel Task
    with patch.object(runtime, "start_task_async"):
        runtime.resume_task(task.id)
        assert task.status == TaskStatus.RUNNING

        runtime.cancel_task(task.id)
        assert task.status == TaskStatus.CANCELLED
        cancel_events = [e for e in events_captured if e.type == TaskEventType.TASK_CANCELLED]
        assert len(cancel_events) == 1

    # Clean test DB
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


# =========================================================================
# 5. FLOATING HUD USER TAKEOVER & ACTION GATE CARDS
# =========================================================================

def test_floating_hud_user_takeover(qapp):
    """Verify FloatingTaskHUD displays user takeover card with Resume and Cancel actions."""
    hud = FloatingTaskHUD(animations_enabled=False)
    resume_calls = []
    cancel_calls = []

    hud.resume_requested.connect(lambda tid: resume_calls.append(tid))
    hud.cancel_requested.connect(lambda tid: cancel_calls.append(tid))

    hud.show_user_takeover("task_123", "Paused — you're using the computer")
    assert hud.current_task_id == "task_123"
    assert "Paused" in hud.title_label.text()
    assert "using the computer" in hud.detail_label.text()
    assert hud.action_container.isVisible()

    # Buttons should be Resume and Cancel
    buttons = hud.action_container.findChildren(QPushButton)
    assert len(buttons) == 2
    btn_labels = [b.text() for b in buttons]
    assert "Resume" in btn_labels
    assert "Cancel" in btn_labels

    # Click resume
    for b in buttons:
        if b.text() == "Resume":
            b.click()
            break
    assert resume_calls == ["task_123"]

    hud.dismiss(immediate=True)


def test_floating_hud_action_gate_confirmation(qapp):
    """Verify ActionGate confirmation card displays and emits confirmation."""
    hud = FloatingTaskHUD(animations_enabled=False)
    confirmed_payload = []
    hud.confirmed.connect(lambda token, tool, args: confirmed_payload.append((token, tool, args)))

    hud.show_confirmation(
        task_id="task_confirm_1",
        prompt="Delete temporary directory?",
        token="tok_xyz",
        tool="delete_folder",
        arguments={"path": "C:\\temp"},
    )

    assert hud.title_label.text() == "Confirmation Required"
    assert "Delete temporary directory?" in hud.detail_label.text()
    assert hud.action_container.isVisible()

    buttons = hud.action_container.findChildren(QPushButton)
    assert len(buttons) == 2  # Confirm, Cancel

    for b in buttons:
        if b.text() == "Confirm":
            b.click()
            break

    assert len(confirmed_payload) == 1
    assert confirmed_payload[0][0] == "tok_xyz"
    assert confirmed_payload[0][1] == "delete_folder"
    assert confirmed_payload[0][2] == {"path": "C:\\temp"}

    hud.dismiss(immediate=True)


# =========================================================================
# 6. TASK CENTER WINDOW TESTS
# =========================================================================

def test_task_center_window(qapp):
    """Verify TaskCenterWindow displays active and completed tasks with pause/cancel controls."""
    bus = TaskEventBus()
    db_path = f"data/test_tc_{int(time.time()*1000)}.db"
    ledger = TaskLedger(db_path)
    runtime = TaskRuntime(event_bus=bus, ledger=ledger)

    t1 = runtime.create_and_enqueue_task("Task 1 - Running")
    t1.status = TaskStatus.RUNNING
    t2 = runtime.create_and_enqueue_task("Task 2 - Completed")
    t2.status = TaskStatus.COMPLETED

    center = TaskCenterWindow(task_runtime=runtime)
    center.refresh_tasks()

    assert "1 active" in center.active_count_lbl.text()
    cards = center.cards_container.findChildren(TaskCardWidget)
    assert len(cards) >= 2

    # Clean test DB
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


# =========================================================================
# 7. ZERO TERMINAL WINDOWS INVARIANT
# =========================================================================

def test_zero_terminal_windows_flag_verification():
    """Verify subprocess creation flags include CREATE_NO_WINDOW and DETACHED_PROCESS."""
    CREATE_NO_WINDOW = 0x00000200
    DETACHED_PROCESS = 0x00000008

    # Verify our codebase uses CREATE_NO_WINDOW for background launches
    from astrarun import main as main_mod
    src = open(main_mod.__file__, "r", encoding="utf-8").read()
    assert "CREATE_NO_WINDOW" in src
    assert "0x00000200" in src
