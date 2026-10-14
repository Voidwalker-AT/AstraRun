"""Tests for SingleStepFastTrack optimization.

Verifies:
- Positive unambiguous commands produce standard TurnDecision
- Math evaluation works cleanly without external model
- Negative examples (pronouns, composite commands, conversational dependencies) return None (fall through)
"""

import pytest

from astrarun.agent.fast_track import SingleStepFastTrack
from astrarun.cognition.turn_models import TurnMode


def test_positive_arithmetic_fast_track():
    """Verify simple arithmetic expressions produce DIRECT_ANSWER TurnDecisions."""
    res = SingleStepFastTrack.match("2 + 2")
    assert res is not None
    assert res.mode == TurnMode.DIRECT_ANSWER
    assert "4" in res.assistant_reply
    assert res.model_role == "FAST_TRACK"

    res_div = SingleStepFastTrack.match("100 / 4")
    assert res_div is not None
    assert res_div.mode == TurnMode.DIRECT_ANSWER
    assert "25" in res_div.assistant_reply

    res_mult = SingleStepFastTrack.match("15 * 3")
    assert res_mult is not None
    assert "45" in res_mult.assistant_reply


def test_positive_open_calculator_fast_track():
    """Verify 'open calculator' produces a governed open_application PlanStep."""
    res = SingleStepFastTrack.match("open calculator")
    assert res is not None
    assert res.mode == TurnMode.TOOL_PLAN
    assert len(res.plan_steps) == 1
    step = res.plan_steps[0]
    assert step.capability_id == "open_application"
    assert step.arguments.get("app") == "calculator"
    assert res.confidence == 1.0


def test_positive_battery_status_fast_track():
    """Verify 'battery percentage' produces a battery_status check."""
    for phrase in ["battery percentage", "battery status", "check battery", "battery level"]:
        res = SingleStepFastTrack.match(phrase)
        assert res is not None, f"Failed on '{phrase}'"
        assert len(res.plan_steps) == 1
        assert res.plan_steps[0].capability_id == "battery_status"


def test_positive_window_snapping_fast_track():
    """Verify window snapping queries produce snap_window_left/right steps."""
    res_l = SingleStepFastTrack.match("snap current window left")
    assert res_l is not None
    assert res_l.plan_steps[0].capability_id == "snap_window_left"

    res_r = SingleStepFastTrack.match("snap current window right")
    assert res_r is not None
    assert res_r.plan_steps[0].capability_id == "snap_window_right"


def test_negative_pronouns_and_conversational_references_fall_through():
    """
    CRITICAL INVARIANT: Pronouns and conversational dependencies MUST return None
    so they fall through to TurnReasoner and session resolution.
    """
    disallowed_phrases = [
        "open it",
        "close that",
        "make it shorter",
        "put that example in a file",
        "why did that happen",
        "explain this",
        "summarize the previous result",
        "what were we discussing",
        "open calculator and explain floating point",
        "delete that",
    ]

    for phrase in disallowed_phrases:
        res = SingleStepFastTrack.match(phrase)
        assert res is None, f"Phrase '{phrase}' must return None to fall through to TurnReasoner, got {res}"
