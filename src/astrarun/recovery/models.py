"""Data contracts for structured failure diagnostics and recovery actions."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FailureCategory(str, Enum):
    """Authoritative taxonomy of workstation agent failure modes."""
    ROUTING_UNCERTAIN = "ROUTING_UNCERTAIN"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_CHANGED = "TARGET_CHANGED"
    ACTION_FAILED = "ACTION_FAILED"
    OBSERVATION_INCONCLUSIVE = "OBSERVATION_INCONCLUSIVE"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    RESOURCE_CLEANUP_FAILED = "RESOURCE_CLEANUP_FAILED"
    USER_TAKEOVER = "USER_TAKEOVER"
    TIMEOUT = "TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNRECOVERABLE = "UNRECOVERABLE"


class RecoveryAction(str, Enum):
    """Authoritative recovery decisions emitted by the fallback engine."""
    RETRY_SAME = "RETRY_SAME"
    RETRY_WITH_NEW_OBSERVATION = "RETRY_WITH_NEW_OBSERVATION"
    REPLAN = "REPLAN"
    SELECT_ALTERNATIVE_CAPABILITY = "SELECT_ALTERNATIVE_CAPABILITY"
    SELECT_ALTERNATIVE_MODEL = "SELECT_ALTERNATIVE_MODEL"
    FALLBACK_TO_DETERMINISTIC_METHOD = "FALLBACK_TO_DETERMINISTIC_METHOD"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    REQUEST_CONFIRMATION = "REQUEST_CONFIRMATION"
    PAUSE_FOR_USER = "PAUSE_FOR_USER"
    ROLLBACK = "ROLLBACK"
    CLEANUP_AND_FAIL = "CLEANUP_AND_FAIL"
    FAIL_CLOSED = "FAIL_CLOSED"


@dataclass
class FailureEvidence:
    """Structured empirical evidence detailing why an operation or verification failed."""
    failure_category: FailureCategory
    what_failed: str
    evidence_summary: str
    evidence_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: str = "runtime_loop"
    world_state_changed: bool = False
    original_goal_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_category": self.failure_category.value,
            "what_failed": self.what_failed,
            "evidence_summary": self.evidence_summary,
            "evidence_data": self.evidence_data,
            "timestamp": self.timestamp,
            "source": self.source,
            "world_state_changed": self.world_state_changed,
            "original_goal_valid": self.original_goal_valid,
        }


@dataclass
class FallbackDecision:
    """Immutable record of an evaluated recovery decision answering the 8 diagnostic questions."""
    decision_id: str
    failure_evidence: FailureEvidence
    action: RecoveryAction
    is_retry_safe: bool
    world_state_changed: bool
    original_goal_valid: bool
    alternative_selected: Optional[str] = None
    preference_rationale: str = ""
    new_verification_required: Optional[str] = None
    fingerprint: str = ""
    attempt_number: int = 1
    policy_verdict: str = "PERMIT"  # "PERMIT", "CONFIRM", or "BLOCK"
    timestamp: float = field(default_factory=time.time)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "failure_evidence": self.failure_evidence.to_dict(),
            "action": self.action.value,
            "is_retry_safe": self.is_retry_safe,
            "world_state_changed": self.world_state_changed,
            "original_goal_valid": self.original_goal_valid,
            "alternative_selected": self.alternative_selected,
            "preference_rationale": self.preference_rationale,
            "new_verification_required": self.new_verification_required,
            "fingerprint": self.fingerprint,
            "attempt_number": self.attempt_number,
            "policy_verdict": self.policy_verdict,
            "timestamp": self.timestamp,
            "provenance": self.provenance,
        }

    @staticmethod
    def compute_fingerprint(category: FailureCategory, target: str, action: str, error_digest: str) -> str:
        h = hashlib.sha256()
        h.update(f"{category.value}:{target}:{action}:{error_digest}".encode("utf-8"))
        return h.hexdigest()[:16]
