"""RC0 Test Suite: Windows Power Lifecycle, Resume Recovery & QoS Governance."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from astrarun.core.qos import QoSHealthState, ResourceGovernor, WorkloadQoS
from astrarun.machine.fact import MachineFact
from astrarun.machine.model import MachineModel
from astrarun.power.budget import ExecutionBudgetTimer
from astrarun.power.events import DisplayState, PowerEventType, PowerState, ResumeVerdict
from astrarun.power.ledger import PowerEventLedger
from astrarun.power.manager import PowerLifecycleManager
from astrarun.power.recovery import RecoveryAssessment, ResumeRecoveryEngine
from astrarun.tasks.checkpoints import TaskCheckpoint
from astrarun.tasks.continuity import ContinuityEngine
from astrarun.tasks.models import Task, TaskStatus


# -----------------------------------------------------------------------------
# 1. ExecutionBudgetTimer Tests
# -----------------------------------------------------------------------------

def test_execution_budget_timer_monotonic_pause():
    """Verify that sleep duration does NOT consume task active execution budget."""
    timer = ExecutionBudgetTimer(budget_seconds=10.0)
    assert timer.is_paused

    timer.start()
    assert not timer.is_paused
    time.sleep(0.05)  # 50ms active work

    # Simulate machine entering sleep for 8 hours (represented by pausing)
    timer.pause()
    assert timer.is_paused
    elapsed_before_sleep = timer.elapsed_active_seconds
    assert 0.04 <= elapsed_before_sleep <= 0.15

    # Simulate sleep duration passing in wall clock
    time.sleep(0.1)

    # Monotonic active elapsed time must NOT have increased while paused
    assert timer.elapsed_active_seconds == elapsed_before_sleep

    # Machine wakes up and resumes
    timer.resume()
    assert not timer.is_paused
    time.sleep(0.05)
    timer.pause()

    total_active = timer.elapsed_active_seconds
    assert total_active > elapsed_before_sleep
    assert total_active < 0.35
    assert not timer.is_expired
    assert timer.remaining_budget_seconds > 9.5


def test_execution_budget_timer_serialization():
    """Verify timer serialization and deserialization from checkpoint dict."""
    t1 = ExecutionBudgetTimer(budget_seconds=100.0)
    t1.start()
    time.sleep(0.05)
    t1.pause()

    d = t1.to_dict()
    assert "budget_seconds" in d
    assert "cumulative_active_sec" in d
    assert d["is_paused"] is True

    t2 = ExecutionBudgetTimer.from_dict(d)
    assert t2.budget_seconds == 100.0
    assert t2.is_paused is True
    assert t2.elapsed_active_seconds == t1.elapsed_active_seconds


# -----------------------------------------------------------------------------
# 2. PowerEventLedger Tests
# -----------------------------------------------------------------------------

def test_power_event_ledger_persistence(tmp_path):
    """Verify persistent recording of the 8 canonical power lifecycle events."""
    db_file = tmp_path / "power_events.db"
    ledger = PowerEventLedger(db_path=db_file)

    ev1 = ledger.record_event(PowerEventType.SYSTEM_SUSPENDING, details={"reason": "user_sleep"})
    ev2 = ledger.record_event(PowerEventType.TASK_SUSPENDED, task_id="task_101", details={"budget": 500})
    ev3 = ledger.record_event(PowerEventType.SYSTEM_RESUMED, details={"reason": "power_button"})
    ev4 = ledger.record_event(PowerEventType.MACHINE_STATE_REFRESHED, details={"free_ram_gb": 8.5})
    ev5 = ledger.record_event(PowerEventType.TASK_RESUME_STARTED, task_id="task_101")
    ev6 = ledger.record_event(PowerEventType.TASK_RESUMED, task_id="task_101")

    events = ledger.list_events(limit=10)
    assert len(events) == 6
    assert events[0].event_type == PowerEventType.SYSTEM_SUSPENDING
    assert events[1].event_type == PowerEventType.TASK_SUSPENDED
    assert events[5].event_type == PowerEventType.TASK_RESUMED
    assert events[1].task_id == "task_101"

    # Invariant: Secret keys must be filtered from details
    ev_secret = ledger.record_event(
        PowerEventType.TASK_RESUME_BLOCKED,
        details={"api_key": "SECRET_KEY_123", "safe_field": "ok"},
    )
    assert "api_key" not in ev_secret.details
    assert ev_secret.details.get("safe_field") == "ok"


# -----------------------------------------------------------------------------
# 3. ResumeRecoveryEngine Tests
# -----------------------------------------------------------------------------

def test_resume_recovery_intact_state(tmp_path):
    """Verify that an intact task receives UNCHANGED verdict."""
    m_db = tmp_path / "machine.db"
    model = MachineModel(db_path=m_db)
    model.set_fact(MachineFact("hardware.storage.volumes", ["C", "E"]))

    cont = ContinuityEngine(checkpoints_dir=tmp_path / "checkpoints")
    cp = TaskCheckpoint(
        task_id="task_intact",
        artifacts=["E:\\Workspace\\Active\\output.csv"],
    )
    cont.save_checkpoint(cp)

    recovery = ResumeRecoveryEngine(machine_model=model, continuity_engine=cont)
    assessment = recovery.evaluate_task(cp)
    assert assessment.verdict == ResumeVerdict.UNCHANGED
    assert not assessment.replan_required
    assert not assessment.requires_user_intervention


def test_resume_recovery_missing_drive(tmp_path):
    """Verify that a missing storage volume triggers REQUIRES_USER."""
    m_db = tmp_path / "machine.db"
    model = MachineModel(db_path=m_db)
    model.set_fact(MachineFact("hardware.storage.volumes", ["C"]))  # Drive E missing

    cont = ContinuityEngine(checkpoints_dir=tmp_path / "checkpoints")
    cp = TaskCheckpoint(
        task_id="task_missing_drive",
        artifacts=["E:\\Workspace\\Active\\output.csv"],
    )
    cont.save_checkpoint(cp)

    recovery = ResumeRecoveryEngine(machine_model=model, continuity_engine=cont)
    assessment = recovery.evaluate_task(cp)
    assert assessment.verdict == ResumeVerdict.REQUIRES_USER
    assert assessment.requires_user_intervention is True
    assert "missing or disconnected" in assessment.drift_details[0]


def test_resume_recovery_dead_process(tmp_path):
    """Verify that a terminated required process triggers REQUIRES_REPLAN."""
    m_db = tmp_path / "machine.db"
    model = MachineModel(db_path=m_db)
    model.set_fact(MachineFact("hardware.storage.volumes", ["C"]))

    cont = ContinuityEngine(checkpoints_dir=tmp_path / "checkpoints")
    cp = TaskCheckpoint(
        task_id="task_dead_process",
        recoverable_handles={"browser_pid": 99999999},  # Non-existent PID
    )
    cont.save_checkpoint(cp)

    recovery = ResumeRecoveryEngine(machine_model=model, continuity_engine=cont)
    assessment = recovery.evaluate_task(cp)
    assert assessment.verdict == ResumeVerdict.REQUIRES_REPLAN
    assert assessment.replan_required is True


# -----------------------------------------------------------------------------
# 4. PowerLifecycleManager Integration Tests
# -----------------------------------------------------------------------------

def test_power_lifecycle_manager_suspend_and_resume(tmp_path):
    """Verify full suspend -> state pause -> wake -> recovery cycle."""
    m_db = tmp_path / "machine.db"
    p_db = tmp_path / "power.db"
    cp_dir = tmp_path / "checkpoints"

    model = MachineModel(db_path=m_db)
    model.bootstrap(quick=True)
    ledger = PowerEventLedger(db_path=p_db)
    cont = ContinuityEngine(checkpoints_dir=cp_dir)
    recovery = ResumeRecoveryEngine(machine_model=model, continuity_engine=cont)

    mgr = PowerLifecycleManager(
        machine_model=model,
        ledger=ledger,
        continuity=cont,
        recovery_engine=recovery,
    )

    assert mgr.is_automation_allowed()

    # Register active running task
    timer = mgr.register_active_task("task_lifecycle_test", object(), budget_seconds=600.0)
    assert not timer.is_paused

    # 1. Trigger Suspend
    mgr.handle_suspend()
    assert mgr.state == PowerState.SUSPENDED
    assert not mgr.is_automation_allowed()
    assert timer.is_paused

    # Verify checkpoint created
    saved_cp = cont.load_latest_checkpoint("task_lifecycle_test")
    assert saved_cp is not None
    assert saved_cp.important_outputs.get("status") == "SUSPENDED"

    # 2. Trigger Resume
    assessments = mgr.handle_resume(reason="UNIT_TEST_WAKE")
    assert mgr.state == PowerState.RUNNING
    assert mgr.is_automation_allowed()
    assert not timer.is_paused
    assert len(assessments) == 1
    assert assessments[0].verdict == ResumeVerdict.UNCHANGED

    # 3. Test Display Off Lock
    mgr.handle_display_change(DisplayState.OFF)
    assert not mgr.is_automation_allowed()
    mgr.handle_display_change(DisplayState.ON)
    assert mgr.is_automation_allowed()


# -----------------------------------------------------------------------------
# 5. ResourceGovernor & QoS Tests
# -----------------------------------------------------------------------------

def test_resource_governor_pressure_throttling():
    """Verify ResourceGovernor throttles background tasks under memory pressure."""
    gov = ResourceGovernor(min_ram_headroom_gb=100.0)  # Artificial high requirement to force pressure
    health = gov.evaluate_health()
    assert health.ram_pressure is True
    assert health.background_paused is True
    assert health.concurrency_limit == 1
    assert not gov.can_run_background_work()

    gov_normal = ResourceGovernor(min_ram_headroom_gb=0.1, min_vram_headroom_gb=0.1)
    health_normal = gov_normal.evaluate_health()
    assert health_normal.background_paused is False
    assert health_normal.concurrency_limit in (2, 4)
    assert gov_normal.can_run_background_work()


# -----------------------------------------------------------------------------
# 6. Task Model Observable Progress State Tests
# -----------------------------------------------------------------------------

def test_task_model_observable_progress_and_suspended_state():
    """Verify continuous observable state and SUSPENDED status transitions."""
    task = Task(id="t_obs_1", conversation_id="conv_1", request_text="Long data build")
    assert task.current_phase == "INITIALIZING"
    assert task.last_action is None
    assert task.active_elapsed_sec == 0.0

    task.transition_to(TaskStatus.RUNNING)
    task.current_phase = "DOWNLOADING"
    task.last_action = "Fetched 50MB batch"
    task.active_elapsed_sec = 12.5
    task.waiting_state = None

    # Transition to SUSPENDED on power event
    task.transition_to(TaskStatus.SUSPENDED)
    assert task.status == TaskStatus.SUSPENDED
    assert task.status.is_waiting is True
    assert not task.status.is_terminal

    # Resume from SUSPENDED back to RUNNING
    task.transition_to(TaskStatus.RUNNING)
    assert task.status == TaskStatus.RUNNING

    # Verify serialization
    d = task.to_dict()
    assert d["current_phase"] == "DOWNLOADING"
    assert d["last_action"] == "Fetched 50MB batch"
    assert d["active_elapsed_sec"] == 12.5
    assert d["status"] == "RUNNING"

    restored = Task.from_dict(d)
    assert restored.current_phase == "DOWNLOADING"
    assert restored.last_action == "Fetched 50MB batch"
    assert restored.active_elapsed_sec == 12.5
