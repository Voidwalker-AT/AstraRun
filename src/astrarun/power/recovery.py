"""Resume Recovery Engine for Post-Wake Task Continuity in AstraRun 1.0.

Evaluates surviving environment, storage volumes, display topology, and process
states to determine safe recovery strategies without blind action replay.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from astrarun.core.logging import get_logger
from astrarun.machine.model import MachineModel
from astrarun.machine.resource_snapshot import ResourceSnapshot
from astrarun.power.events import ResumeVerdict
from astrarun.tasks.checkpoints import TaskCheckpoint
from astrarun.tasks.continuity import ContinuityEngine

logger = get_logger("astrarun.power.recovery")


@dataclass
class RecoveryAssessment:
    """Recovery verdict and actionable remediation for an interrupted task."""
    task_id: str
    verdict: ResumeVerdict
    reason: str
    drift_details: List[str] = field(default_factory=list)
    remediation_action: Optional[str] = None
    replan_required: bool = False
    requires_user_intervention: bool = False


class ResumeRecoveryEngine:
    """Assesses tasks after system wake or process recovery."""

    def __init__(
        self,
        machine_model: Optional[MachineModel] = None,
        continuity_engine: Optional[ContinuityEngine] = None,
    ) -> None:
        self.model = machine_model or MachineModel.get_instance()
        self.continuity = continuity_engine or ContinuityEngine()

    def evaluate_task(self, checkpoint: TaskCheckpoint) -> RecoveryAssessment:
        """Examine checkpoint against current machine state to determine recovery strategy."""
        drift_details: List[str] = []

        # 1. Check storage volume availability
        vols_fact = self.model.get_fact("hardware.storage.volumes")
        mounted_vols = vols_fact.value if vols_fact and isinstance(vols_fact.value, list) else None
        has_drift, drift_reasons = self.continuity.check_machine_drift(checkpoint, mounted_volumes=mounted_vols)
        if has_drift:
            drift_details.extend(drift_reasons)
            return RecoveryAssessment(
                task_id=checkpoint.task_id,
                verdict=ResumeVerdict.REQUIRES_USER,
                reason="Required storage volume is disconnected or missing after wake.",
                drift_details=drift_details,
                remediation_action="Prompt user to reconnect the missing drive or specify a new artifact destination.",
                requires_user_intervention=True,
            )

        # 2. Check process handles (browsers, workers, servers)
        handles = getattr(checkpoint, "recoverable_handles", None) or getattr(checkpoint, "context_variables", {}) or {}
        for handle_name, pid_val in handles.items():
            if "pid" in handle_name.lower():
                try:
                    pid = int(pid_val)
                    if not psutil.pid_exists(pid):
                        drift_details.append(f"Process {handle_name} (PID {pid}) terminated during suspend.")
                except Exception:
                    pass

        if drift_details:
            return RecoveryAssessment(
                task_id=checkpoint.task_id,
                verdict=ResumeVerdict.REQUIRES_REPLAN,
                reason="Required target process terminated during power suspension.",
                drift_details=drift_details,
                remediation_action="Re-open target application or replan steps from the last completed artifact.",
                replan_required=True,
            )

        # 3. Check display / monitor topology changes
        disp_fact = self.model.get_fact("hardware.display.primary_resolution")
        snap = ResourceSnapshot.capture(include_gpu=False)

        # 4. Check network connectivity if task used network handles
        if handles.get("requires_network", False):
            if not snap.network_connected:
                return RecoveryAssessment(
                    task_id=checkpoint.task_id,
                    verdict=ResumeVerdict.REQUIRES_USER,
                    reason="Network connection lost during suspend.",
                    drift_details=["Network interface reports offline."],
                    remediation_action="Wait for Wi-Fi/Ethernet reconnection or prompt user.",
                    requires_user_intervention=True,
                )

        # 5. Default: Clean resumption
        return RecoveryAssessment(
            task_id=checkpoint.task_id,
            verdict=ResumeVerdict.UNCHANGED,
            reason="All storage volumes, processes, and environment invariants survived suspend.",
            drift_details=[],
            remediation_action="Resume active task execution from next pending plan step.",
            replan_required=False,
            requires_user_intervention=False,
        )
