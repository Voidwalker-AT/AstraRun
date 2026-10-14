"""Adversarial Mutation Suite for Hermes Training-Candidate Quality Gate (F0-25B.1 Section 9).

Validates that the TrainingQualityGate kills all 10 semantic verification mutants.
"""

import pytest
from astrarun.hermes.training_gate import (
    TrainingQualityGate,
    RejectionReason,
)


def test_mutant_1_ctrl_a_dispatched_but_selection_absent():
    # Ctrl+A dispatched, but selection range is 0
    transition = {
        "transition_verified": True,
        "expected_delta": {"selection_active": True},
        "observed_delta": {"selected_length": 0, "document_length": 50, "observable": True},
        "raw_evidence_reference": "scintilla_sel_0",
    }
    res = TrainingQualityGate.evaluate_transition(transition)
    assert not res.passed
    assert RejectionReason.TAUTOLOGICAL_SELECTION.value in res.rejection_reasons


def test_mutant_2_ctrl_n_dispatched_but_tab_count_unchanged():
    # Ctrl+N dispatched, but tab count is identical
    transition = {
        "transition_verified": True,
        "expected_delta": {"tabs_count_increased": True},
        "observed_delta": {"pre_tabs_count": 1, "post_tabs_count": 1, "delta": 0},
        "raw_evidence_reference": "tabs_delta_0",
    }
    res = TrainingQualityGate.evaluate_transition(transition)
    assert not res.passed
    assert RejectionReason.TAB_COUNT_UNCHANGED.value in res.rejection_reasons


def test_mutant_3_ctrl_f_dispatched_but_no_dialog_appears():
    # Ctrl+F dispatched, but dialog_found is False
    transition = {
        "transition_verified": True,
        "expected_delta": {"find_dialog_opened": True},
        "observed_delta": {"dialog_found": False, "dialog_hwnds": []},
        "raw_evidence_reference": "none",
    }
    res = TrainingQualityGate.evaluate_transition(transition)
    assert not res.passed
    assert RejectionReason.UNATTACHED_OR_WRONG_DIALOG.value in res.rejection_reasons or RejectionReason.MISSING_EVIDENCE_REFERENCE.value in res.rejection_reasons


def test_mutant_4_unrelated_dialog_appears():
    # Dialog found, but belongs to wrong PID or wrong window class
    transition = {
        "transition_verified": True,
        "expected_delta": {"find_dialog_opened": True},
        "observed_delta": {"dialog_found": True, "dialog_hwnds": [0x999], "dialog_pid": 99999, "dialog_class": "UnrelatedAppWindow"},
        "raw_evidence_reference": "unrelated_window",
    }
    res = TrainingQualityGate.evaluate_transition(transition, target_pid=1234)
    assert not res.passed
    assert RejectionReason.UNATTACHED_OR_WRONG_DIALOG.value in res.rejection_reasons


def test_mutant_5_unrelated_tab_appears():
    # Negative delta in tab count
    transition = {
        "transition_verified": True,
        "expected_delta": {"tabs_count_increased": True},
        "observed_delta": {"pre_tabs_count": 2, "post_tabs_count": 1, "delta": -1},
        "raw_evidence_reference": "tab_closed",
    }
    res = TrainingQualityGate.evaluate_transition(transition)
    assert not res.passed
    assert RejectionReason.TAB_COUNT_UNCHANGED.value in res.rejection_reasons


def test_mutant_6_state_hash_changes_for_irrelevant_reason():
    # Tab creation claimed because hash changed, but tab count is not present
    transition = {
        "transition_verified": True,
        "expected_delta": {"tabs_count_increased": True},
        "observed_delta": {"hash_changed": True},  # Missing actual tab count data
        "raw_evidence_reference": "irrelevant_hash",
    }
    res = TrainingQualityGate.evaluate_transition(transition)
    assert not res.passed
    assert RejectionReason.PREDICATE_TYPE_MISMATCH.value in res.rejection_reasons


def test_mutant_7_hypothesis_says_false_while_predicate_expects_true():
    # Polarity contradiction: hypothesis predicts no transition, but expected delta demands true
    transition = {
        "hypothesis": "Clicking an invalid target produces no state transition",
        "transition_verified": True,
        "expected_delta": {"state_transition": True},  # Contradicts hypothesis
        "observed_delta": {"state_transition": False},
        "raw_evidence_reference": "ref_invariance",
    }
    res = TrainingQualityGate.evaluate_transition(transition)
    assert not res.passed
    assert RejectionReason.POLARITY_CONTRADICTION.value in res.rejection_reasons


def test_mutant_8_hermes_transition_stores_wrong_observation_field():
    # Selection expected, but recorded observed_delta has length_changed (the F0-25B bug)
    transition = {
        "transition_verified": True,
        "expected_delta": {"selection_active": True},
        "observed_delta": {"length_changed": False},  # Wrong observation field!
        "raw_evidence_reference": "scintilla_ref",
    }
    res = TrainingQualityGate.evaluate_transition(transition)
    assert not res.passed
    assert RejectionReason.PREDICATE_TYPE_MISMATCH.value in res.rejection_reasons


def test_mutant_9_transition_verified_manually_forced_true():
    # transition_verified is True, but evaluation['passed'] is False
    transition = {
        "transition_verified": True,
        "evaluation": {"passed": False, "criterion": "verification failed"},
        "expected_delta": {"length_increased": True},
        "observed_delta": {"delta": 0},
        "raw_evidence_reference": "ref_forced",
    }
    res = TrainingQualityGate.evaluate_transition(transition)
    assert not res.passed
    assert RejectionReason.FORCED_VERIFICATION.value in res.rejection_reasons


def test_mutant_10_training_candidate_sourced_from_invalid_hermes_knowledge():
    # Candidate marked as VERIFIED Hermes knowledge, but transition has missing evidence
    candidate = {
        "hermes_status": "VERIFIED",
        "transition": {
            "transition_verified": True,
            "expected_delta": {"selection_active": True},
            "observed_delta": {"length_changed": False},
            "raw_evidence_reference": "",
        }
    }
    res = TrainingQualityGate.evaluate_training_candidate(candidate)
    assert not res.passed
    assert RejectionReason.INVALID_HERMES_PROVENANCE.value in res.rejection_reasons
