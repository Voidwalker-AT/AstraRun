"""Training-Candidate Quality Gate for Hermes Trajectories and Transitions.

Independently validates that training candidates are backed by authentic,
semantically consistent, and physically proven evidence before they can be
promoted to the model training corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class RejectionReason(str, Enum):
    PREDICATE_TYPE_MISMATCH = "PREDICATE_TYPE_MISMATCH"
    MISSING_EVIDENCE_REFERENCE = "MISSING_EVIDENCE_REFERENCE"
    UNVERIFIED_TRANSITION_CLAIM = "UNVERIFIED_TRANSITION_CLAIM"
    POLARITY_CONTRADICTION = "POLARITY_CONTRADICTION"
    TAUTOLOGICAL_SELECTION = "TAUTOLOGICAL_SELECTION"
    UNATTACHED_OR_WRONG_DIALOG = "UNATTACHED_OR_WRONG_DIALOG"
    TAB_COUNT_UNCHANGED = "TAB_COUNT_UNCHANGED"
    IRRELEVANT_STATE_HASH_MUTATION = "IRRELEVANT_STATE_HASH_MUTATION"
    INVALID_HERMES_PROVENANCE = "INVALID_HERMES_PROVENANCE"
    FORCED_VERIFICATION = "FORCED_VERIFICATION"


@dataclass
class QualityGateResult:
    passed: bool
    rejection_reasons: List[str] = field(default_factory=list)
    rejection_details: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TrainingQualityGate:
    """Rigorous gate evaluating candidate trajectories and state transitions."""

    @classmethod
    def evaluate_transition(cls, transition: Dict[str, Any], target_pid: Optional[int] = None) -> QualityGateResult:
        rejections: List[str] = []
        details: List[str] = []

        is_verified = transition.get("transition_verified", False)
        exp_delta = transition.get("expected_delta", {}) or transition.get("expected_value", {})
        obs_delta = transition.get("observed_delta", {}) or transition.get("observed_value", {})
        raw_ref = transition.get("raw_evidence_reference", "")
        pred_type = transition.get("predicate_type", "")

        # 1. Missing raw evidence reference
        if not raw_ref or raw_ref in ("", "none", "UNVERIFIED", "missing_selection_observation"):
            rejections.append(RejectionReason.MISSING_EVIDENCE_REFERENCE.value)
            details.append("raw_evidence_reference is empty or placeholder")

        # 2. Forced verification without empirical truth
        if is_verified:
            eval_dict = transition.get("evaluation", {})
            if isinstance(eval_dict, dict) and eval_dict.get("passed") is False:
                rejections.append(RejectionReason.FORCED_VERIFICATION.value)
                details.append("transition_verified is True but evaluation['passed'] is False")

        # 3. Predicate type & schema consistency
        if "selection_active" in exp_delta:
            # Must have selection-specific fields
            if "selected_length" not in obs_delta and "observable" not in obs_delta:
                rejections.append(RejectionReason.PREDICATE_TYPE_MISMATCH.value)
                details.append("Expected selection_active but observed_delta lacks selection measurements")
            else:
                sel_len = obs_delta.get("selected_length", 0)
                doc_len = obs_delta.get("document_length", 0)
                if sel_len == 0 or (doc_len > 0 and sel_len != doc_len):
                    rejections.append(RejectionReason.TAUTOLOGICAL_SELECTION.value)
                    details.append(f"Selection invalid: selected_length={sel_len}, document_length={doc_len}")

        if "tabs_count_increased" in exp_delta:
            if "post_tabs_count" not in obs_delta and "delta" not in obs_delta:
                rejections.append(RejectionReason.PREDICATE_TYPE_MISMATCH.value)
                details.append("Expected tabs_count_increased but observed_delta lacks tab count data")
            else:
                pre_t = obs_delta.get("pre_tabs_count", 0)
                post_t = obs_delta.get("post_tabs_count", 0)
                delta = obs_delta.get("delta", post_t - pre_t)
                if delta <= 0 and post_t <= pre_t:
                    rejections.append(RejectionReason.TAB_COUNT_UNCHANGED.value)
                    details.append(f"Tab count failed to increase: pre={pre_t}, post={post_t}")

        if "find_dialog_opened" in exp_delta:
            if "dialog_found" not in obs_delta and "dialog_hwnds" not in obs_delta:
                rejections.append(RejectionReason.PREDICATE_TYPE_MISMATCH.value)
                details.append("Expected find_dialog_opened but observed_delta lacks dialog fields")
            else:
                dlg_found = obs_delta.get("dialog_found", False)
                dlg_pid = obs_delta.get("dialog_pid")
                dlg_cls = obs_delta.get("dialog_class", "")
                if not dlg_found:
                    rejections.append(RejectionReason.UNATTACHED_OR_WRONG_DIALOG.value)
                    details.append("dialog_found is False")
                elif target_pid and dlg_pid and (dlg_pid != target_pid):
                    rejections.append(RejectionReason.UNATTACHED_OR_WRONG_DIALOG.value)
                    details.append(f"Dialog belongs to unrelated PID {dlg_pid} instead of target {target_pid}")
                elif dlg_cls and dlg_cls != "#32770" and "find" not in dlg_cls.lower():
                    rejections.append(RejectionReason.UNATTACHED_OR_WRONG_DIALOG.value)
                    details.append(f"Dialog class '{dlg_cls}' is not a standard dialog window")

        # 4. Polarity contradictions
        hypothesis = transition.get("hypothesis", "")
        if "no state transition" in hypothesis.lower() and exp_delta.get("state_transition") is True:
            rejections.append(RejectionReason.POLARITY_CONTRADICTION.value)
            details.append("Hypothesis predicted NO transition but expected_delta demanded state_transition=True")

        return QualityGateResult(
            passed=len(rejections) == 0,
            rejection_reasons=rejections,
            rejection_details=details,
        )

    @classmethod
    def evaluate_training_candidate(cls, candidate: Dict[str, Any]) -> QualityGateResult:
        rejections: List[str] = []
        details: List[str] = []

        # Validate steps/transitions in candidate
        trans = candidate.get("transition", {})
        if not trans and "post_state" in candidate:
            # Construct pseudo-transition from trajectory step
            trans = {
                "transition_verified": candidate.get("verified", False),
                "expected_delta": candidate.get("expected_outcome", {}),
                "observed_delta": candidate.get("actual_outcome", {}),
                "raw_evidence_reference": candidate.get("evidence_reference", ""),
                "hypothesis": candidate.get("hypothesis", ""),
            }

        t_res = cls.evaluate_transition(trans)
        if not t_res.passed:
            rejections.extend(t_res.rejection_reasons)
            details.extend(t_res.rejection_details)

        # Hermes knowledge status check
        hermes_status = candidate.get("hermes_status")
        if hermes_status == "VERIFIED" and not t_res.passed:
            rejections.append(RejectionReason.INVALID_HERMES_PROVENANCE.value)
            details.append("Candidate marked as VERIFIED Hermes knowledge but underlying transition failed gate")

        return QualityGateResult(
            passed=len(rejections) == 0,
            rejection_reasons=list(set(rejections)),
            rejection_details=details,
        )
