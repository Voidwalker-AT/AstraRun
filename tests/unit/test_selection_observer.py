"""Unit tests for Generic Selection Observation and Semantic SELECT_ALL Verification."""

import pytest
from astrarun.computer_use.ui.editable_surface import (
    SelectionObservation,
    verify_select_all_predicate,
    send_message_timeout_w,
    observe_surface_selection,
)


def test_selection_observation_defaults():
    obs = SelectionObservation()
    assert not obs.observable
    assert obs.source == "NONE"
    assert obs.anchor is None
    assert obs.caret is None
    assert obs.start is None
    assert obs.end is None
    assert obs.selected_length is None
    assert obs.document_length is None
    assert obs.evidence_reference == ""


def test_verify_select_all_predicate_truth_table():
    # 1. Unobservable selection
    assert not verify_select_all_predicate(
        SelectionObservation(observable=False, selected_length=10, document_length=10)
    )

    # 2. None lengths
    assert not verify_select_all_predicate(
        SelectionObservation(observable=True, selected_length=None, document_length=10)
    )
    assert not verify_select_all_predicate(
        SelectionObservation(observable=True, selected_length=10, document_length=None)
    )

    # 3. Empty document (length 0 cannot be meaningfully selected-all)
    assert not verify_select_all_predicate(
        SelectionObservation(observable=True, selected_length=0, document_length=0)
    )

    # 4. Zero selection in non-empty document (caret only)
    assert not verify_select_all_predicate(
        SelectionObservation(observable=True, selected_length=0, document_length=50)
    )

    # 5. Partial selection
    assert not verify_select_all_predicate(
        SelectionObservation(observable=True, selected_length=25, document_length=50)
    )

    # 6. Negative control / selection beyond doc
    assert not verify_select_all_predicate(
        SelectionObservation(observable=True, selected_length=55, document_length=50)
    )

    # 7. Exact full selection match (SELECT_ALL satisfied)
    assert verify_select_all_predicate(
        SelectionObservation(observable=True, selected_length=50, document_length=50)
    )
    assert verify_select_all_predicate(
        SelectionObservation(
            observable=True,
            source="SCINTILLA_ADAPTER",
            start=0,
            end=128,
            selected_length=128,
            document_length=128,
            evidence_reference="scintilla_0x123_start_0_end_128_doclen_128",
        )
    )


def test_send_message_timeout_invalid_handle():
    # Invalid handle 0 must fail closed immediately without hanging
    ok, val = send_message_timeout_w(0, 0x0000, 0, 0, timeout_ms=100)
    assert not ok
    assert val == 0


def test_observe_surface_selection_invalid_hwnd():
    obs = observe_surface_selection(target_hwnd=0)
    assert not obs.observable
    assert obs.source == "NONE"
    assert "invalid_window_handle" in obs.evidence_reference
