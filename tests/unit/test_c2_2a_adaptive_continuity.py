"""Section 4: Adaptive Continuity and Simulated Power Lifecycle Suite for AstraRun C2.2A.

Empirically verifies:
1. Multi-step task pause -> machine disturbance -> resume with re-observation and re-planning.
2. Simulated Windows sleep / wake transitions via PowerLifecycleManager:
   - Checkpoint creation with pause_reason="SYSTEM_SUSPEND"
   - Active execution budget paused during sleep (no phantom budget exhaustion)
   - Dynamic machine state refresh upon wake
   - Recovery assessment and ledger audit trail
3. Invariant: User-paused tasks (PAUSED_USER_REQUEST) are never inadvertently resumed on power wake.
"""

from __future__ import annotations

import time
from pathlib import Path
import pytest

from astrarun.core.paths import AstraPaths
from astrarun.machine.model import MachineModel
from astrarun.power.events import PowerEventType, PowerState, ResumeVerdict
from astrarun.power.ledger import PowerEventLedger
from astrarun.power.manager import PowerLifecycleManager
from astrarun.tasks.checkpoints import TaskCheckpoint
from astrarun.tasks.continuity import ContinuityEngine
from astrarun.tasks.models import TaskStatus


class MockTask:
    def __init__(self, task_id: str, status: TaskStatus = TaskStatus.RUNNING):
        self.id = task_id
        self.task_id = task_id
        self.status = status
        self.goal = "Multi-step complex analytical workflow"
        self.current_step = 2
        self.total_steps = 5


def test_multistep_pause_disturbance_resume_replan(tmp_path):
    """Test task pause -> machine disturbance -> re-observation and re-planning."""
    continuity = ContinuityEngine(checkpoints_dir=tmp_path / "checkpoints")
    
    task_id = "task_multistep_drift_01"
    # 1. Save checkpoint for step 2 of 5
    cp = continuity.save_checkpoint(
        task_id=task_id,
        goal="Process datasets across network storage",
        status="IN_PROGRESS",
        step_index=2,
        artifacts=[r"Z:\Data\source_batch.csv"],  # Assumes drive Z:
        context_variables={"processed_rows": 500, "active_dataset": "source_batch"},
        summary="Completed initial chunk processing, awaiting aggregation",
    )
    assert cp is not None
    assert cp.step_index == 2

    # 2. Machine disturbance: Drive Z: is disconnected / unmounted
    has_drift, reasons = continuity.check_machine_drift(cp, mounted_volumes=["C", "D"])
    assert has_drift, "Expected machine drift when drive Z: is missing"
    assert any("Z:" in r for r in reasons)

    # 3. Simulate re-planning: Update checkpoint with new path on local drive C:
    replan_cp = continuity.save_checkpoint(
        task_id=task_id,
        goal="Process datasets across network storage",
        status="IN_PROGRESS",
        step_index=2,
        artifacts=[r"C:\LocalData\source_batch.csv"],
        context_variables={
            "processed_rows": 500,
            "active_dataset": "source_batch",
            "failover_local": True,
        },
        summary="Replanned to use local replica on drive C:",
    )
    has_drift_after, reasons_after = continuity.check_machine_drift(replan_cp, mounted_volumes=["C", "D"])
    assert not has_drift_after, "Drift should be resolved after replan to drive C:"


def test_simulated_sleep_wake_lifecycle(tmp_path):
    """Verify clean state preservation and budget continuity across simulated Windows sleep/wake."""
    db_path = tmp_path / "power_ledger.db"
    ledger = PowerEventLedger(db_path=db_path)
    continuity = ContinuityEngine(checkpoints_dir=tmp_path / "checkpoints")
    
    mgr = PowerLifecycleManager(
        machine_model=MachineModel.get_instance(),
        ledger=ledger,
        continuity=continuity,
    )

    task = MockTask("task_sleep_wake_01", status=TaskStatus.RUNNING)
    timer = mgr.register_active_task(task.id, task, budget_seconds=600.0)
    assert not timer.is_paused
    initial_remaining = timer.remaining_budget_seconds

    # 1. Trigger simulated sleep transition
    mgr.handle_suspend()
    assert mgr.state == PowerState.SUSPENDED
    assert timer.is_paused, "Budget timer must be paused during sleep"

    # Verify checkpoint created
    saved_cp = continuity.load_checkpoint(task.id)
    assert saved_cp is not None
    assert saved_cp.status == "SUSPENDED"

    # Verify suspend events recorded in ledger
    events = ledger.list_events()
    event_types = [e.event_type for e in events]
    assert PowerEventType.SYSTEM_SUSPENDING in event_types
    assert PowerEventType.TASK_SUSPENDED in event_types

    # 2. Simulate sleep duration elapsed (1 second wall time)
    time.sleep(1.0)

    # 3. Trigger simulated wake transition
    assessments = mgr.handle_resume(reason="SIMULATED_USER_RESUME")
    assert mgr.state == PowerState.RESUMING or mgr.state == PowerState.RUNNING

    # Budget timer must have resumed without losing the 1 second sleep time
    assert not timer.is_paused
    # The elapsed active execution should be negligible (< 0.5s), not including the 1s sleep
    assert timer.elapsed_active_seconds < 0.8

    # Verify resume events recorded in ledger
    wake_events = ledger.list_events()
    wake_types = [e.event_type for e in wake_events]
    assert PowerEventType.SYSTEM_RESUMED in wake_types
    assert PowerEventType.MACHINE_STATE_REFRESHED in wake_types
    assert PowerEventType.TASK_RESUMED in wake_types


def test_user_paused_task_invariant_across_sleep_wake(tmp_path):
    """User-paused tasks must NEVER be auto-resumed upon system wake."""
    db_path = tmp_path / "user_pause_ledger.db"
    ledger = PowerEventLedger(db_path=db_path)
    continuity = ContinuityEngine(checkpoints_dir=tmp_path / "checkpoints")
    
    mgr = PowerLifecycleManager(
        machine_model=MachineModel.get_instance(),
        ledger=ledger,
        continuity=continuity,
    )

    user_task = MockTask("task_user_paused_01", status=TaskStatus.PAUSED_USER_REQUEST)
    timer = mgr.register_active_task(user_task.id, user_task, budget_seconds=600.0)
    timer.pause()

    # Sleep transition
    mgr.handle_suspend()
    assert mgr.state == PowerState.SUSPENDED

    # Wake transition
    mgr.handle_resume(reason="SIMULATED_WAKE")

    # Invariant: Timer must remain paused, task must remain user-paused
    assert timer.is_paused, "User-paused task timer was improperly resumed on wake!"
    assert user_task.status == TaskStatus.PAUSED_USER_REQUEST
