"""Disturbance Classification, Human Interruption Tracking & Bounded Recovery Budgets.

Core Principles:
1. Human interruption is an observation: Distinguish temporary input takeover from state-changing human interventions.
2. Do not fight the user: Repeated human conflicting actions (e.g. closing an app twice) halt automatic reopen and ask what to do.
3. Bounded recovery budgets: Every recovery strategy has a maximum attempt count (1 or 2) before escalating or failing.
4. Privacy: Only task-relevant human interruptions are recorded; no keystroke logging or ambient surveillance.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tasks.disturbances")


class DisturbanceType(str, Enum):
    # Human Action Disturbances
    USER_INPUT_TAKEOVER = "USER_INPUT_TAKEOVER"
    USER_CLOSED_REQUIRED_WINDOW = "USER_CLOSED_REQUIRED_WINDOW"
    USER_CHANGED_REQUIRED_WINDOW = "USER_CHANGED_REQUIRED_WINDOW"
    USER_NAVIGATED_AWAY = "USER_NAVIGATED_AWAY"
    USER_MODIFIED_TARGET_FILE = "USER_MODIFIED_TARGET_FILE"
    USER_DELETED_TARGET_FILE = "USER_DELETED_TARGET_FILE"

    # Application & Process Failures
    APPLICATION_CRASHED = "APPLICATION_CRASHED"
    APPLICATION_HUNG = "APPLICATION_HUNG"
    PROCESS_EXITED = "PROCESS_EXITED"
    TAB_CLOSED = "TAB_CLOSED"
    DOWNLOAD_INTERRUPTED = "DOWNLOAD_INTERRUPTED"

    # Environmental & Network Disturbances
    NETWORK_LOST = "NETWORK_LOST"
    NETWORK_RESTORED = "NETWORK_RESTORED"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"

    # Filesystem Changes
    FILE_CHANGED = "FILE_CHANGED"
    FILE_MOVED = "FILE_MOVED"
    FILE_DELETED = "FILE_DELETED"

    # Model & Tool Failures
    MODEL_CRASHED = "MODEL_CRASHED"
    TOOL_FAILED = "TOOL_FAILED"


@dataclass
class DisturbanceEvent:
    """Structured record of an unexpected environmental change or user interference."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str = ""
    timestamp: float = field(default_factory=time.time)
    source: str = "runtime_observer"
    disturbance_type: DisturbanceType = DisturbanceType.PROCESS_EXITED
    observed_before: Any = None
    observed_after: Any = None
    affected_invariants: List[str] = field(default_factory=list)
    likely_origin: Optional[str] = None
    is_human_intervention: bool = False
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "disturbance_type": self.disturbance_type.value,
            "observed_before": str(self.observed_before),
            "observed_after": str(self.observed_after),
            "affected_invariants": self.affected_invariants,
            "likely_origin": self.likely_origin,
            "is_human_intervention": self.is_human_intervention,
            "details": self.details,
        }


@dataclass
class RecoveryBudget:
    """Bounded retry policy preventing infinite loops and respecting user intent."""
    task_id: str
    max_auto_attempts_per_strategy: int = 2
    max_total_recovery_attempts: int = 5
    attempts_by_strategy: Dict[str, int] = field(default_factory=dict)
    attempts_by_target: Dict[str, int] = field(default_factory=dict)
    total_attempts: int = 0

    def can_attempt_recovery(self, strategy: str, target: str = "") -> bool:
        """Determine if an automatic recovery attempt is permitted under the budget."""
        if self.total_attempts >= self.max_total_recovery_attempts:
            logger.warning(
                "Task %s recovery budget exhausted (total=%d >= max=%d)",
                self.task_id, self.total_attempts, self.max_total_recovery_attempts
            )
            return False

        strat_count = self.attempts_by_strategy.get(strategy, 0)
        if strat_count >= self.max_auto_attempts_per_strategy:
            logger.warning(
                "Task %s strategy '%s' budget exhausted (attempts=%d >= max=%d)",
                self.task_id, strategy, strat_count, self.max_auto_attempts_per_strategy
            )
            return False

        if target:
            target_count = self.attempts_by_target.get(target, 0)
            if target_count >= self.max_auto_attempts_per_strategy:
                logger.warning(
                    "Task %s target '%s' recovery exhausted (attempts=%d >= max=%d)",
                    self.task_id, target, target_count, self.max_auto_attempts_per_strategy
                )
                return False

        return True

    def record_attempt(self, strategy: str, target: str = "") -> int:
        """Record an attempt and return the updated count for that strategy."""
        self.total_attempts += 1
        self.attempts_by_strategy[strategy] = self.attempts_by_strategy.get(strategy, 0) + 1
        if target:
            self.attempts_by_target[target] = self.attempts_by_target.get(target, 0) + 1
        count = self.attempts_by_strategy[strategy]
        logger.info(
            "Task %s recorded recovery attempt for '%s' (strategy count=%d, total=%d)",
            self.task_id, strategy, count, self.total_attempts
        )
        return count


class DisturbanceTracker:
    """
    Manages and classifies disturbances encountered during task execution.
    Enforces 'Do Not Fight The User' policies by detecting repeated intentional human actions.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.budget = RecoveryBudget(task_id=task_id)
        self.history: List[DisturbanceEvent] = []
        self._repeated_user_actions: Dict[str, int] = {}  # target/action -> count

    def record_disturbance(
        self,
        disturbance_type: DisturbanceType,
        observed_before: Any,
        observed_after: Any,
        affected_invariants: Optional[List[str]] = None,
        source: str = "watch_set",
        likely_origin: Optional[str] = None,
        is_human_intervention: bool = False,
        details: str = "",
    ) -> DisturbanceEvent:
        """Record a structured disturbance and analyze for repeated user conflicts."""
        ev = DisturbanceEvent(
            task_id=self.task_id,
            timestamp=time.time(),
            source=source,
            disturbance_type=disturbance_type,
            observed_before=observed_before,
            observed_after=observed_after,
            affected_invariants=affected_invariants or [],
            likely_origin=likely_origin,
            is_human_intervention=is_human_intervention,
            details=details,
        )
        self.history.append(ev)

        # Track repeated human actions targeting the same entity
        if is_human_intervention and ev.affected_invariants:
            for inv_target in ev.affected_invariants:
                self._repeated_user_actions[inv_target] = self._repeated_user_actions.get(inv_target, 0) + 1

        logger.info(
            "Task %s disturbance recorded: %s (Human: %s, Details: %s)",
            self.task_id, disturbance_type.value, is_human_intervention, details
        )
        return ev

    def should_ask_user_instead_of_reopening(self, target: str) -> bool:
        """
        'Do Not Fight The User' Check:
        If user intentionally repeats a conflicting action (e.g. closes required app twice),
        return True so Astra stops fighting the user and asks what to do.
        """
        count = self._repeated_user_actions.get(target, 0)
        return count >= 2

    def get_user_conflict_prompt(self, target: str) -> Dict[str, Any]:
        """Construct the clarification prompt when a user repeatedly closes a required dependency."""
        return {
            "title": f"Astra needs {target}",
            "message": f"Astra needs {target} to continue this task. You closed it twice.\nHow would you like to proceed?",
            "options": [
                {"id": "resume_with_target", "label": f"Resume with {target}"},
                {"id": "continue_alternative", "label": "Continue another way"},
                {"id": "cancel_task", "label": "Cancel task"},
            ],
            "target": target,
        }
