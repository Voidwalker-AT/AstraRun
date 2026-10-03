"""Comprehensive Unit & Regression Tests for Milestone 7A: Adaptive Execution & Resilience.

Validates:
1. Invariant checking across process, file, hash, content, workspace, and network targets.
2. TaskWatchSet scoped observation (monitoring only what matters).
3. Disturbance tracking, human intervention classification, and event logging.
4. 'Do Not Fight The User' protocol (stopping auto-reopen when user closes app twice).
5. Bounded recovery budgets (max 2 attempts, preventing infinite loops).
6. Durable TaskCheckpoints, SHA-256 artifact hashing, and SecretBroker scrubbing.
7. TaskLedger checkpoint storage, retrieval, and crash recovery discovery.
8. Adaptive plan execution with precondition verification, recovery, and file conflict safety.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astrarun.tasks.checkpoints import PlanRevision, RecoveryPlan, TaskCheckpoint
from astrarun.tasks.disturbances import (
    DisturbanceEvent,
    DisturbanceTracker,
    DisturbanceType,
    RecoveryBudget,
)
from astrarun.tasks.invariants import (
    InvariantImportance,
    InvariantType,
    TaskInvariant,
    TaskWatchSet,
)
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.models import (
    InvalidStateTransitionError,
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
    validate_transition,
)
from astrarun.tasks.runtime import PlanStep, TaskRuntime


# =============================================================================
# 1. Invariant Engine Tests
# =============================================================================

def test_invariant_process_running():
    """Verify PROCESS_RUNNING invariant against real process and nonexistent process."""
    # Current python process is running
    inv_true = TaskInvariant(
        type=InvariantType.PROCESS_RUNNING,
        target="python.exe" if sys.platform == "win32" else "python",
        expected_state=True,
    )
    valid, observed, msg = inv_true.check()
    assert valid is True
    assert len(observed) > 0
    assert "running: True" in msg

    # Nonexistent process is not running
    inv_false = TaskInvariant(
        type=InvariantType.PROCESS_RUNNING,
        target="nonexistent_process_xyz_9999.exe",
        expected_state=True,
    )
    valid, observed, msg = inv_false.check()
    assert valid is False
    assert len(observed) == 0


def test_invariant_file_and_hash(tmp_path):
    """Verify FILE_EXISTS, FILE_HASH_MATCHES, and FILE_CONTAINS_CHANGE."""
    test_file = tmp_path / "test_artifact.txt"
    test_file.write_text("Hello AstraRun Adaptive World 2026!", encoding="utf-8")

    # 1. File exists
    inv_exists = TaskInvariant(
        type=InvariantType.FILE_EXISTS,
        target=str(test_file),
        expected_state=True,
    )
    valid, _, _ = inv_exists.check()
    assert valid is True

    # 2. File hash matches
    expected_sha = hashlib.sha256(test_file.read_bytes()).hexdigest()
    inv_hash = TaskInvariant(
        type=InvariantType.FILE_HASH_MATCHES,
        target=str(test_file),
        expected_state=expected_sha,
    )
    valid, observed_hash, _ = inv_hash.check()
    assert valid is True
    assert observed_hash == expected_sha

    # 3. File hash mismatch after modification
    inv_bad_hash = TaskInvariant(
        type=InvariantType.FILE_HASH_MATCHES,
        target=str(test_file),
        expected_state="0000000000000000000000000000000000000000000000000000000000000000",
    )
    valid, _, _ = inv_bad_hash.check()
    assert valid is False

    # 4. File contains change
    inv_contains = TaskInvariant(
        type=InvariantType.FILE_CONTAINS_CHANGE,
        target=str(test_file),
        expected_state="Adaptive World",
    )
    valid, _, _ = inv_contains.check()
    assert valid is True

    inv_missing = TaskInvariant(
        type=InvariantType.FILE_CONTAINS_CHANGE,
        target=str(test_file),
        expected_state="Nonexistent String XYZ",
    )
    valid, _, _ = inv_missing.check()
    assert valid is False


def test_invariant_workspace_and_download(tmp_path):
    """Verify WORKSPACE_AVAILABLE and DOWNLOAD_PROGRESSING."""
    # Workspace check
    inv_ws = TaskInvariant(
        type=InvariantType.WORKSPACE_AVAILABLE,
        target=str(tmp_path),
        expected_state=True,
    )
    valid, _, _ = inv_ws.check()
    assert valid is True

    # Download progressing with .part file
    download_target = tmp_path / "big_dataset.zip"
    part_file = tmp_path / "big_dataset.zip.part"
    part_file.write_bytes(b"chunk1_data")

    inv_dl = TaskInvariant(
        type=InvariantType.DOWNLOAD_PROGRESSING,
        target=str(download_target),
        expected_state=True,
    )
    valid, size1, _ = inv_dl.check()
    assert valid is True
    assert size1 == len(b"chunk1_data")

    # Increase download size
    part_file.write_bytes(b"chunk1_data_chunk2_data")
    valid2, size2, _ = inv_dl.check()
    assert valid2 is True
    assert size2 > size1


# =============================================================================
# 2. TaskWatchSet Scoping Tests
# =============================================================================

def test_task_watch_set(tmp_path):
    """Verify TaskWatchSet scopes observation to active task targets only."""
    watch_set = TaskWatchSet(task_id="task-watch-1")

    p = tmp_path / "watched.txt"
    p.write_text("watched content")

    inv_file = TaskInvariant(type=InvariantType.FILE_EXISTS, target=str(p))
    inv_proc = TaskInvariant(type=InvariantType.PROCESS_RUNNING, target="notepad.exe")

    watch_set.add_invariant(inv_file)
    watch_set.add_invariant(inv_proc)

    assert p in watch_set.watched_files
    assert "notepad.exe" in watch_set.watched_processes

    all_checks = watch_set.check_all()
    assert len(all_checks) == 2

    # Broken invariants filter
    broken = watch_set.get_broken_invariants()
    # At least notepad is likely not running or broken
    assert any(b[0].target == "notepad.exe" for b in broken)


# =============================================================================
# 3. Disturbance Tracking & Human Intervention Classification
# =============================================================================

def test_disturbance_tracker_and_classification():
    """Verify disturbance event recording and human intervention flagging."""
    tracker = DisturbanceTracker(task_id="task-dist-1")

    ev1 = tracker.record_disturbance(
        disturbance_type=DisturbanceType.USER_INPUT_TAKEOVER,
        observed_before="IDLE",
        observed_after="USER_ACTIVE",
        affected_invariants=["mouse", "keyboard"],
        is_human_intervention=True,
        details="User moved mouse during autonomous execution",
    )
    assert ev1.is_human_intervention is True
    assert len(tracker.history) == 1

    ev2 = tracker.record_disturbance(
        disturbance_type=DisturbanceType.APPLICATION_CRASHED,
        observed_before=1234,
        observed_after=0,
        affected_invariants=["editor.exe"],
        is_human_intervention=False,
        details="Process exited with code -1073741819",
    )
    assert ev2.is_human_intervention is False
    assert len(tracker.history) == 2

    d = ev1.to_dict()
    assert d["disturbance_type"] == "USER_INPUT_TAKEOVER"
    assert d["is_human_intervention"] is True


# =============================================================================
# 4. 'Do Not Fight The User' Protocol Tests
# =============================================================================

def test_do_not_fight_the_user():
    """Verify that closing a required app twice stops auto-reopen and prompts user."""
    tracker = DisturbanceTracker(task_id="task-fight-user-1")

    # First closure: should auto-reopen (ask_user is False)
    tracker.record_disturbance(
        disturbance_type=DisturbanceType.USER_CLOSED_REQUIRED_WINDOW,
        observed_before=True,
        observed_after=False,
        affected_invariants=["notepad.exe"],
        is_human_intervention=True,
        details="User closed notepad",
    )
    assert tracker.should_ask_user_instead_of_reopening("notepad.exe") is False

    # Second closure: should NOT auto-reopen, must ask user!
    tracker.record_disturbance(
        disturbance_type=DisturbanceType.USER_CLOSED_REQUIRED_WINDOW,
        observed_before=True,
        observed_after=False,
        affected_invariants=["notepad.exe"],
        is_human_intervention=True,
        details="User closed notepad again",
    )
    assert tracker.should_ask_user_instead_of_reopening("notepad.exe") is True

    # Clarification prompt structure
    prompt = tracker.get_user_conflict_prompt("notepad.exe")
    assert "Astra needs notepad.exe" in prompt["title"]
    assert "You closed it twice" in prompt["message"]
    option_ids = [opt["id"] for opt in prompt["options"]]
    assert "resume_with_target" in option_ids
    assert "continue_alternative" in option_ids
    assert "cancel_task" in option_ids


# =============================================================================
# 5. Recovery Budget Bounds Tests
# =============================================================================

def test_recovery_budget_bounds():
    """Verify recovery budget limits attempts to prevent infinite retry loops."""
    budget = RecoveryBudget(
        task_id="task-budget-1",
        max_auto_attempts_per_strategy=2,
        max_total_recovery_attempts=4,
    )

    # Strategy: reopen_app
    assert budget.can_attempt_recovery("reopen_app", "calc.exe") is True
    att1 = budget.record_attempt("reopen_app", "calc.exe")
    assert att1 == 1

    assert budget.can_attempt_recovery("reopen_app", "calc.exe") is True
    att2 = budget.record_attempt("reopen_app", "calc.exe")
    assert att2 == 2

    # 3rd attempt for same strategy must be denied!
    assert budget.can_attempt_recovery("reopen_app", "calc.exe") is False

    # Different strategy can still attempt within total budget
    assert budget.can_attempt_recovery("wait_network") is True
    budget.record_attempt("wait_network")
    budget.record_attempt("wait_network")

    # Total budget now reached (4 attempts)
    assert budget.can_attempt_recovery("any_strategy") is False


# =============================================================================
# 6. Durable Checkpoints & Secret Scrubbing Tests
# =============================================================================

def test_checkpoint_artifact_hashing_and_scrubbing(tmp_path):
    """Verify checkpoint records SHA-256 artifact hashes and scrubs secrets."""
    art_file = tmp_path / "output_report.md"
    art_file.write_text("# AstraRun Report\nAll invariants passed.", encoding="utf-8")

    checkpoint = TaskCheckpoint(
        task_id="task-chk-1",
        current_step_id="step_write_report",
        completed_step_ids=["step_init", "step_process"],
        important_outputs={
            "summary": "Report generated successfully",
            "api_key": "Bearer astra_live_secret_key_1234567890abcdef",
        },
    )

    # Hash artifact
    digest = checkpoint.record_artifact(art_file)
    assert digest is not None
    assert str(art_file) in checkpoint.artifact_hashes
    assert checkpoint.artifact_hashes[str(art_file)] == digest

    # Serialize to dictionary and verify secret scrubbing
    serialized = checkpoint.to_dict()
    assert "astra_live_secret_key" not in serialized["important_outputs"]["api_key"]
    assert "***REDACTED***" in serialized["important_outputs"]["api_key"]
    assert serialized["important_outputs"]["summary"] == "Report generated successfully"


# =============================================================================
# 7. SQLite Ledger Checkpoint Storage & Recovery Tests
# =============================================================================

def test_ledger_checkpoint_persistence_and_recovery(tmp_path):
    """Verify SQLite ledger persists checkpoints and discovers interrupted tasks."""
    db_file = tmp_path / "resilience_ledger.db"
    ledger = TaskLedger(db_path=db_file)

    # Save a running task
    task = Task(
        id="interrupted-task-42",
        conversation_id="conv-resilience",
        request_text="Long running data pipeline",
        status=TaskStatus.RUNNING,
    )
    ledger.save_task(task)

    # Save a checkpoint for this task
    chk = TaskCheckpoint(
        task_id=task.id,
        current_step_id="step_2",
        completed_step_ids=["step_1"],
        important_outputs={"step_1_out": "partial_data_ok"},
    )
    ledger.save_checkpoint(chk)

    # Retrieve checkpoint
    retrieved_chk = ledger.get_latest_checkpoint(task.id)
    assert retrieved_chk is not None
    assert retrieved_chk.checkpoint_id == chk.checkpoint_id
    assert retrieved_chk.completed_step_ids == ["step_1"]
    assert retrieved_chk.important_outputs["step_1_out"] == "partial_data_ok"

    # Simulate crash / reboot recovery
    interrupted_count = ledger.recover_interrupted_tasks()
    assert interrupted_count == 1

    # Discover recoverable tasks
    recoverable = ledger.get_recoverable_interrupted_tasks()
    assert len(recoverable) == 1
    assert recoverable[0]["task_id"] == task.id
    assert recoverable[0]["status"] == TaskStatus.INTERRUPTED.value


# =============================================================================
# 8. Adaptive Runtime Plan Execution & File Conflict Safety
# =============================================================================

def test_adaptive_runtime_execution_with_precondition_check(tmp_path):
    """Verify TaskRuntime executes adaptive plan, monitors invariants, and saves checkpoints."""
    db_file = tmp_path / "runtime_resilience.db"
    ledger = TaskLedger(db_path=db_file)
    runtime = TaskRuntime(ledger=ledger)

    task = Task(
        id="task-adapt-1",
        conversation_id="conv-1",
        request_text="Build workspace structure",
        status=TaskStatus.CREATED,
    )
    runtime.ledger.save_task(task)

    target_file = tmp_path / "step_output.txt"

    steps = [
        PlanStep(
            step_id="step_1",
            capability="write_file",
            arguments={"path": str(target_file), "content": "Adaptive step 1 output"},
            description="Write output file",
            expected_postconditions=[
                TaskInvariant(
                    type=InvariantType.FILE_EXISTS,
                    target=str(target_file),
                    expected_state=True,
                )
            ],
        ),
        PlanStep(
            step_id="step_2",
            capability="verify_file",
            arguments={"path": str(target_file)},
            description="Verify output file content",
            preconditions=[
                TaskInvariant(
                    type=InvariantType.FILE_EXISTS,
                    target=str(target_file),
                    expected_state=True,
                )
            ],
            expected_postconditions=[
                TaskInvariant(
                    type=InvariantType.FILE_CONTAINS_CHANGE,
                    target=str(target_file),
                    expected_state="Adaptive step 1 output",
                )
            ],
        ),
    ]

    # Pre-create file to simulate step_1 capability output
    target_file.write_text("Adaptive step 1 output", encoding="utf-8")

    result = runtime.execute_adaptive_plan(task.id, steps)
    assert result.success is True
    assert result.status == TaskStatus.COMPLETED

    # Verify checkpoint was created
    latest_chk = ledger.get_latest_checkpoint(task.id)
    assert latest_chk is not None
    assert "step_2" in latest_chk.completed_step_ids


def test_file_conflict_detection_prevents_blind_overwrite(tmp_path):
    """Verify that external file change breaks invariant and halts with WAITING_CLARIFICATION."""
    db_file = tmp_path / "conflict_ledger.db"
    ledger = TaskLedger(db_path=db_file)
    runtime = TaskRuntime(ledger=ledger)

    task = Task(
        id="task-conflict-1",
        conversation_id="conv-c",
        request_text="Edit configuration file",
        status=TaskStatus.CREATED,
    )
    runtime.ledger.save_task(task)

    cfg_file = tmp_path / "app.config"
    cfg_file.write_text("initial_config_v1", encoding="utf-8")

    # Step expects initial_config_v1, but file was modified externally to user_modified_v2
    cfg_file.write_text("user_modified_v2", encoding="utf-8")

    steps = [
        PlanStep(
            step_id="step_edit",
            capability="edit_config",
            arguments={"file_path": str(cfg_file)},
            description="Apply Astra edits",
            preconditions=[
                TaskInvariant(
                    type=InvariantType.FILE_CONTAINS_CHANGE,
                    target=str(cfg_file),
                    expected_state="initial_config_v1",
                )
            ],
        )
    ]

    result = runtime.execute_adaptive_plan(task.id, steps)
    # Must NOT blindly overwrite; must pause in WAITING_CLARIFICATION!
    assert result.success is False
    assert result.status == TaskStatus.WAITING_CLARIFICATION
    assert "File conflict on" in result.message

    # Task status in ledger must be WAITING_CLARIFICATION
    persisted_task = ledger.get_task(task.id)
    assert persisted_task.status == TaskStatus.WAITING_CLARIFICATION
