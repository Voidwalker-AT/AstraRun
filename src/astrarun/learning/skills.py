"""Skill Manager for AstraRun Learning Foundation.

Manages the lifecycle, versioning, rollback, and compilation of learned skill candidates
into executable Workflow objects. Enforces human review gating prior to activation.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from astrarun.core.logging import get_logger
from astrarun.core.models import ToolRisk
from astrarun.learning.models import (
    AuditAction,
    AuditEvent,
    SkillCandidate,
    SkillStatus,
    SkillStep,
)
from astrarun.learning.persistence import LearningPersistence
from astrarun.workflows.models import Workflow, WorkflowStep

logger = get_logger("astrarun.learning.skills")


class SkillManager:
    """
    Coordinates candidate skill proposals, human review, version upgrades, and workflow conversion.
    """

    def __init__(self, persistence: Optional[LearningPersistence] = None) -> None:
        self.persistence = persistence or LearningPersistence()

    def propose_skill(self, candidate: SkillCandidate) -> SkillCandidate:
        """
        Record a newly discovered skill candidate awaiting human review.
        """
        candidate.status = SkillStatus.PENDING_REVIEW
        self.persistence.save_skill(candidate)

        self.persistence.record_audit(
            AuditEvent(
                id=str(uuid.uuid4()),
                action=AuditAction.SKILL_PROPOSED,
                entity_type="skill",
                entity_id=candidate.id,
                timestamp=time.time(),
                details={"name": candidate.name, "step_count": len(candidate.steps)},
            )
        )
        logger.info("Proposed skill '%s' (%s) awaiting review", candidate.name, candidate.id)
        return candidate

    def get_skill(self, skill_id: str) -> Optional[SkillCandidate]:
        """Fetch skill by ID."""
        return self.persistence.get_skill(skill_id)

    def list_skills(self, status: Optional[SkillStatus] = None) -> list[SkillCandidate]:
        """List skills matching status filter."""
        return self.persistence.list_skills(status=status)

    def approve_skill(self, skill_id: str, review_notes: Optional[str] = None) -> Optional[SkillCandidate]:
        """
        User approves a skill, transitioning it to ACTIVE status and making it executable.
        """
        skill = self.persistence.get_skill(skill_id)
        if not skill:
            return None

        skill.status = SkillStatus.ACTIVE
        skill.confidence = max(0.95, skill.confidence)
        skill.updated_at = time.time()
        if review_notes:
            skill.review_notes = review_notes
        self.persistence.save_skill(skill)

        self.persistence.record_audit(
            AuditEvent(
                id=str(uuid.uuid4()),
                action=AuditAction.SKILL_APPROVED,
                entity_type="skill",
                entity_id=skill.id,
                timestamp=time.time(),
                details={"name": skill.name, "version": skill.version},
            )
        )
        logger.info("Skill '%s' approved and activated", skill.name)
        return skill

    def reject_skill(self, skill_id: str, review_notes: Optional[str] = None) -> Optional[SkillCandidate]:
        """User rejects a skill candidate."""
        skill = self.persistence.get_skill(skill_id)
        if not skill:
            return None

        skill.status = SkillStatus.REJECTED
        skill.updated_at = time.time()
        if review_notes:
            skill.review_notes = review_notes
        self.persistence.save_skill(skill)

        self.persistence.record_audit(
            AuditEvent(
                id=str(uuid.uuid4()),
                action=AuditAction.SKILL_REJECTED,
                entity_type="skill",
                entity_id=skill.id,
                timestamp=time.time(),
                details={"name": skill.name},
            )
        )
        return skill

    def disable_skill(self, skill_id: str) -> Optional[SkillCandidate]:
        """User disables an active skill."""
        skill = self.persistence.get_skill(skill_id)
        if not skill:
            return None

        skill.status = SkillStatus.DISABLED
        skill.updated_at = time.time()
        self.persistence.save_skill(skill)
        return skill

    def delete_skill(self, skill_id: str) -> bool:
        """Permanently delete a skill."""
        skill = self.persistence.get_skill(skill_id)
        if not skill:
            return False

        deleted = self.persistence.delete_skill(skill_id)
        if deleted:
            self.persistence.record_audit(
                AuditEvent(
                    id=str(uuid.uuid4()),
                    action=AuditAction.SKILL_DEPRECATED,
                    entity_type="skill",
                    entity_id=skill_id,
                    timestamp=time.time(),
                    details={"name": skill.name},
                )
            )
        return deleted

    def update_skill_steps(self, skill_id: str, new_steps: list[SkillStep]) -> Optional[SkillCandidate]:
        """
        Update steps on a skill, incrementing its version number for rollback and tracking.
        """
        skill = self.persistence.get_skill(skill_id)
        if not skill:
            return None

        old_ver = skill.version
        skill.steps = new_steps
        skill.version = old_ver + 1
        skill.updated_at = time.time()
        self.persistence.save_skill(skill)

        self.persistence.record_audit(
            AuditEvent(
                id=str(uuid.uuid4()),
                action=AuditAction.SKILL_APPROVED,
                entity_type="skill",
                entity_id=skill.id,
                timestamp=time.time(),
                details={"name": skill.name, "old_version": old_ver, "new_version": skill.version},
            )
        )
        return skill

    def to_workflow(
        self,
        skill: SkillCandidate,
        parameter_overrides: Optional[dict[str, Any]] = None,
    ) -> Workflow:
        """
        Convert an active SkillCandidate into an executable Workflow definition.
        Substitutes parameter bindings with overrides or defaults.
        """
        if skill.status != SkillStatus.ACTIVE:
            raise ValueError(f"Skill '{skill.name}' is not ACTIVE (status={skill.status.value}). Only active skills can be executed.")

        overrides = parameter_overrides or {}
        workflow_steps: list[WorkflowStep] = []

        for s in skill.steps:
            args = dict(s.arguments)
            # Apply parameter substitutions
            for arg_key, param_name in s.parameter_bindings.items():
                if param_name in overrides:
                    args[arg_key] = overrides[param_name]
                else:
                    # Find default in parameter definitions
                    for p in skill.parameters:
                        if p["name"] == param_name and "default" in p:
                            args[arg_key] = p["default"]
                            break

            workflow_steps.append(
                WorkflowStep(
                    step_id=f"step_{s.step_index}_{s.capability_id}",
                    name=f"Step {s.step_index}: {s.capability_id}",
                    tool=s.capability_id,
                    arguments=args,
                    critical=True,
                )
            )

        # Map risk level
        risk_map = {
            "LOW": ToolRisk.LOW,
            "MEDIUM": ToolRisk.MEDIUM,
            "HIGH": ToolRisk.HIGH,
            "CRITICAL": ToolRisk.BLOCKED,
        }
        workflow_risk = risk_map.get(skill.max_risk_level, ToolRisk.LOW)

        return Workflow(
            id=f"learned_skill_{skill.id}",
            name=skill.name,
            description=skill.description,
            steps=workflow_steps,
            risk=workflow_risk,
            rollback_supported=False,
        )
