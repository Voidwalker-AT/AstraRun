"""Comprehensive verification tests for RC0.1 Durable User Pause/Resume and Capability Discovery.

Tests verify:
1. Durable user pause (RUNNING -> PAUSING -> PAUSED_USER_REQUEST) and audit event flow.
2. Checkpoint persistence and rehydration across runtime restarts.
3. Pre-resumption state reconciliation ("RESUME IS RECONCILIATION, NOT UNPAUSE").
4. External progress discovery (download completed externally during pause).
5. Human conflict classification (merge conflict markers or conflicting file edits).
6. Goal already completed externally (transitions directly to COMPLETED).
7. Power wake composition (system wake does NOT resume user-paused tasks).
8. Existing capability resolver (exact match reuse for Spark/Qwen in E:\\AI_Models\\GGUF).
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import pytest

from astrarun.discovery.candidates import CompatibilityStatus, ExistingCapabilityCandidate
from astrarun.discovery.resolver import ExistingCapabilityResolver
from astrarun.power.events import DisplayState, PowerEventType, PowerState, ResumeVerdict as PowerResumeVerdict
from astrarun.power.manager import PowerLifecycleManager
from astrarun.tasks.checkpoints import TaskCheckpoint
from astrarun.tasks.events import TaskEventBus
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.models import Task, TaskEvent, TaskEventType, TaskStatus
from astrarun.tasks.reconciliation import (
    HumanChangeClassification,
    ResumeAssessment,
    ResumeVerdict,
    TaskReconciliationEngine,
)
from astrarun.tasks.runtime import PlanStep, TaskRuntime


@pytest.fixture
def temp_ledger(tmp_path: Path) -> TaskLedger:
    db_file = tmp_path / "test_tasks.db"
    return TaskLedger(db_path=str(db_file))


@pytest.fixture
def event_bus() -> TaskEventBus:
    return TaskEventBus()


def test_durable_user_pause_lifecycle(temp_ledger: TaskLedger, event_bus: TaskEventBus):
    """Verify RUNNING -> PAUSING -> PAUSED_USER_REQUEST atomic transition and audit events."""
    runtime = TaskRuntime(ledger=temp_ledger, event_bus=event_bus)

    received_events = []
    event_bus.subscribe(lambda ev: received_events.append(ev))

    task = runtime.create_and_enqueue_task("Analyze quarterly report PDF")
    task.transition_to(TaskStatus.RUNNING)
    temp_ledger.save_task(task)

    # User pauses task
    runtime.pause_task(task.id, is_user_takeover=False, reason="USER_REQUEST")

    # Verify task state
    updated = runtime.get_task(task.id)
    assert updated is not None
    assert updated.status == TaskStatus.PAUSED_USER_REQUEST

    # Verify checkpoint
    chk = temp_ledger.get_latest_checkpoint(task.id)
    assert chk is not None
    assert chk.status == TaskStatus.PAUSED_USER_REQUEST.value
    assert chk.pause_reason == "USER_REQUEST"
    assert chk.pause_timestamp is not None

    # Verify audit events emitted
    event_types = [ev.type for ev in received_events]
    assert TaskEventType.USER_PAUSE_REQUESTED in event_types
    assert TaskEventType.TASK_PAUSING in event_types
    assert TaskEventType.TASK_PAUSED in event_types


def test_paused_task_survives_runtime_restart(temp_ledger: TaskLedger, event_bus: TaskEventBus):
    """Verify task in PAUSED_USER_REQUEST survives complete app/runtime reinitialization."""
    runtime1 = TaskRuntime(ledger=temp_ledger, event_bus=event_bus)
    task = runtime1.create_and_enqueue_task("Long running simulation")
    task.transition_to(TaskStatus.RUNNING)
    temp_ledger.save_task(task)

    runtime1.pause_task(task.id)
    assert runtime1.get_task(task.id).status == TaskStatus.PAUSED_USER_REQUEST

    # Simulate application restart with new runtime instance pointing to same SQLite ledger
    runtime2 = TaskRuntime(ledger=temp_ledger, event_bus=event_bus)
    rehydrated = runtime2.get_task(task.id)

    assert rehydrated is not None
    assert rehydrated.status == TaskStatus.PAUSED_USER_REQUEST
    assert not rehydrated.status.is_terminal
    assert rehydrated.status.is_waiting


def test_resume_reconciliation_unchanged(temp_ledger: TaskLedger, event_bus: TaskEventBus, tmp_path: Path):
    """Verify clean resumption when environment is unchanged."""
    runtime = TaskRuntime(ledger=temp_ledger, event_bus=event_bus)
    received_events = []
    event_bus.subscribe(lambda ev: received_events.append(ev))

    task = runtime.create_and_enqueue_task("Generate documentation")
    task.transition_to(TaskStatus.RUNNING)
    temp_ledger.save_task(task)

    # Create dummy artifact
    art = tmp_path / "output.md"
    art.write_text("# Documentation", encoding="utf-8")

    chk = runtime.create_checkpoint(task.id, "step_1", ["step_1"], {}, [art])
    runtime.pause_task(task.id)

    # Resume task
    assessment = runtime.resume_task(task.id)

    assert assessment.verdict == ResumeVerdict.UNCHANGED
    assert str(art) in assessment.surviving_artifacts
    assert runtime.get_task(task.id).status == TaskStatus.RUNNING

    ev_types = [ev.type for ev in received_events]
    assert TaskEventType.RESUME_REQUESTED in ev_types
    assert TaskEventType.RESUME_RECONCILIATION_STARTED in ev_types
    assert TaskEventType.TASK_RESUMED in ev_types


def test_resume_reconciliation_external_progress(temp_ledger: TaskLedger, event_bus: TaskEventBus, tmp_path: Path):
    """Verify detection when human or external process finished a download while paused."""
    runtime = TaskRuntime(ledger=temp_ledger, event_bus=event_bus)
    received_events = []
    event_bus.subscribe(lambda ev: received_events.append(ev))

    task = runtime.create_and_enqueue_task("Download large dataset")
    task.transition_to(TaskStatus.RUNNING)
    temp_ledger.save_task(task)

    target_file = tmp_path / "dataset.zip"
    target_file.write_text("partial", encoding="utf-8")

    chk = TaskCheckpoint(
        task_id=task.id,
        goal=task.request_text,
        status=TaskStatus.PAUSED_USER_REQUEST.value,
        completed_step_ids=["step_prep"],
        recoverable_handles={
            "download_dataset": {
                "target_file": str(target_file),
                "expected_size": 20,
                "step_id": "step_download",
            }
        },
    )
    temp_ledger.save_checkpoint(chk)
    runtime.pause_task(task.id)

    # While paused, user/browser completes the download externally!
    target_file.write_text("01234567890123456789", encoding="utf-8")  # exactly 20 bytes

    assessment = runtime.resume_task(task.id)

    assert assessment.verdict == ResumeVerdict.PROGRESS_ADVANCED_EXTERNALLY
    assert len(assessment.externally_completed_work) == 1
    assert assessment.plan_revision is not None
    assert "step_download" in assessment.plan_revision.preserved_completed_steps

    ev_types = [ev.type for ev in received_events]
    assert TaskEventType.RESUME_EXTERNAL_PROGRESS_FOUND in ev_types
    assert TaskEventType.PLAN_REVISED_AFTER_PAUSE in ev_types


def test_resume_reconciliation_human_conflict(temp_ledger: TaskLedger, event_bus: TaskEventBus, tmp_path: Path):
    """Verify human conflicting modification halts auto-resumption and requests clarification."""
    runtime = TaskRuntime(ledger=temp_ledger, event_bus=event_bus)
    received_events = []
    event_bus.subscribe(lambda ev: received_events.append(ev))

    task = runtime.create_and_enqueue_task("Refactor authentication module")
    task.transition_to(TaskStatus.RUNNING)
    temp_ledger.save_task(task)

    target_file = tmp_path / "auth.py"
    target_file.write_text("def authenticate(): return True\n", encoding="utf-8")

    chk = runtime.create_checkpoint(task.id, "step_auth", ["step_auth"], {}, [target_file])
    runtime.pause_task(task.id)

    # Human injects conflict markers while paused
    target_file.write_text("<<<<<<< HEAD\ndef authenticate(): pass\n=======\nCONFLICT: manual edit\n>>>>>>>\n", encoding="utf-8")

    assessment = runtime.resume_task(task.id)

    assert assessment.verdict == ResumeVerdict.REQUIRES_USER
    assert assessment.requires_user_confirmation is True
    assert len(assessment.conflicts) > 0
    # Task must transition to WAITING_CLARIFICATION rather than running over user changes
    assert runtime.get_task(task.id).status == TaskStatus.WAITING_CLARIFICATION

    ev_types = [ev.type for ev in received_events]
    assert TaskEventType.RESUME_CONFLICT_FOUND in ev_types
    assert TaskEventType.CLARIFICATION_REQUESTED in ev_types


def test_resume_reconciliation_goal_already_completed(temp_ledger: TaskLedger, event_bus: TaskEventBus, tmp_path: Path):
    """Verify task transitions directly to COMPLETED when goal was achieved during pause."""
    runtime = TaskRuntime(ledger=temp_ledger, event_bus=event_bus)
    received_events = []
    event_bus.subscribe(lambda ev: received_events.append(ev))

    task = runtime.create_and_enqueue_task("Create final release package")
    task.transition_to(TaskStatus.RUNNING)
    temp_ledger.save_task(task)

    package_file = tmp_path / "package.exe"
    chk = runtime.create_checkpoint(task.id, "step_pkg", [], {}, [])
    runtime.pause_task(task.id)

    # Human creates the package file manually while paused
    package_file.write_bytes(b"RELEASE_BINARY")

    def goal_verifier(checkpoint, artifacts):
        return package_file.exists()

    assessment = runtime.resume_task(task.id, goal_verification_func=goal_verifier)

    assert assessment.verdict == ResumeVerdict.GOAL_ALREADY_COMPLETED
    assert runtime.get_task(task.id).status == TaskStatus.COMPLETED

    ev_types = [ev.type for ev in received_events]
    assert TaskEventType.TASK_COMPLETED in ev_types


def test_power_wake_composition_does_not_resume_user_paused_task(temp_ledger: TaskLedger):
    """Verify system wake does NOT auto-resume a task that was explicitly paused by the user."""
    pm = PowerLifecycleManager(ledger=None)
    task = Task(id="task_paused_user", conversation_id="conv_user", request_text="Manual analysis", status=TaskStatus.PAUSED_USER_REQUEST)
    pm.register_task(task)

    # System goes to sleep
    pm.handle_suspend()
    assert task.status == TaskStatus.PAUSED_USER_REQUEST

    # System wakes up
    assessments = pm.handle_resume(reason="WAKE_FROM_SLEEP")

    # Task must remain PAUSED_USER_REQUEST, not auto-resumed!
    assert task.status == TaskStatus.PAUSED_USER_REQUEST
    # No recovery assessment should have scheduled it for autonomous running
    assert all(a.task_id != "task_paused_user" for a in assessments)


def test_existing_capability_discovery_exact_match():
    """Verify ExistingCapabilityResolver finds local Spark & Qwen GGUF models as EXACT_MATCH."""
    resolver = ExistingCapabilityResolver()
    models = resolver.discover_models()

    assert "spark-x2.5-1.7b-q4" in models
    assert "qwen2.5-coder-1.5b-q4" in models

    spark = models["spark-x2.5-1.7b-q4"]
    qwen = models["qwen2.5-coder-1.5b-q4"]

    assert spark.status == CompatibilityStatus.EXACT_MATCH
    assert spark.is_recommended is True
    assert "0 MB download" in spark.reuse_action
    assert spark.path is not None and spark.path.exists()

    assert qwen.status == CompatibilityStatus.EXACT_MATCH
    assert qwen.is_recommended is True
    assert "0 MB download" in qwen.reuse_action
    assert qwen.path is not None and qwen.path.exists()

    # Tools check
    tools = resolver.discover_tools()
    assert "git" in tools
    assert tools["git"].is_available is True

    # Invariant: internal libraries are NEVER external capability candidates
    for forbidden in ("pyside6", "numpy", "pydantic", "sqlite", "httpx", "pillow", "onnxruntime"):
        assert forbidden not in tools
        assert forbidden not in models
