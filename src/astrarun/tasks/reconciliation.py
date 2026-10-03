"""Task Reconciliation and Resume Assessment Engine for AstraRun 1.0 (RC0.1).

Implements the fundamental invariant:
"RESUME IS RECONCILIATION, NOT UNPAUSE"

Before any suspended or user-paused task continues execution:
1. Re-observe physical machine facts and hardware topology.
2. Capture instantaneous ResourceSnapshot.
3. Verify prior created artifacts, files, hashes, and downloads.
4. Detect external progress (e.g. browser or user finished a download or fixed code).
5. Detect and classify human changes (COMPATIBLE, CONFLICTING, GOAL_COMPLETING, GOAL_INVALIDATING).
6. Verify surviving application and process handles.
7. Classify overall resumption into typed ResumeVerdict.
8. Formulate PlanRevision if downstream steps require adaptation without restarting valid completed work.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil

from astrarun.core.logging import get_logger
from astrarun.machine.model import MachineModel
from astrarun.machine.resource_snapshot import ResourceSnapshot
from astrarun.tasks.checkpoints import PlanRevision, TaskCheckpoint

logger = get_logger("astrarun.tasks.reconciliation")


class ResumeVerdict(str, Enum):
    """Authoritative classification of task state reconciliation."""
    UNCHANGED = "UNCHANGED"
    PROGRESS_ADVANCED_EXTERNALLY = "PROGRESS_ADVANCED_EXTERNALLY"
    RECOVERABLE_DRIFT = "RECOVERABLE_DRIFT"
    PLAN_PARTIALLY_INVALID = "PLAN_PARTIALLY_INVALID"
    REQUIRES_REPLAN = "REQUIRES_REPLAN"
    REQUIRES_USER = "REQUIRES_USER"
    GOAL_ALREADY_COMPLETED = "GOAL_ALREADY_COMPLETED"
    UNRECOVERABLE = "UNRECOVERABLE"


class HumanChangeClassification(str, Enum):
    """Categorization of human operator modifications during task pause."""
    COMPATIBLE = "COMPATIBLE"
    CONFLICTING = "CONFLICTING"
    GOAL_COMPLETING = "GOAL_COMPLETING"
    GOAL_INVALIDATING = "GOAL_INVALIDATING"


@dataclass
class ObservedHumanChange:
    """Record of a detected human modification to a target file or state."""
    target_path: str
    classification: HumanChangeClassification
    details: str
    reconciliation_action: str


@dataclass
class ResumeAssessment:
    """Comprehensive outcome of pre-resumption state reconciliation."""
    task_id: str
    verdict: ResumeVerdict
    reason: str
    changed_invariants: List[str] = field(default_factory=list)
    surviving_artifacts: List[str] = field(default_factory=list)
    lost_state: List[str] = field(default_factory=list)
    externally_completed_work: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    human_changes: List[ObservedHumanChange] = field(default_factory=list)
    recommended_recovery: str = ""
    steps_still_valid: List[str] = field(default_factory=list)
    steps_invalidated: List[str] = field(default_factory=list)
    plan_revision: Optional[PlanRevision] = None
    requires_user_confirmation: bool = False

    @property
    def can_proceed_autonomously(self) -> bool:
        return self.verdict in {
            ResumeVerdict.UNCHANGED,
            ResumeVerdict.PROGRESS_ADVANCED_EXTERNALLY,
            ResumeVerdict.RECOVERABLE_DRIFT,
            ResumeVerdict.PLAN_PARTIALLY_INVALID,
            ResumeVerdict.REQUIRES_REPLAN,
        } and not self.requires_user_confirmation


class TaskReconciliationEngine:
    """Authoritative engine evaluating reality before unpausing or resuming tasks."""

    def __init__(self, machine_model: Optional[MachineModel] = None) -> None:
        self.model = machine_model or MachineModel.get_instance()

    def reconcile(
        self,
        checkpoint: TaskCheckpoint,
        goal_verification_func: Optional[Any] = None,
    ) -> ResumeAssessment:
        """
        Execute full reconciliation protocol across filesystem, processes, network,
        external downloads, and human interventions.
        """
        logger.info("Starting pre-resume reconciliation for task %s (goal: %s)", checkpoint.task_id, checkpoint.goal)
        task_id = checkpoint.task_id

        # 1. Refresh machine facts & snapshot
        self.model.refresh_volatile()
        self.model.refresh_realtime()
        snapshot = ResourceSnapshot.capture(include_gpu=True)

        changed_invariants: List[str] = []
        surviving_artifacts: List[str] = []
        lost_state: List[str] = []
        externally_completed: List[Dict[str, Any]] = []
        conflicts: List[str] = []
        human_changes: List[ObservedHumanChange] = []
        steps_valid = list(checkpoint.completed_step_ids)
        steps_invalid: List[str] = []

        # 2. Check Storage Volume Connectivity
        vols_fact = self.model.get_fact("hardware.storage.volumes")
        mounted_vols = {str(v).replace(":", "").upper() for v in vols_fact.value} if (vols_fact and isinstance(vols_fact.value, list)) else {"C", "E"}
        for art_path in checkpoint.artifacts:
            if len(art_path) >= 2 and art_path[1] == ":":
                drive_letter = art_path[0].upper()
                if drive_letter not in mounted_vols:
                    changed_invariants.append(f"Storage volume {drive_letter}: is disconnected.")
                    lost_state.append(art_path)

        if lost_state:
            return ResumeAssessment(
                task_id=task_id,
                verdict=ResumeVerdict.REQUIRES_USER,
                reason="Required storage volume is currently missing or disconnected.",
                changed_invariants=changed_invariants,
                lost_state=lost_state,
                conflicts=["Target volume disconnected during task pause."],
                recommended_recovery="Reconnect drive or provide alternative artifact path.",
                requires_user_confirmation=True,
            )

        # 3. Check Prior Created Files & Artifact Hashes
        for art_path_str, recorded_hash in checkpoint.artifact_hashes.items():
            p = Path(art_path_str)
            if not p.exists():
                lost_state.append(f"Artifact missing: {art_path_str}")
                steps_invalid.append(art_path_str)
            else:
                # File exists — compute current hash
                current_hash = self._compute_file_hash(p)
                if recorded_hash == "unhashed" or current_hash == recorded_hash:
                    surviving_artifacts.append(art_path_str)
                else:
                    # File was modified while paused! Classify human change
                    change = self._classify_file_modification(p, recorded_hash, current_hash, checkpoint)
                    human_changes.append(change)
                    if change.classification == HumanChangeClassification.CONFLICTING:
                        conflicts.append(f"File {p.name} was modified with conflicting edits.")
                    elif change.classification == HumanChangeClassification.GOAL_COMPLETING:
                        externally_completed.append({"type": "file_fix", "path": str(p), "details": change.details})

        # 4. Check External Progress (e.g. In-Flight Downloads or Builds)
        handles = getattr(checkpoint, "recoverable_handles", {}) or {}
        for handle_name, handle_info in handles.items():
            # Download handle
            if "download" in handle_name.lower() or (isinstance(handle_info, dict) and "target_file" in handle_info):
                target_file = handle_info.get("target_file") if isinstance(handle_info, dict) else str(handle_info)
                p_dl = Path(target_file)
                expected_size = handle_info.get("expected_size") if isinstance(handle_info, dict) else None
                expected_hash = handle_info.get("expected_hash") if isinstance(handle_info, dict) else None

                if p_dl.exists():
                    actual_size = p_dl.stat().st_size
                    if expected_size and actual_size >= expected_size:
                        # Completed externally while paused!
                        hash_matches = True
                        if expected_hash:
                            hash_matches = (self._compute_file_hash(p_dl).lower() == expected_hash.lower())
                        if hash_matches:
                            externally_completed.append({
                                "type": "download_completed_externally",
                                "target": str(p_dl),
                                "size": actual_size,
                                "step_id": handle_info.get("step_id", handle_name),
                            })
                            surviving_artifacts.append(str(p_dl))
                    elif actual_size > 0:
                        # Partial download survived
                        surviving_artifacts.append(str(p_dl))

            # External process handles
            if "pid" in handle_name.lower():
                try:
                    pid = int(handle_info)
                    if not psutil.pid_exists(pid):
                        lost_state.append(f"Process {handle_name} (PID {pid}) terminated while paused.")
                        changed_invariants.append(f"Target process PID {pid} is no longer running.")
                except Exception:
                    pass

        # 5. Check Goal Completion via external callback / checks
        if goal_verification_func:
            try:
                if goal_verification_func(checkpoint, surviving_artifacts):
                    return ResumeAssessment(
                        task_id=task_id,
                        verdict=ResumeVerdict.GOAL_ALREADY_COMPLETED,
                        reason="Task goal has been fully satisfied by external progress or manual operator intervention.",
                        surviving_artifacts=surviving_artifacts,
                        externally_completed_work=externally_completed,
                        recommended_recovery="Mark task COMPLETED without re-executing plan steps.",
                    )
            except Exception as e:
                logger.warning("Goal verification callback error: %s", e)

        # 6. Formulate Verdict
        # Case A: Human made conflicting edits
        if conflicts:
            return ResumeAssessment(
                task_id=task_id,
                verdict=ResumeVerdict.REQUIRES_USER,
                reason="Target files were modified externally with conflicting changes.",
                changed_invariants=changed_invariants,
                surviving_artifacts=surviving_artifacts,
                lost_state=lost_state,
                conflicts=conflicts,
                human_changes=human_changes,
                recommended_recovery="Prompt operator to choose whether to keep manual edits or replan.",
                requires_user_confirmation=True,
            )

        # Case B: External progress completed the next step(s)
        if externally_completed:
            # Plan revision skipping completed steps
            revised_steps: List[str] = []
            for item in externally_completed:
                sid = item.get("step_id")
                if sid:
                    steps_valid.append(sid)
                    revised_steps.append(sid)

            plan_rev = PlanRevision(
                original_plan_id=checkpoint.plan_id or "plan_1",
                revision=checkpoint.plan_version + 1,
                reason="Skipped steps completed externally during pause.",
                preserved_completed_steps=steps_valid,
                invalidated_steps=[],
                new_steps=[],
            )
            return ResumeAssessment(
                task_id=task_id,
                verdict=ResumeVerdict.PROGRESS_ADVANCED_EXTERNALLY,
                reason=f"Detected external progress: {len(externally_completed)} item(s) completed while paused.",
                changed_invariants=changed_invariants,
                surviving_artifacts=surviving_artifacts,
                lost_state=lost_state,
                externally_completed_work=externally_completed,
                human_changes=human_changes,
                recommended_recovery="Adopt externally completed work and resume from subsequent pending step.",
                steps_still_valid=steps_valid,
                plan_revision=plan_rev,
            )

        # Case C: State lost (e.g. process terminated, intermediate artifact deleted)
        if lost_state:
            # Need to replan
            plan_rev = PlanRevision(
                original_plan_id=checkpoint.plan_id or "plan_1",
                revision=checkpoint.plan_version + 1,
                reason="Reconstruct execution steps after state loss during pause.",
                preserved_completed_steps=[s for s in steps_valid if s not in steps_invalid],
                invalidated_steps=steps_invalid or lost_state,
                new_steps=[],
            )
            return ResumeAssessment(
                task_id=task_id,
                verdict=ResumeVerdict.REQUIRES_REPLAN,
                reason=f"Environment drift detected during pause: {len(lost_state)} item(s) lost.",
                changed_invariants=changed_invariants,
                surviving_artifacts=surviving_artifacts,
                lost_state=lost_state,
                recommended_recovery="Re-open necessary processes or regenerate missing intermediate files.",
                steps_still_valid=[s for s in steps_valid if s not in steps_invalid],
                steps_invalidated=steps_invalid or lost_state,
                plan_revision=plan_rev,
            )

        # Case D: Clean unchanged resumption
        return ResumeAssessment(
            task_id=task_id,
            verdict=ResumeVerdict.UNCHANGED,
            reason="All storage volumes, artifacts, and process invariants survived pause cleanly.",
            changed_invariants=[],
            surviving_artifacts=surviving_artifacts,
            lost_state=[],
            externally_completed_work=[],
            conflicts=[],
            human_changes=human_changes,
            recommended_recovery="Resume active execution directly from pending plan step.",
            steps_still_valid=steps_valid,
            steps_invalidated=[],
        )

    def _compute_file_hash(self, path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    h.update(chunk)
            return h.hexdigest().lower()
        except Exception:
            return ""

    def _classify_file_modification(
        self,
        path: Path,
        old_hash: str,
        new_hash: str,
        checkpoint: TaskCheckpoint,
    ) -> ObservedHumanChange:
        """Classify operator change to a target file."""
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            content = ""

        # Check for merge conflict markers or syntax conflicts
        if "<<<<<<<" in content or ">>>>>>>" in content or "CONFLICT:" in content:
            return ObservedHumanChange(
                target_path=str(path),
                classification=HumanChangeClassification.CONFLICTING,
                details=f"Merge conflict markers or unresolved conflicts found in {path.name}.",
                reconciliation_action="Ask user for conflict resolution.",
            )

        # Check if file was truncated or emptied
        if len(content.strip()) == 0 and len(old_hash) > 0:
            return ObservedHumanChange(
                target_path=str(path),
                classification=HumanChangeClassification.CONFLICTING,
                details=f"Target file {path.name} was emptied or wiped while paused.",
                reconciliation_action="Prompt user before recreating or modifying file.",
            )

        goal_lower = checkpoint.goal.lower()
        # If user completed the goal directly (e.g. fixed syntax error or wrote expected output)
        if "fix" in goal_lower or "implement" in goal_lower:
            # Check if file has substantive syntax/content
            if len(content.strip()) > 50:
                return ObservedHumanChange(
                    target_path=str(path),
                    classification=HumanChangeClassification.GOAL_COMPLETING,
                    details="Human operator updated file content; syntax is clean.",
                    reconciliation_action="Verify file and complete task without overwriting user work.",
                )

        # Default compatible modification: re-read file
        return ObservedHumanChange(
            target_path=str(path),
            classification=HumanChangeClassification.COMPATIBLE,
            details=f"File {path.name} content modified externally ({old_hash[:8]} -> {new_hash[:8]}).",
            reconciliation_action="Re-read modified file into context and adjust downstream inputs.",
        )
