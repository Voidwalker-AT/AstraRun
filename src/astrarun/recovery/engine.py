"""Intelligent Fallback and Recovery Engine for AstraRun.

Enforces structured diagnostics, fallback hierarchies, loop prevention budgets,
and unbreakable security boundaries across all execution recovery paths.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.recovery.models import (
    FailureCategory,
    FailureEvidence,
    FallbackDecision,
    RecoveryAction,
)

logger = get_logger("astrarun.recovery.engine")


class IntelligentFallbackEngine:
    """
    Evaluates failure evidence, selects governed recovery actions according to
    strict capability hierarchies, and prevents oscillation loops with bounded budgets.
    """

    MAX_RETRIES_PER_FINGERPRINT = 2
    MAX_TOTAL_REPLANS = 3
    CYCLE_WINDOW = 4

    def __init__(self, capability_registry: Optional[Any] = None) -> None:
        self.capability_registry = capability_registry
        self._fingerprint_counts: Dict[str, int] = {}
        self._decision_history: List[FallbackDecision] = []

    def evaluate_failure(
        self,
        evidence: FailureEvidence,
        task_id: Optional[str] = None,
        candidate_alternatives: Optional[List[str]] = None,
        security_override_block: bool = False,
        requires_confirmation: bool = False,
    ) -> FallbackDecision:
        """
        Evaluate structured failure evidence and produce a provenanced FallbackDecision.
        Answers all 8 diagnostic questions.
        """
        decision_id = f"dec_{uuid.uuid4().hex[:8]}"
        category = evidence.failure_category
        target = evidence.what_failed
        error_digest = evidence.evidence_summary[:64]

        fingerprint = FallbackDecision.compute_fingerprint(
            category, target, evidence.source, error_digest
        )
        attempt_num = self._fingerprint_counts.get(fingerprint, 0) + 1
        self._fingerprint_counts[fingerprint] = attempt_num

        # ---------------------------------------------------------------------
        # 1. SECURITY INVARIANT: BLOCK remains BLOCK; CONFIRM remains CONFIRM
        # ---------------------------------------------------------------------
        if category == FailureCategory.POLICY_BLOCKED or security_override_block:
            decision = FallbackDecision(
                decision_id=decision_id,
                failure_evidence=evidence,
                action=RecoveryAction.FAIL_CLOSED,
                is_retry_safe=False,
                world_state_changed=evidence.world_state_changed,
                original_goal_valid=False,
                alternative_selected=None,
                preference_rationale="Security policy violation must fail closed; fallback bypass prohibited.",
                new_verification_required=None,
                fingerprint=fingerprint,
                attempt_number=attempt_num,
                policy_verdict="BLOCK",
                provenance={"enforcement": "ExecutionBroker_ActionGate", "invariant": "BLOCK_REMAINS_BLOCK"},
            )
            self._record_decision(decision)
            return decision

        if requires_confirmation:
            decision = FallbackDecision(
                decision_id=decision_id,
                failure_evidence=evidence,
                action=RecoveryAction.REQUEST_CONFIRMATION,
                is_retry_safe=False,
                world_state_changed=evidence.world_state_changed,
                original_goal_valid=evidence.original_goal_valid,
                alternative_selected=None,
                preference_rationale="Operation requires explicit user confirmation before proceeding.",
                new_verification_required="user_confirmation_ack",
                fingerprint=fingerprint,
                attempt_number=attempt_num,
                policy_verdict="CONFIRM",
                provenance={"enforcement": "ActionGate", "invariant": "CONFIRM_REMAINS_CONFIRM"},
            )
            self._record_decision(decision)
            return decision

        # ---------------------------------------------------------------------
        # 2. LOOP PREVENTION: Bounded budgets and cycle detection
        # ---------------------------------------------------------------------
        # A. Budget exhaustion for this specific failure fingerprint
        if attempt_num > self.MAX_RETRIES_PER_FINGERPRINT:
            logger.warning(
                "Recovery budget exceeded for fingerprint %s (%d attempts). Escalating to CLEANUP_AND_FAIL.",
                fingerprint, attempt_num
            )
            decision = FallbackDecision(
                decision_id=decision_id,
                failure_evidence=evidence,
                action=RecoveryAction.CLEANUP_AND_FAIL,
                is_retry_safe=False,
                world_state_changed=evidence.world_state_changed,
                original_goal_valid=False,
                alternative_selected=None,
                preference_rationale=f"Exceeded max retries ({self.MAX_RETRIES_PER_FINGERPRINT}) for failure fingerprint.",
                new_verification_required="cleanup_verification",
                fingerprint=fingerprint,
                attempt_number=attempt_num,
                policy_verdict="ESCALATED_TERMINAL",
                provenance={"loop_guard": "budget_exhaustion"},
            )
            self._record_decision(decision)
            return decision

        # B. Cycle detection: A -> B -> A -> B oscillation
        if self._detect_cycle(fingerprint):
            logger.warning("Oscillation cycle detected in recovery history for fingerprint %s. Escalating to FAIL_CLOSED.", fingerprint)
            decision = FallbackDecision(
                decision_id=decision_id,
                failure_evidence=evidence,
                action=RecoveryAction.FAIL_CLOSED,
                is_retry_safe=False,
                world_state_changed=evidence.world_state_changed,
                original_goal_valid=False,
                alternative_selected=None,
                preference_rationale="Recovery oscillation cycle (A -> B -> A) detected; terminating loop.",
                new_verification_required=None,
                fingerprint=fingerprint,
                attempt_number=attempt_num,
                policy_verdict="CYCLE_TERMINATED",
                provenance={"loop_guard": "cycle_detection"},
            )
            self._record_decision(decision)
            return decision

        # ---------------------------------------------------------------------
        # 3. HIERARCHICAL RECOVERY MAPPING
        # ---------------------------------------------------------------------
        if category in (FailureCategory.ROUTING_UNCERTAIN, FailureCategory.MISSING_CONTEXT):
            action = RecoveryAction.REQUEST_CLARIFICATION
            alt = None
            rationale = "Context is missing or intent is ambiguous; user clarification required."
            new_ver = "user_input_clarification"
            safe_retry = False

        elif category in (FailureCategory.TARGET_NOT_FOUND, FailureCategory.TARGET_CHANGED, FailureCategory.OBSERVATION_INCONCLUSIVE, FailureCategory.TIMEOUT):
            action = RecoveryAction.RETRY_WITH_NEW_OBSERVATION
            alt = "fresh_desktop_observation"
            rationale = "Target environment shifted or observation stale; refreshing live desktop sensor state."
            new_ver = "target_presence_observation"
            safe_retry = True

        elif category == FailureCategory.MODEL_UNAVAILABLE:
            action = RecoveryAction.SELECT_ALTERNATIVE_MODEL
            alt = candidate_alternatives[0] if candidate_alternatives else "deterministic_rules"
            rationale = "Preferred model unavailable; failing over to configured secondary model or deterministic rules."
            new_ver = "model_structured_output_valid"
            safe_retry = True

        elif category == FailureCategory.MODEL_OUTPUT_INVALID:
            action = RecoveryAction.FALLBACK_TO_DETERMINISTIC_METHOD
            alt = "deterministic_capability_retrieval"
            rationale = "Model emitted malformed output; falling back to authoritative deterministic capability matching."
            new_ver = "deterministic_plan_validation"
            safe_retry = True

        elif category == FailureCategory.CAPABILITY_UNAVAILABLE or category == FailureCategory.ACTION_FAILED:
            if candidate_alternatives:
                action = RecoveryAction.SELECT_ALTERNATIVE_CAPABILITY
                alt = candidate_alternatives[0]
                rationale = f"Primary capability {target} failed; selecting alternative {alt} from hierarchy."
                new_ver = f"capability_execution_success_{alt}"
                safe_retry = False
            else:
                action = RecoveryAction.REPLAN
                alt = "replan_execution_graph"
                rationale = f"Capability {target} failed without equivalent alternative; replanning task DAG."
                new_ver = "replan_quality_validation"
                safe_retry = False

        elif category in (FailureCategory.PRECONDITION_FAILED, FailureCategory.POSTCONDITION_FAILED, FailureCategory.VERIFICATION_FAILED):
            action = RecoveryAction.REPLAN
            alt = "replan_with_remediation_step"
            rationale = f"Verification oracle or contract pre/postcondition failed for {target}; replanning with remediation."
            new_ver = "independent_goal_verification"
            safe_retry = False

        elif category == FailureCategory.RESOURCE_CLEANUP_FAILED:
            action = RecoveryAction.CLEANUP_AND_FAIL
            alt = "forced_ledger_resource_reclamation"
            rationale = "Resource ledger detected unreleased child resources; enforcing hard cleanup and failing task."
            new_ver = "resource_ledger_zero_residue"
            safe_retry = False

        elif category == FailureCategory.USER_TAKEOVER:
            action = RecoveryAction.PAUSE_FOR_USER
            alt = "wait_for_user_idle"
            rationale = "User interaction detected; pausing autonomous execution to preserve user autonomy."
            new_ver = "user_resume_signal"
            safe_retry = False

        elif category == FailureCategory.PROVIDER_UNAVAILABLE:
            action = RecoveryAction.FALLBACK_TO_DETERMINISTIC_METHOD
            alt = "local_resident_tools"
            rationale = "External provider unreachable; falling back to local resident execution."
            new_ver = "local_execution_verification"
            safe_retry = True

        else:  # UNRECOVERABLE
            action = RecoveryAction.FAIL_CLOSED
            alt = None
            rationale = f"Unrecoverable state encountered ({target}); failing closed safely."
            new_ver = None
            safe_retry = False

        decision = FallbackDecision(
            decision_id=decision_id,
            failure_evidence=evidence,
            action=action,
            is_retry_safe=safe_retry,
            world_state_changed=evidence.world_state_changed,
            original_goal_valid=evidence.original_goal_valid,
            alternative_selected=alt,
            preference_rationale=rationale,
            new_verification_required=new_ver,
            fingerprint=fingerprint,
            attempt_number=attempt_num,
            policy_verdict="PERMIT",
            provenance={
                "task_id": task_id,
                "strategy": "IntelligentFallbackHierarchy_v1",
                "timestamp": time.time(),
            },
        )
        self._record_decision(decision)
        return decision

    def _detect_cycle(self, current_fingerprint: str) -> bool:
        """Detect A -> B -> A cycle within recent window."""
        recent = [d.fingerprint for d in self._decision_history[-self.CYCLE_WINDOW:]]
        if len(recent) >= 2 and recent[-1] != current_fingerprint and current_fingerprint in recent:
            return True
        return False

    def _record_decision(self, decision: FallbackDecision) -> None:
        self._decision_history.append(decision)
        logger.info(
            "FallbackDecision [%s]: %s -> %s (alt=%s, policy=%s, attempt=%d)",
            decision.decision_id,
            decision.failure_evidence.failure_category.value,
            decision.action.value,
            decision.alternative_selected,
            decision.policy_verdict,
            decision.attempt_number,
        )

    def get_history(self) -> List[FallbackDecision]:
        return list(self._decision_history)

    def reset(self) -> None:
        self._fingerprint_counts.clear()
        self._decision_history.clear()
