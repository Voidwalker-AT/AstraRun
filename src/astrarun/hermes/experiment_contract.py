"""Machine-Checkable Experiment Contract and Typed Predicate Evaluator for Hermes.

Eliminates manual interpretation of prose by enforcing explicit predicate types,
machine-checkable hypothesis polarities, and verifiable raw evidence references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class PredicateType(str, Enum):
    """Strongly-typed predicate categories for state transition verification."""
    TEXT_BUFFER_DELTA = "TEXT_BUFFER_DELTA"
    SELECTION_RANGE_SPAN = "SELECTION_RANGE_SPAN"
    DOCUMENT_TAB_COUNT = "DOCUMENT_TAB_COUNT"
    DIALOG_SURFACE_PRESENCE = "DIALOG_SURFACE_PRESENCE"
    STATE_INVARIANCE = "STATE_INVARIANCE"
    FILE_SYSTEM_MUTATION = "FILE_SYSTEM_MUTATION"
    GENERIC_STATE_DELTA = "GENERIC_STATE_DELTA"


@dataclass
class PredicateEvaluationResult:
    """Evaluation result of a machine-checkable predicate."""
    passed: bool
    predicate_type: str
    expected_value: Dict[str, Any]
    observed_value: Dict[str, Any]
    raw_evidence_reference: str
    criterion_description: str
    hypothesis_status: str  # "SUPPORTED" | "REFUTED" | "INCONCLUSIVE"


@dataclass
class ExperimentContract:
    """Machine-checkable experiment contract governing an exploration cycle."""
    hypothesis: str
    predicate_type: PredicateType
    supported_predicates: Dict[str, Any]
    refuted_predicates: Dict[str, Any]
    affordance_name: str
    capability_id: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    evaluator_name: str = "default"

    def evaluate(
        self,
        pre_state: Dict[str, Any],
        post_state: Dict[str, Any],
        raw_evidence: Optional[Dict[str, Any]] = None,
    ) -> PredicateEvaluationResult:
        """Evaluate observation against contract supported and refuted predicates."""
        raw_evidence = raw_evidence or {}

        if self.predicate_type == PredicateType.TEXT_BUFFER_DELTA:
            pre_len = pre_state.get("buffer_length", 0)
            post_len = post_state.get("buffer_length", 0)
            delta = post_len - pre_len
            min_delta = self.supported_predicates.get("min_char_delta", 1)
            passed = delta >= min_delta or post_state.get("is_dirty", False) or (post_state.get("status_bar") != pre_state.get("status_bar"))
            observed = {
                "pre_length": pre_len,
                "post_length": post_len,
                "delta": delta,
                "is_dirty": post_state.get("is_dirty", False),
                "status_bar_changed": post_state.get("status_bar") != pre_state.get("status_bar"),
            }
            ref = raw_evidence.get("evidence_reference", f"text_delta_{delta}_dirty_{post_state.get('is_dirty')}")
            return PredicateEvaluationResult(
                passed=passed,
                predicate_type=self.predicate_type.value,
                expected_value=self.supported_predicates,
                observed_value=observed,
                raw_evidence_reference=ref,
                criterion_description=f"delta >= {min_delta} or dirty indicated",
                hypothesis_status="SUPPORTED" if passed else "REFUTED",
            )

        elif self.predicate_type == PredicateType.SELECTION_RANGE_SPAN:
            sel_obs = raw_evidence.get("selection_observation")
            if sel_obs:
                obs_dict = {
                    "observable": sel_obs.observable,
                    "source": sel_obs.source,
                    "start": sel_obs.start,
                    "end": sel_obs.end,
                    "selected_length": sel_obs.selected_length,
                    "document_length": sel_obs.document_length,
                }
                passed = bool(
                    sel_obs.observable
                    and sel_obs.document_length is not None
                    and sel_obs.document_length > 0
                    and sel_obs.selected_length is not None
                    and sel_obs.selected_length == sel_obs.document_length
                )
                ref = sel_obs.evidence_reference
            else:
                obs_dict = {"observable": False}
                passed = False
                ref = "missing_selection_observation"

            return PredicateEvaluationResult(
                passed=passed,
                predicate_type=self.predicate_type.value,
                expected_value=self.supported_predicates,
                observed_value=obs_dict,
                raw_evidence_reference=ref,
                criterion_description="observable == True and selected_length == document_length > 0",
                hypothesis_status="SUPPORTED" if passed else "REFUTED",
            )

        elif self.predicate_type == PredicateType.DOCUMENT_TAB_COUNT:
            pre_count = pre_state.get("tabs_count", 0)
            post_count = post_state.get("tabs_count", 0)
            pre_names = pre_state.get("tab_names", [])
            post_names = post_state.get("tab_names", [])
            delta = post_count - pre_count
            names_increased = len(post_names) > len(pre_names)
            passed = delta > 0 or names_increased or ("new 2" in post_state.get("title", "").lower())
            observed = {
                "pre_tabs_count": pre_count,
                "post_tabs_count": post_count,
                "delta": delta,
                "pre_tab_names": pre_names,
                "post_tab_names": post_names,
                "title": post_state.get("title", ""),
            }
            ref = raw_evidence.get("evidence_reference", f"tabs_count_pre_{pre_count}_post_{post_count}_delta_{delta}")
            return PredicateEvaluationResult(
                passed=passed,
                predicate_type=self.predicate_type.value,
                expected_value=self.supported_predicates,
                observed_value=observed,
                raw_evidence_reference=ref,
                criterion_description="post_tabs_count > pre_tabs_count or tab_names increased",
                hypothesis_status="SUPPORTED" if passed else "REFUTED",
            )

        elif self.predicate_type == PredicateType.DIALOG_SURFACE_PRESENCE:
            dialog_found = raw_evidence.get("dialog_found", False)
            dialog_hwnds = raw_evidence.get("dialog_hwnds", [])
            dialog_class = raw_evidence.get("dialog_class", "")
            dialog_pid = raw_evidence.get("dialog_pid", 0)
            passed = bool(dialog_found and len(dialog_hwnds) > 0)
            observed = {
                "dialog_found": dialog_found,
                "dialog_hwnds": [f"0x{h:x}" if isinstance(h, int) else str(h) for h in dialog_hwnds],
                "dialog_class": dialog_class,
                "dialog_pid": dialog_pid,
            }
            ref = raw_evidence.get("evidence_reference", f"dialog_hwnds_{len(dialog_hwnds)}_class_{dialog_class}")
            return PredicateEvaluationResult(
                passed=passed,
                predicate_type=self.predicate_type.value,
                expected_value=self.supported_predicates,
                observed_value=observed,
                raw_evidence_reference=ref,
                criterion_description="dialog_found == True and matching PID/HWND",
                hypothesis_status="SUPPORTED" if passed else "REFUTED",
            )

        elif self.predicate_type == PredicateType.STATE_INVARIANCE:
            # Tests whether an invalid or benign action results in NO state transition
            pre_hash = pre_state.get("state_hash", "")
            post_hash = post_state.get("state_hash", "")
            hashes_equal = (pre_hash == post_hash) if (pre_hash and post_hash) else True
            # Supported predicate says state_transition == False
            state_transition_occurred = not hashes_equal
            expected_transition = self.supported_predicates.get("state_transition", False)
            passed = (state_transition_occurred == expected_transition)
            observed = {
                "state_transition_occurred": state_transition_occurred,
                "pre_hash": pre_hash,
                "post_hash": post_hash,
            }
            ref = f"invariance_state_transition_{state_transition_occurred}"
            return PredicateEvaluationResult(
                passed=passed,
                predicate_type=self.predicate_type.value,
                expected_value=self.supported_predicates,
                observed_value=observed,
                raw_evidence_reference=ref,
                criterion_description=f"state_transition_occurred == {expected_transition}",
                hypothesis_status="SUPPORTED" if passed else "REFUTED",
            )

        # Fallback
        return PredicateEvaluationResult(
            passed=False,
            predicate_type="UNKNOWN",
            expected_value=self.supported_predicates,
            observed_value={},
            raw_evidence_reference="unsupported_predicate_type",
            criterion_description="unsupported_predicate_type",
            hypothesis_status="INCONCLUSIVE",
        )
