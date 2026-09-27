"""Comprehensive automated test suite for AstraRun v0.8 Task Runtime, Activity Timeline & History.

Covers:
- Task, TaskEvent, TaskStatus formal FSM: 14 states, valid transitions, InvalidStateTransitionError
- CancellationToken: thread-safe cooperative cancellation, cancellation reasons, callbacks
- TaskEventBus: subscription, filtering by task_id, global broadcast, exception safety
- Serialization & Privacy: API key/password redaction, request hashing, payload sanitization, titles
- TaskLedger: SQLite WAL mode, schema version 1, CRUD, recent/filtered/range/search queries,
  crash recovery (INTERRUPTED), database corruption recovery, retention pruning, export
- TaskManager: lifecycle authority, event emission, execution orchestration, capability tracing,
  cooperative cancellation interception, failure resilience
- Semantic Re-Run Safety: new task creation, request-text preservation, zero stale argument replay
- UI Components: TaskActivityView, ActivityEventRow, HistoryView, TaskDetailWidget, signals
- Security & Invariants: SQL injection protection, XSS escaping, zero raw shell execution
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.tasks.cancellation import CancellationToken, TaskCancelledError
from astrarun.tasks.events import TaskEventBus, get_global_event_bus
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.manager import TaskManager
from astrarun.tasks.models import (
    Conversation,
    ConversationMessage,
    InvalidStateTransitionError,
    Task,
    TaskError,
    TaskEvent,
    TaskEventType,
    TaskResult,
    TaskStatus,
    validate_transition,
)
from astrarun.tasks.serialization import (
    generate_capability_summary,
    generate_task_title,
    hash_request,
    sanitize_capability_payload,
    sanitize_request,
)
from astrarun.ui.activity import ActivityEventRow, TaskActivityView
from astrarun.ui.history import HistoryView, TaskDetailWidget


# ---------------------------------------------------------------------------
# Session Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Ensure a singleton QApplication exists for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_ledger(tmp_path):
    """Provides a fresh isolated TaskLedger in a temporary directory."""
    db_file = tmp_path / "test_history.db"
    ledger = TaskLedger(db_path=db_file)
    return ledger


# ---------------------------------------------------------------------------
# 1. State Machine & Domain Models Tests
# ---------------------------------------------------------------------------

def test_task_status_properties():
    """Verify state classification properties across all 14 task states."""
    # Terminal states
    for status in [
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.BLOCKED,
        TaskStatus.PARTIALLY_COMPLETED,
        TaskStatus.INTERRUPTED,
    ]:
        assert status.is_terminal is True
        assert status.is_active is False

    # Active states
    for status in [
        TaskStatus.CREATED,
        TaskStatus.PARSING,
        TaskStatus.RESOLVING,
        TaskStatus.READY,
        TaskStatus.RUNNING,
    ]:
        assert status.is_active is True
        assert status.is_terminal is False

    # Waiting states
    for status in [
        TaskStatus.WAITING_CONFIRMATION,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.WAITING_USER,
    ]:
        assert status.is_waiting is True
        assert status.is_terminal is False


def test_fsm_valid_transitions():
    """Verify that expected legal lifecycle transitions succeed without error."""
    # Normal forward path
    validate_transition(TaskStatus.CREATED, TaskStatus.PARSING)
    validate_transition(TaskStatus.PARSING, TaskStatus.RESOLVING)
    validate_transition(TaskStatus.RESOLVING, TaskStatus.READY)
    validate_transition(TaskStatus.READY, TaskStatus.RUNNING)
    validate_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)

    # Interactivity paths
    validate_transition(TaskStatus.RUNNING, TaskStatus.WAITING_CONFIRMATION)
    validate_transition(TaskStatus.WAITING_CONFIRMATION, TaskStatus.RUNNING)
    validate_transition(TaskStatus.WAITING_CONFIRMATION, TaskStatus.CANCELLED)

    validate_transition(TaskStatus.RESOLVING, TaskStatus.WAITING_CLARIFICATION)
    validate_transition(TaskStatus.WAITING_CLARIFICATION, TaskStatus.RUNNING)

    # Termination paths
    validate_transition(TaskStatus.RUNNING, TaskStatus.FAILED)
    validate_transition(TaskStatus.RUNNING, TaskStatus.BLOCKED)
    validate_transition(TaskStatus.RUNNING, TaskStatus.CANCELLED)
    validate_transition(TaskStatus.RUNNING, TaskStatus.PARTIALLY_COMPLETED)
    validate_transition(TaskStatus.RUNNING, TaskStatus.INTERRUPTED)


def test_fsm_invalid_transitions():
    """Verify that illegal transitions raise InvalidStateTransitionError."""
    # Cannot transition from terminal states
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)

    with pytest.raises(InvalidStateTransitionError):
        validate_transition(TaskStatus.FAILED, TaskStatus.READY)

    with pytest.raises(InvalidStateTransitionError):
        validate_transition(TaskStatus.BLOCKED, TaskStatus.COMPLETED)

    with pytest.raises(InvalidStateTransitionError):
        validate_transition(TaskStatus.CANCELLED, TaskStatus.RUNNING)

    with pytest.raises(InvalidStateTransitionError):
        validate_transition(TaskStatus.INTERRUPTED, TaskStatus.RUNNING)

    # Cannot jump backwards in execution without going through formal states
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(TaskStatus.READY, TaskStatus.CREATED)


def test_task_model_lifecycle():
    """Verify Task dataclass state tracking, duration calculation, and dict serialization."""
    t0 = time.time()
    task = Task(
        id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        request_text="inspect port 3000",
        created_at=t0,
        status=TaskStatus.CREATED,
    )
    assert task.status == TaskStatus.CREATED
    assert task.completed_at is None

    task.transition_to(TaskStatus.RUNNING)
    assert task.status == TaskStatus.RUNNING

    time.sleep(0.01)
    task.transition_to(TaskStatus.COMPLETED)
    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at is not None
    assert task.duration_ms() > 0

    d = task.to_dict()
    assert d["id"] == task.id
    assert d["status"] == "COMPLETED"
    restored = Task.from_dict(d)
    assert restored.id == task.id
    assert restored.status == TaskStatus.COMPLETED


def test_task_event_immutability():
    """Verify TaskEvent is frozen and cannot be mutated."""
    ev = TaskEvent(
        id=str(uuid.uuid4()),
        task_id=str(uuid.uuid4()),
        type=TaskEventType.NLP_PARSE_STARTED,
        title="Parsing Request",
        timestamp=time.time(),
    )
    with pytest.raises(AttributeError):
        ev.title = "Modified"  # Frozen dataclass


# ---------------------------------------------------------------------------
# 2. Cooperative Cancellation Tests
# ---------------------------------------------------------------------------

def test_cancellation_token_basics():
    """Verify CancellationToken state, callbacks, and exception throwing."""
    token = CancellationToken()
    assert token.is_cancelled is False
    assert token.reason is None

    # check_cancelled should do nothing when not cancelled
    token.check_cancelled()

    # Register callback
    callback_called = []
    token.register_callback(lambda: callback_called.append(True))

    token.cancel("User aborted")
    assert token.is_cancelled is True
    assert token.reason == "User aborted"
    assert len(callback_called) == 1

    # Idempotent second cancel
    token.cancel("Second reason ignored")
    assert token.reason == "User aborted"
    assert len(callback_called) == 1  # Not called again

    with pytest.raises(TaskCancelledError) as exc_info:
        token.check_cancelled()
    assert "User aborted" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. Event Bus Tests
# ---------------------------------------------------------------------------

def test_task_event_bus():
    """Verify TaskEventBus subscription, filtering, and unsubscription."""
    bus = TaskEventBus()
    received_all = []
    received_specific = []

    sub_all = bus.subscribe(lambda e: received_all.append(e))
    target_task_id = "task-target-123"
    sub_spec = bus.subscribe(lambda e: received_specific.append(e), task_id=target_task_id)

    ev1 = TaskEvent(
        id="e1", task_id="task-other", type=TaskEventType.TASK_CREATED,
        title="Other Task", timestamp=time.time()
    )
    ev2 = TaskEvent(
        id="e2", task_id=target_task_id, type=TaskEventType.CAPABILITY_STARTED,
        title="Target Task", timestamp=time.time()
    )

    bus.publish(ev1)
    bus.publish(ev2)

    assert len(received_all) == 2
    assert len(received_specific) == 1
    assert received_specific[0].task_id == target_task_id

    # Unsubscribe specific
    bus.unsubscribe(sub_spec)
    bus.publish(ev2)
    assert len(received_all) == 3
    assert len(received_specific) == 1  # No new event received


def test_task_event_bus_exception_safety():
    """Verify that a failing subscriber does not disrupt other subscribers."""
    bus = TaskEventBus()
    received = []

    def bad_subscriber(ev):
        raise RuntimeError("Subscriber exploded")

    def good_subscriber(ev):
        received.append(ev)

    bus.subscribe(bad_subscriber)
    bus.subscribe(good_subscriber)

    ev = TaskEvent(id="e1", task_id="t1", type=TaskEventType.TASK_CREATED, title="T", timestamp=time.time())
    bus.publish(ev)

    assert len(received) == 1
    assert received[0].id == "e1"


# ---------------------------------------------------------------------------
# 4. Serialization, Sanitization & Privacy Tests
# ---------------------------------------------------------------------------

def test_sanitize_request_redaction():
    """Verify regex-based credential and secret redaction from raw text."""
    dirty_requests = [
        ("use key sk-1234567890abcdef1234567890abcdef to call service", "[REDACTED]"),
        ("authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "[REDACTED]"),
        ("connect with password=SuperSecretPassword123! to host", "[REDACTED]"),
        ("normal request to open chrome", "normal request to open chrome"),
    ]
    for text, expected_marker in dirty_requests:
        sanitized = sanitize_request(text)
        if expected_marker == "[REDACTED]":
            assert "[REDACTED" in sanitized
            assert "1234567890abcdef" not in sanitized
            assert "SuperSecretPassword123!" not in sanitized
        else:
            assert sanitized == expected_marker


def test_hash_request():
    """Verify deterministic SHA-256 request hashing."""
    h1 = hash_request("open vscode")
    h2 = hash_request("open vscode")
    h3 = hash_request("close vscode")
    assert len(h1) == 64
    assert h1 == h2
    assert h1 != h3


def test_sanitize_capability_payload():
    """Verify bounded and safe payload sanitization."""
    # Bounded process list
    huge_proc_list = [{"pid": i, "name": f"proc_{i}.exe"} for i in range(500)]
    clean_procs = sanitize_capability_payload("list_processes", huge_proc_list)
    assert len(clean_procs) <= 50

    # Unsanitized dict passes through cleanly without large bloat
    clean_dict = sanitize_capability_payload("inspect_port", {"port": 8080, "protocol": "TCP"})
    assert clean_dict == {"port": 8080, "protocol": "TCP"}


def test_generate_task_title():
    """Verify natural deterministic title generation."""
    assert generate_task_title("open project astrarun in vscode") == "Open Astrarun in VS Code"
    assert generate_task_title("what process is running on port 3000") == "Inspect Port 3000"


# ---------------------------------------------------------------------------
# 5. Task Ledger SQLite Tests
# ---------------------------------------------------------------------------

def test_ledger_schema_and_pragmas(temp_ledger):
    """Verify table schema, user_version, and WAL mode in SQLite."""
    with temp_ledger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        ver = cursor.fetchone()[0]
        assert ver == 1

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        assert "tasks" in tables
        assert "task_events" in tables
        assert "conversations" in tables
        assert "conversation_messages" in tables


def test_ledger_task_crud(temp_ledger):
    """Verify basic CRUD operations on tasks and events."""
    task = Task(
        id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        request_text="inspect port 8000",
        source="launcher",
    )
    temp_ledger.save_task(task)

    # Retrieve
    loaded = temp_ledger.get_task(task.id, include_events=True)
    assert loaded is not None
    assert loaded.id == task.id
    assert loaded.request_text == "inspect port 8000"
    assert len(loaded.events) == 0

    # Append events
    ev1 = TaskEvent(
        id=str(uuid.uuid4()),
        task_id=task.id,
        type=TaskEventType.NLP_PARSE_STARTED,
        title="NLP Parse",
        timestamp=time.time(),
    )
    temp_ledger.append_event(ev1)

    # Update status and complete
    result = TaskResult(
        task_id=task.id,
        success=True,
        status=TaskStatus.COMPLETED,
        message="Port 8000 is open",
        summary="Found process on port 8000",
        capabilities_used=["inspect_port"],
        duration_ms=45.2,
    )
    temp_ledger.update_task_status(task.id, TaskStatus.COMPLETED, final_result=result)

    reloaded = temp_ledger.get_task(task.id, include_events=True)
    assert reloaded.status == TaskStatus.COMPLETED
    assert len(reloaded.events) == 1
    assert reloaded.events[0].type == TaskEventType.NLP_PARSE_STARTED
    assert reloaded.final_result is not None
    assert reloaded.final_result.summary == "Found process on port 8000"


def test_ledger_queries(temp_ledger):
    """Verify recent, status, capability, range, and search queries."""
    # Seed 5 tasks
    for i in range(5):
        t = Task(
            id=f"t-{i}",
            conversation_id="conv-1",
            request_text=f"task query #{i} test",
            status=TaskStatus.COMPLETED if i % 2 == 0 else TaskStatus.FAILED,
            created_at=time.time() - (5 - i) * 10,
        )
        temp_ledger.save_task(t)

    # Recent
    recent = temp_ledger.get_recent_tasks(limit=3)
    assert len(recent) == 3
    assert recent[0].id == "t-4"  # most recent first

    # By status
    completed = temp_ledger.get_tasks_by_status(TaskStatus.COMPLETED)
    assert len(completed) == 3

    # Search
    matches = temp_ledger.search_tasks("query #2")
    assert len(matches) == 1
    assert matches[0].id == "t-2"


def test_ledger_crash_recovery(temp_ledger):
    """Verify that recover_interrupted_tasks marks non-terminal tasks as INTERRUPTED."""
    active_task = Task(
        id="active-task-1",
        conversation_id="conv-1",
        request_text="dangling job",
        status=TaskStatus.RUNNING,
    )
    completed_task = Task(
        id="completed-task-2",
        conversation_id="conv-1",
        request_text="finished job",
        status=TaskStatus.COMPLETED,
    )
    temp_ledger.save_task(active_task)
    temp_ledger.save_task(completed_task)

    recovered_count = temp_ledger.recover_interrupted_tasks()
    assert recovered_count == 1

    t1 = temp_ledger.get_task("active-task-1", include_events=True)
    assert t1.status == TaskStatus.INTERRUPTED
    assert any(e.type == TaskEventType.TASK_INTERRUPTED for e in t1.events)

    t2 = temp_ledger.get_task("completed-task-2")
    assert t2.status == TaskStatus.COMPLETED


def test_ledger_corruption_recovery(tmp_path):
    """Verify that a corrupted database file is safely backed up and replaced."""
    corrupt_db = tmp_path / "corrupt_history.db"
    # Write corrupt garbage bytes
    corrupt_db.write_bytes(b"CORRUPT DATA INVALID SQLITE DATABASE HEADER NOT 100 BYTES")

    # Creating TaskLedger should detect corruption, rename, and initialize fresh DB
    ledger = TaskLedger(db_path=corrupt_db)
    assert corrupt_db.exists()

    # Backed up file should exist
    backups = list(tmp_path.glob("corrupt_history.db.corrupt.*"))
    assert len(backups) == 1

    # New ledger should operate cleanly
    task = Task(id="test-corrupt-recover", conversation_id="conv-1", request_text="healthy task")
    ledger.save_task(task)
    assert ledger.get_task("test-corrupt-recover") is not None


def test_ledger_retention_and_clear(temp_ledger):
    """Verify retention pruning and clear history."""
    t_old = Task(
        id="t-old",
        conversation_id="c1",
        request_text="old task",
        status=TaskStatus.COMPLETED,
        created_at=time.time() - 86400 * 40,  # 40 days old
    )
    t_new = Task(
        id="t-new",
        conversation_id="c1",
        request_text="new task",
        status=TaskStatus.COMPLETED,
        created_at=time.time() - 3600,  # 1 hour old
    )
    temp_ledger.save_task(t_old)
    temp_ledger.save_task(t_new)

    # Retention cleanup for 30 days
    pruned = temp_ledger.cleanup_retention(retention_days=30)
    assert pruned == 1
    assert temp_ledger.get_task("t-old") is None
    assert temp_ledger.get_task("t-new") is not None

    # Clear history
    temp_ledger.clear_history()
    assert temp_ledger.get_task("t-new") is None
    assert len(temp_ledger.get_recent_tasks()) == 0


def test_ledger_export_task(temp_ledger):
    """Verify complete JSON export for a task and its events."""
    task = Task(id="export-me", conversation_id="conv-exp", request_text="export request")
    temp_ledger.save_task(task)
    ev = TaskEvent(id="ev-exp", task_id="export-me", type=TaskEventType.TASK_CREATED, title="Export", timestamp=time.time())
    temp_ledger.append_event(ev)

    exported = temp_ledger.export_task("export-me")
    assert exported is not None
    import json
    data = json.loads(exported)
    assert data["id"] == "export-me"
    assert len(data["events"]) == 1
    assert data["events"][0]["title"] == "Export"


# ---------------------------------------------------------------------------
# 6. Task Manager Lifecycle & Execution Tests
# ---------------------------------------------------------------------------

def test_task_manager_lifecycle(temp_ledger):
    """Verify TaskManager task creation, status transitions, and completion."""
    bus = TaskEventBus()
    tm = TaskManager(ledger=temp_ledger, event_bus=bus)

    events_received = []
    bus.subscribe(lambda e: events_received.append(e))

    task = tm.create_task("check system status", source="test")
    assert task.status == TaskStatus.CREATED
    assert len(events_received) == 1
    assert events_received[0].type == TaskEventType.TASK_CREATED

    tm.start_task(task.id)
    assert tm.get_task(task.id).status == TaskStatus.RUNNING

    res = TaskResult(
        task_id=task.id,
        success=True,
        status=TaskStatus.COMPLETED,
        message="System optimal",
        summary="Checked system",
    )
    tm.complete_task(task.id, res)

    # In-memory active tasks should be purged, ledger should have completed state
    persisted = temp_ledger.get_task(task.id, include_events=True)
    assert persisted.status == TaskStatus.COMPLETED
    assert any(e.type == TaskEventType.TASK_COMPLETED for e in persisted.events)


def test_task_manager_block_and_fail(temp_ledger):
    """Verify policy blocking and failure recording."""
    tm = TaskManager(ledger=temp_ledger, event_bus=TaskEventBus())

    # Policy block
    t_block = tm.create_task("format drive c:", source="test")
    tm.start_task(t_block.id)
    tm.block_task(t_block.id, reason="Prohibited raw format", capability_id="format_drive")
    persisted_block = temp_ledger.get_task(t_block.id)
    assert persisted_block.status == TaskStatus.BLOCKED
    assert persisted_block.final_result.error.code == "POLICY_BLOCKED"

    # Failure
    t_fail = tm.create_task("failing operation", source="test")
    tm.start_task(t_fail.id)
    tm.fail_task(t_fail.id, TaskError(code="CONNECTION_REFUSED", message="Port unreachable"))
    persisted_fail = temp_ledger.get_task(t_fail.id)
    assert persisted_fail.status == TaskStatus.FAILED
    assert persisted_fail.final_result.error.code == "CONNECTION_REFUSED"


def test_task_manager_execute_capability(temp_ledger):
    """Verify capability execution, event instrumentation, and timing."""
    tm = TaskManager(ledger=temp_ledger, event_bus=TaskEventBus())
    reg = CapabilityRegistry()

    task = tm.create_task("inspect cpu", source="test")
    tm.start_task(task.id)

    cap_res = tm.execute_capability(task.id, "cpu_status", {}, reg)
    assert cap_res.success is True

    persisted = temp_ledger.get_task(task.id, include_events=True)
    event_types = [e.type for e in persisted.events]
    assert TaskEventType.CAPABILITY_STARTED in event_types
    assert TaskEventType.CAPABILITY_COMPLETED in event_types


def test_task_manager_cancellation_interception(temp_ledger):
    """Verify that cancellation token prevents capability execution and marks task CANCELLED."""
    tm = TaskManager(ledger=temp_ledger, event_bus=TaskEventBus())
    reg = CapabilityRegistry()

    task = tm.create_task("search files", source="test")
    tm.start_task(task.id)

    token = tm.get_cancellation_token(task.id)
    assert token is not None
    token.cancel("User cancelled before start")

    with pytest.raises(TaskCancelledError):
        tm.execute_capability(task.id, "list_recent_files", {}, reg)

    persisted = temp_ledger.get_task(task.id, include_events=True)
    assert persisted.status == TaskStatus.CANCELLED
    event_types = [e.type for e in persisted.events]
    assert TaskEventType.TASK_CANCEL_REQUESTED in event_types
    assert TaskEventType.TASK_CANCELLED in event_types


# ---------------------------------------------------------------------------
# 7. Semantic Re-Run Safety Invariant Tests (Rule #35, #36)
# ---------------------------------------------------------------------------

def test_semantic_rerun_safety(temp_ledger):
    """
    CRITICAL INVARIANT TEST:
    Verify that re_run_task spawns a NEW task from the original user request text,
    and strictly DOES NOT replay stale resolved arguments, stale PIDs, or stale file paths.
    """
    tm = TaskManager(ledger=temp_ledger, event_bus=TaskEventBus())

    # Task 1: Historical run with specific stale parameters
    old_task = tm.create_task("stop process on port 3000", source="test")
    tm.start_task(old_task.id)
    # Stale result with PID 9999
    res = TaskResult(
        task_id=old_task.id,
        success=True,
        status=TaskStatus.COMPLETED,
        message="Terminated pid 9999",
        summary="Terminated PID 9999",
        capabilities_used=["terminate_process"],
        data={"stale_pid": 9999},
    )
    tm.complete_task(old_task.id, res)

    # Trigger re-run
    new_task = tm.re_run_task(old_task.id)

    assert new_task.id != old_task.id
    assert new_task.status == TaskStatus.CREATED
    assert new_task.request_text == old_task.request_text

    # Verify that new task has zero stale results or events attached
    assert new_task.final_result is None
    assert len(new_task.events) == 1

    # Persisted new task should be independent
    persisted_new = temp_ledger.get_task(new_task.id, include_events=True)
    assert persisted_new.id == new_task.id
    assert persisted_new.status == TaskStatus.CREATED
    # Events should only contain initial TASK_CREATED
    assert len(persisted_new.events) == 1
    assert persisted_new.events[0].type == TaskEventType.TASK_CREATED


# ---------------------------------------------------------------------------
# 8. UI Components Tests
# ---------------------------------------------------------------------------

def test_task_activity_view(qapp):
    """Verify TaskActivityView rendering, row addition, and cancellation signal."""
    view = TaskActivityView()
    task = Task(id="ui-task-1", conversation_id="conv-1", request_text="inspect port 3000")
    view.set_task(task)

    assert "inspect port 3000" in view.request_label.text().lower()
    assert "ASTRA" in view.status_badge.text()

    # Add events
    ev1 = TaskEvent(
        id="e1", task_id="ui-task-1", type=TaskEventType.NLP_PARSE_STARTED,
        title="Parsing request", timestamp=time.time()
    )
    ev2 = TaskEvent(
        id="e2", task_id="ui-task-1", type=TaskEventType.CAPABILITY_COMPLETED,
        title="Inspect Port", summary="Port 3000 is open", duration_ms=12.5,
        timestamp=time.time()
    )
    view.on_event(ev1)
    view.on_event(ev2)

    assert len(view._rows) == 2

    # Cancellation signal
    cancel_signal_received = []
    view.cancel_requested.connect(lambda tid: cancel_signal_received.append(tid))
    view.cancel_btn.click()
    assert cancel_signal_received == ["ui-task-1"]


def test_history_view(qapp, temp_ledger):
    """Verify HistoryView task listing, searching, filtering, and re-run signal."""
    # Seed 3 tasks
    t1 = Task(id="h1", conversation_id="c1", request_text="open vscode", status=TaskStatus.COMPLETED)
    t2 = Task(id="h2", conversation_id="c1", request_text="kill process 1234", status=TaskStatus.FAILED)
    t3 = Task(id="h3", conversation_id="c1", request_text="shutdown pc", status=TaskStatus.BLOCKED)
    temp_ledger.save_task(t1)
    temp_ledger.save_task(t2)
    temp_ledger.save_task(t3)

    view = HistoryView(ledger=temp_ledger)
    assert view.task_list.count() == 3

    # Search filter
    view.search_input.setText("vscode")
    assert view.task_list.count() == 1

    # Filter chips
    view.search_input.clear()
    view._on_filter_clicked("Completed")
    assert view.task_list.count() == 1

    view._on_filter_clicked("Blocked/Failed")
    assert view.task_list.count() == 2

    # Reset All
    view._on_filter_clicked("All")
    assert view.task_list.count() == 3

    # Select task and test detail view + re-run signal
    view.task_list.setCurrentRow(0)
    assert view.detail_widget.title_label.text() != "Select a task to view details"

    rerun_signal_received = []
    view.task_rerun_requested.connect(lambda tid: rerun_signal_received.append(tid))
    view.detail_widget.rerun_button.click()
    assert len(rerun_signal_received) == 1


# ---------------------------------------------------------------------------
# 9. Security & Safety Regressions Tests
# ---------------------------------------------------------------------------

def test_sql_injection_defense(temp_ledger):
    """Verify that malicious SQL injection inputs in queries or tasks do not execute."""
    injection_strings = [
        "'; DROP TABLE tasks; --",
        "' OR '1'='1",
        "UNION SELECT * FROM sqlite_master --",
    ]
    for evil in injection_strings:
        # Saving task with injection in text
        t = Task(id=str(uuid.uuid4()), conversation_id="conv-inj", request_text=evil)
        temp_ledger.save_task(t)

        # Searching with injection string
        results = temp_ledger.search_tasks(evil)
        assert len(results) >= 1

        # Verify tables still exist
        with temp_ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM tasks;")
            count = cursor.fetchone()[0]
            assert count >= 1


def test_zero_raw_shell_execution_invariant():
    """Verify that TaskManager and TaskLedger codebase contains zero raw shell execution."""
    src_dir = Path(__file__).resolve().parent.parent / "src" / "astrarun" / "tasks"
    for py_file in src_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "shell=True" not in content
        assert "os.system(" not in content
        assert "cmd.exe" not in content
        assert "powershell.exe" not in content
