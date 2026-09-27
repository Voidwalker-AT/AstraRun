"""Domain models, enums, and data contracts for AstraRun Learning Foundation (v0.8.5).

Defines strongly-typed representations for semantic memories, evidence references,
corrections, user preferences, skill candidates, steps, and audit logs.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MemoryNamespace(str, Enum):
    """Categorical namespaces isolating learned facts and preventing cross-domain pollution."""
    ALIAS = "ALIAS"
    PREFERENCE = "PREFERENCE"
    WORKFLOW = "WORKFLOW"
    ENTITY_ATTRIBUTE = "ENTITY_ATTRIBUTE"
    TEACHING = "TEACHING"


class MemoryStatus(str, Enum):
    """Lifecycle states for learned semantic knowledge."""
    CANDIDATE = "CANDIDATE"      # Discovered by evidence, confidence < threshold or support < min
    ACTIVE = "ACTIVE"            # Confirmed by user or high confidence (>= 0.85) and support >= 3
    REJECTED = "REJECTED"        # User explicitly rejected or contradicted
    DEPRECATED = "DEPRECATED"    # Decayed over time or replaced by a newer version
    CONFLICTED = "CONFLICTED"    # Ambiguous conflicting targets with similar confidence


class EvidenceType(str, Enum):
    """Provenance categories of verifiable runtime occurrences supporting or refuting knowledge."""
    CONFIRMATION_ACCEPTED = "CONFIRMATION_ACCEPTED"  # User clicked Confirm in ActionGate dialog
    CONFIRMATION_REJECTED = "CONFIRMATION_REJECTED"  # User clicked Reject or Cancel in ActionGate dialog
    USER_CORRECTION = "USER_CORRECTION"              # User immediately modified target or cancelled and retried
    EXPLICIT_TEACHING = "EXPLICIT_TEACHING"          # User used explicit teaching syntax ("alias X to Y")
    SUCCESSFUL_EXECUTION = "SUCCESSFUL_EXECUTION"    # Task executed to completion without correction
    EXECUTION_FAILED = "EXECUTION_FAILED"            # Capability failed during execution
    USER_QUERY_SELECTION = "USER_QUERY_SELECTION"    # User selected candidate from disambiguation dialog


class SkillStatus(str, Enum):
    """Lifecycle states for reusable composite skill candidates."""
    CANDIDATE = "CANDIDATE"            # Mined by PatternMiner from recurring task sequences
    PENDING_REVIEW = "PENDING_REVIEW"  # Staged for user confirmation in Skill Review dialog
    ACTIVE = "ACTIVE"                  # Approved by user and executable
    REJECTED = "REJECTED"              # User rejected the proposed skill
    DEPRECATED = "DEPRECATED"          # Superseded by newer version
    DISABLED = "DISABLED"              # Temporarily turned off by user


class AuditAction(str, Enum):
    """Immutable audit trail actions for transparency and accountability."""
    MEMORY_CREATED = "MEMORY_CREATED"
    MEMORY_UPDATED = "MEMORY_UPDATED"
    MEMORY_PROMOTED = "MEMORY_PROMOTED"
    MEMORY_DEPRECATED = "MEMORY_DEPRECATED"
    MEMORY_DELETED = "MEMORY_DELETED"
    SKILL_PROPOSED = "SKILL_PROPOSED"
    SKILL_APPROVED = "SKILL_APPROVED"
    SKILL_REJECTED = "SKILL_REJECTED"
    SKILL_DEPRECATED = "SKILL_DEPRECATED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    DATA_PRUNED = "DATA_PRUNED"
    DATA_CLEARED = "DATA_CLEARED"


@dataclass(frozen=True)
class EvidenceReference:
    """
    Immutable pointer to a verified historical task or event providing provenance for a memory.
    """
    task_id: str
    conversation_id: str
    event_id: Optional[str] = None
    evidence_type: EvidenceType = EvidenceType.SUCCESSFUL_EXECUTION
    timestamp: float = field(default_factory=time.time)
    weight: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "event_id": self.event_id,
            "evidence_type": self.evidence_type.value,
            "timestamp": self.timestamp,
            "weight": self.weight,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvidenceReference:
        return cls(
            task_id=d["task_id"],
            conversation_id=d["conversation_id"],
            event_id=d.get("event_id"),
            evidence_type=EvidenceType(d.get("evidence_type", EvidenceType.SUCCESSFUL_EXECUTION.value)),
            timestamp=d.get("timestamp", time.time()),
            weight=float(d.get("weight", 1.0)),
            details=d.get("details", {}),
        )


@dataclass
class SemanticMemory:
    """
    Durable unit of workstation knowledge (alias, preference, or fact) with complete provenance.
    """
    id: str
    namespace: MemoryNamespace
    key: str
    value: Any
    target_type: str  # e.g. "application", "project", "folder", "command", "preference"
    status: MemoryStatus = MemoryStatus.CANDIDATE
    confidence: float = 0.0
    support_count: int = 1
    contradiction_count: int = 0
    evidence_refs: list[EvidenceReference] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    user_confirmed: bool = False
    pinned: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "namespace": self.namespace.value,
            "key": self.key,
            "value": self.value,
            "target_type": self.target_type,
            "status": self.status.value,
            "confidence": self.confidence,
            "support_count": self.support_count,
            "contradiction_count": self.contradiction_count,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "user_confirmed": self.user_confirmed,
            "pinned": self.pinned,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SemanticMemory:
        return cls(
            id=d["id"],
            namespace=MemoryNamespace(d["namespace"]),
            key=d["key"],
            value=d["value"],
            target_type=d["target_type"],
            status=MemoryStatus(d.get("status", MemoryStatus.CANDIDATE.value)),
            confidence=float(d.get("confidence", 0.0)),
            support_count=int(d.get("support_count", 1)),
            contradiction_count=int(d.get("contradiction_count", 0)),
            evidence_refs=[EvidenceReference.from_dict(r) for r in d.get("evidence_refs", [])],
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
            last_used_at=float(d.get("last_used_at", time.time())),
            user_confirmed=bool(d.get("user_confirmed", False)),
            pinned=bool(d.get("pinned", False)),
            metadata=d.get("metadata", {}),
        )


@dataclass
class Correction:
    """
    Record of a user correction where an erroneous mapping was replaced with a corrected one.
    """
    id: str
    task_id: str
    conversation_id: str
    incorrect_mapping: dict[str, Any]
    corrected_mapping: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "incorrect_mapping": dict(self.incorrect_mapping),
            "corrected_mapping": dict(self.corrected_mapping),
            "timestamp": self.timestamp,
            "applied": self.applied,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Correction:
        return cls(
            id=d["id"],
            task_id=d["task_id"],
            conversation_id=d["conversation_id"],
            incorrect_mapping=d.get("incorrect_mapping", {}),
            corrected_mapping=d.get("corrected_mapping", {}),
            timestamp=float(d.get("timestamp", time.time())),
            applied=bool(d.get("applied", False)),
        )


@dataclass
class SkillStep:
    """
    Single discrete capability invocation within a compound reusable skill.
    """
    step_index: int
    capability_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    parameter_bindings: dict[str, str] = field(default_factory=dict)  # arg_name -> param_name
    requires_confirmation: bool = False
    risk_level: str = "LOW"  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "capability_id": self.capability_id,
            "arguments": dict(self.arguments),
            "parameter_bindings": dict(self.parameter_bindings),
            "requires_confirmation": self.requires_confirmation,
            "risk_level": self.risk_level,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SkillStep:
        return cls(
            step_index=int(d["step_index"]),
            capability_id=d["capability_id"],
            arguments=d.get("arguments", {}),
            parameter_bindings=d.get("parameter_bindings", {}),
            requires_confirmation=bool(d.get("requires_confirmation", False)),
            risk_level=d.get("risk_level", "LOW"),
        )


@dataclass
class SkillCandidate:
    """
    Reusable workflow routine mined from repetitive user task sequences or taught explicitly.
    Requires human review before execution activation.
    """
    id: str
    name: str
    description: str
    trigger_phrases: list[str] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    steps: list[SkillStep] = field(default_factory=list)
    status: SkillStatus = SkillStatus.CANDIDATE
    support_count: int = 1
    confidence: float = 0.0
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    evidence_task_ids: list[str] = field(default_factory=list)
    author: str = "pattern_miner"  # "pattern_miner" | "user_teaching"
    review_notes: Optional[str] = None

    @property
    def max_risk_level(self) -> str:
        """Calculate aggregate risk level from all composite steps."""
        risks = [s.risk_level for s in self.steps]
        if "CRITICAL" in risks:
            return "CRITICAL"
        if "HIGH" in risks:
            return "HIGH"
        if "MEDIUM" in risks:
            return "MEDIUM"
        return "LOW"

    @property
    def requires_confirmation(self) -> bool:
        """Skill requires confirmation if any step requires confirmation or risk is HIGH/CRITICAL."""
        return any(s.requires_confirmation for s in self.steps) or self.max_risk_level in {"HIGH", "CRITICAL"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_phrases": list(self.trigger_phrases),
            "parameters": list(self.parameters),
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "support_count": self.support_count,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "evidence_task_ids": list(self.evidence_task_ids),
            "author": self.author,
            "review_notes": self.review_notes,
            "max_risk_level": self.max_risk_level,
            "requires_confirmation": self.requires_confirmation,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SkillCandidate:
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            trigger_phrases=d.get("trigger_phrases", []),
            parameters=d.get("parameters", []),
            steps=[SkillStep.from_dict(s) for s in d.get("steps", [])],
            status=SkillStatus(d.get("status", SkillStatus.CANDIDATE.value)),
            support_count=int(d.get("support_count", 1)),
            confidence=float(d.get("confidence", 0.0)),
            version=int(d.get("version", 1)),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
            evidence_task_ids=d.get("evidence_task_ids", []),
            author=d.get("author", "pattern_miner"),
            review_notes=d.get("review_notes"),
        )


@dataclass(frozen=True)
class AuditEvent:
    """
    Append-only audit record tracking state changes in memory and skills.
    """
    id: str
    action: AuditAction
    entity_type: str  # "memory" | "skill" | "alias" | "preference"
    entity_id: str
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "timestamp": self.timestamp,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AuditEvent:
        return cls(
            id=d["id"],
            action=AuditAction(d["action"]),
            entity_type=d["entity_type"],
            entity_id=d["entity_id"],
            timestamp=float(d.get("timestamp", time.time())),
            details=d.get("details", {}),
        )
