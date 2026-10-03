"""Power Lifecycle Manager for AstraRun 1.0.

Central coordinator for Windows sleep/hibernate/resume transitions, task pausing,
active execution budget accounting, and safe post-wake recovery.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.machine.model import MachineModel
from astrarun.machine.resource_snapshot import ResourceSnapshot
from astrarun.power.budget import ExecutionBudgetTimer
from astrarun.power.events import DisplayState, PowerEventType, PowerState, ResumeVerdict
from astrarun.power.ledger import PowerEventLedger
from astrarun.power.listener import StandaloneWin32PowerListener, callbacks
from astrarun.power.recovery import RecoveryAssessment, ResumeRecoveryEngine
from astrarun.tasks.checkpoints import TaskCheckpoint
from astrarun.tasks.continuity import ContinuityEngine

logger = get_logger("astrarun.power.manager")


class PowerLifecycleManager:
    """Manages the full suspend, resume, and recovery lifecycle."""

    _instance: Optional[PowerLifecycleManager] = None

    def __init__(
        self,
        machine_model: Optional[MachineModel] = None,
        ledger: Optional[PowerEventLedger] = None,
        continuity: Optional[ContinuityEngine] = None,
        recovery_engine: Optional[ResumeRecoveryEngine] = None,
    ) -> None:
        self.state: PowerState = PowerState.RUNNING
        self.display_state: DisplayState = DisplayState.ON
        self.model = machine_model or MachineModel.get_instance()
        self.ledger = ledger or PowerEventLedger()
        self.continuity = continuity or ContinuityEngine()
        self.recovery = recovery_engine or ResumeRecoveryEngine(self.model, self.continuity)

        self._active_tasks: Dict[str, Any] = {}
        self._task_timers: Dict[str, ExecutionBudgetTimer] = {}
        self._automation_locked: bool = False
        self._listener: Optional[StandaloneWin32PowerListener] = None

        # Hook into global listener callbacks
        callbacks.on_suspend.append(self.handle_suspend)
        callbacks.on_resume.append(self.handle_resume)
        callbacks.on_display_change.append(self.handle_display_change)
        callbacks.on_session_end.append(self.handle_session_end)

    @classmethod
    def get_instance(cls) -> PowerLifecycleManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_active_task(self, task_id: str, task_obj: Any, budget_seconds: float = 1200.0) -> ExecutionBudgetTimer:
        """Register a running task with its active execution budget timer."""
        self._active_tasks[task_id] = task_obj
        timer = ExecutionBudgetTimer(budget_seconds=budget_seconds)
        timer.start()
        self._task_timers[task_id] = timer
        return timer

    def unregister_task(self, task_id: str) -> None:
        """Unregister a task upon completion or cancellation."""
        self._active_tasks.pop(task_id, None)
        self._task_timers.pop(task_id, None)

    def is_automation_allowed(self) -> bool:
        """Check if physical UI automation is currently safe and authorized."""
        if self._automation_locked or self.state in (PowerState.SUSPENDING, PowerState.SUSPENDED, PowerState.RESUMING):
            return False
        if self.display_state == DisplayState.OFF:
            return False
        return True

    # -------------------------------------------------------------------------
    # Suspend Lifecycle
    # -------------------------------------------------------------------------

    def handle_suspend(self) -> None:
        """Executed immediately before Windows enters sleep/hibernate."""
        if self.state == PowerState.SUSPENDED:
            return

        logger.info("[POWER_LIFECYCLE] Initiating graceful suspend transition...")
        self.state = PowerState.SUSPENDING
        self._automation_locked = True

        # 1. Record system suspending
        self.ledger.record_event(
            PowerEventType.SYSTEM_SUSPENDING,
            details={"active_task_count": len(self._active_tasks)},
        )

        # 2. Checkpoint and suspend all active tasks
        for task_id, task in list(self._active_tasks.items()):
            timer = self._task_timers.get(task_id)
            if timer:
                timer.pause()

            # Create durable checkpoint
            cp = TaskCheckpoint(
                task_id=task_id,
                important_outputs={"status": "SUSPENDED", "reason": "SYSTEM_SUSPEND"},
            )
            self.continuity.save_checkpoint(cp)

            # Record task suspended in ledger
            self.ledger.record_event(
                PowerEventType.TASK_SUSPENDED,
                task_id=task_id,
                details={
                    "remaining_budget_sec": timer.remaining_budget_seconds if timer else 0.0,
                    "elapsed_active_sec": timer.elapsed_active_seconds if timer else 0.0,
                },
            )

        # 3. Flush MachineModel state
        try:
            self.model.refresh_dynamic_metrics()
        except Exception as e:
            logger.debug("Failed refreshing dynamic metrics on suspend: %s", e)

        self.state = PowerState.SUSPENDED
        logger.info("[POWER_LIFECYCLE] Suspend transition completed cleanly.")

    # -------------------------------------------------------------------------
    # Resume Lifecycle
    # -------------------------------------------------------------------------

    def handle_resume(self, reason: str = "RESUME_AUTOMATIC") -> List[RecoveryAssessment]:
        """Executed when Windows wakes up from sleep or hibernate."""
        logger.info("[POWER_LIFECYCLE] System waking from suspend (%s). Entering RESUMING state...", reason)
        self.state = PowerState.RESUMING
        self._automation_locked = True  # DO NOT immediately click/type

        # 1. Record system resumed
        self.ledger.record_event(
            PowerEventType.SYSTEM_RESUMED,
            details={"reason": reason, "suspended_tasks": len(self._active_tasks)},
        )

        # 2. Refresh Machine Reality
        logger.info("[POWER_LIFECYCLE] Refreshing volatile machine metrics, displays, and network...")
        self.model.refresh_dynamic_metrics()
        snap = ResourceSnapshot.capture(include_gpu=True)

        self.ledger.record_event(
            PowerEventType.MACHINE_STATE_REFRESHED,
            details={
                "free_ram_gb": snap.available_ram_gb,
                "free_vram_gb": snap.free_vram_gb,
                "network_connected": snap.network_connected,
                "power_plugged": snap.power_plugged,
            },
        )

        # 3. Evaluate each task checkpoint
        assessments: List[RecoveryAssessment] = []
        for task_id in list(self._active_tasks.keys()):
            self.ledger.record_event(PowerEventType.TASK_RESUME_STARTED, task_id=task_id)

            cp = self.continuity.load_latest_checkpoint(task_id)
            if not cp:
                cp = TaskCheckpoint(task_id=task_id)

            assessment = self.recovery.evaluate_task(cp)
            assessments.append(assessment)
            timer = self._task_timers.get(task_id)

            if assessment.verdict in (ResumeVerdict.UNCHANGED, ResumeVerdict.RECOVERABLE_DRIFT):
                if timer:
                    timer.resume()
                self.ledger.record_event(
                    PowerEventType.TASK_RESUMED,
                    task_id=task_id,
                    details={
                        "verdict": assessment.verdict.value,
                        "remaining_budget_sec": timer.remaining_budget_seconds if timer else 0.0,
                    },
                )
            elif assessment.verdict == ResumeVerdict.REQUIRES_REPLAN:
                self.ledger.record_event(
                    PowerEventType.TASK_REPLANNED_AFTER_RESUME,
                    task_id=task_id,
                    details={"drift_details": assessment.drift_details},
                )
            elif assessment.verdict == ResumeVerdict.REQUIRES_USER:
                self.ledger.record_event(
                    PowerEventType.TASK_RESUME_BLOCKED,
                    task_id=task_id,
                    details={"reason": assessment.reason, "remediation": assessment.remediation_action},
                )

        # 4. Release automation lock when safe
        self._automation_locked = False
        self.state = PowerState.RUNNING
        logger.info("[POWER_LIFECYCLE] Resume processing complete. Runtime state is RUNNING.")
        return assessments

    def handle_display_change(self, state: DisplayState) -> None:
        """Handle monitor power/sleep state change."""
        self.display_state = state
        self.ledger.record_event(
            PowerEventType.DISPLAY_STATE_CHANGED,
            details={"display_state": state.value},
        )
        if state == DisplayState.OFF:
            logger.info("[POWER_LIFECYCLE] Display turned OFF. Locking physical automation.")
            self._automation_locked = True
        elif state == DisplayState.ON:
            logger.info("[POWER_LIFECYCLE] Display turned ON. Automation unlocked if system running.")
            if self.state == PowerState.RUNNING:
                self._automation_locked = False

    def handle_session_end(self) -> None:
        """Handle Windows shutdown or user logoff."""
        logger.info("[POWER_LIFECYCLE] Handling session end (shutdown/logoff)...")
        self.handle_suspend()
        self.ledger.record_event(PowerEventType.SESSION_ENDING)

    def start_listener(self) -> None:
        """Start background Win32 power listener if running standalone."""
        if self._listener is None:
            self._listener = StandaloneWin32PowerListener()
            self._listener.start()

    def stop_listener(self) -> None:
        """Stop background Win32 power listener."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
