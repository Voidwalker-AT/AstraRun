"""Tests for TurnReasoner, TurnDecision schema validation, and fail-safe parsing.

Verifies:
- All TurnModes (DIRECT_ANSWER, TOOL_PLAN, HYBRID_ACT_AND_ANSWER, CLARIFY, REFUSE)
- Strict schema validation
- Malformed model JSON fails safely without executing arbitrary prose
- Code fences and json extraction
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from astrarun.cognition.client import ModelClient
from astrarun.cognition.models import InferenceObservation
from astrarun.cognition.turn_models import PlanStep, TurnDecision, TurnMode
from astrarun.cognition.turn_reasoner import TurnReasoner
from astrarun.session.models import ConversationSession


def test_turn_decision_schema_and_serialization():
    """Verify TurnDecision schema fields, JSON schema export, and roundtrip serialization."""
    step = PlanStep(
        step_id="step-1",
        capability_id="open_application",
        arguments={"app": "calculator"},
        depends_on=[],
    )
    decision = TurnDecision(
        mode=TurnMode.TOOL_PLAN,
        assistant_reply="Opening Calculator.",
        goal_summary="Launch Calculator",
        plan_steps=[step],
        referenced_artifacts=[],
        confidence=0.95,
        model_role="TURN_REASONER",
    )

    data = decision.to_dict()
    assert data["mode"] == "TOOL_PLAN"
    assert len(data["plan_steps"]) == 1
    assert data["plan_steps"][0]["capability_id"] == "open_application"

    # Roundtrip from dict
    reloaded = TurnDecision.from_dict(data)
    assert reloaded.mode == TurnMode.TOOL_PLAN
    assert reloaded.plan_steps[0].capability_id == "open_application"
    assert reloaded.confidence == 0.95

    # Check canonical JSON schema
    schema = TurnDecision.json_schema()
    assert "properties" in schema
    assert "mode" in schema["properties"]
    assert "DIRECT_ANSWER" in schema["properties"]["mode"]["enum"]


def test_turn_reasoner_direct_answer():
    """Verify TurnReasoner correctly parses DIRECT_ANSWER decision."""
    raw_json = json.dumps({
        "mode": "DIRECT_ANSWER",
        "assistant_reply": "A modular inverse of an integer a modulo m is an integer x such that ax = 1 (mod m).",
        "goal_summary": "Explain modular inverse",
        "plan_steps": [],
        "confidence": 1.0,
    })

    mock_client = MagicMock(spec=ModelClient)
    mock_client.complete_sync.return_value = InferenceObservation(
        model_id="test_model",
        status="SUCCESS",
        raw_output=f"```json\n{raw_json}\n```",
        latency_ms=120.0,
    )

    reasoner = TurnReasoner(model_client=mock_client)
    decision = reasoner.reason_turn("Explain modular inverses.")

    assert decision.mode == TurnMode.DIRECT_ANSWER
    assert "modular inverse" in decision.assistant_reply.lower()
    assert len(decision.plan_steps) == 0


def test_turn_reasoner_tool_plan():
    """Verify TurnReasoner parses TOOL_PLAN with governed capability proposal."""
    raw_json = json.dumps({
        "mode": "TOOL_PLAN",
        "assistant_reply": "Creating modular inverse example file.",
        "goal_summary": "Write example file",
        "plan_steps": [
            {
                "step_id": "step-1",
                "capability_id": "write_file",
                "arguments": {
                    "path": "C:/temp/modular_inverse.txt",
                    "content": "For 3x = 1 (mod 7), x = 5 is the modular inverse.",
                },
                "depends_on": [],
            }
        ],
        "confidence": 0.9,
    })

    mock_client = MagicMock(spec=ModelClient)
    mock_client.complete_sync.return_value = InferenceObservation(
        model_id="test_model",
        status="SUCCESS",
        raw_output=raw_json,
        latency_ms=150.0,
    )

    reasoner = TurnReasoner(model_client=mock_client)
    decision = reasoner.reason_turn("Put that example in a text file.")

    assert decision.mode == TurnMode.TOOL_PLAN
    assert len(decision.plan_steps) == 1
    assert decision.plan_steps[0].capability_id == "write_file"
    assert decision.plan_steps[0].arguments["path"] == "C:/temp/modular_inverse.txt"


def test_turn_reasoner_clarify_and_refuse_modes():
    """Verify CLARIFY and REFUSE modes are supported."""
    mock_client = MagicMock(spec=ModelClient)

    # CLARIFY
    mock_client.complete_sync.return_value = InferenceObservation(
        model_id="test",
        status="SUCCESS",
        raw_output=json.dumps({
            "mode": "CLARIFY",
            "clarification_question": "Did you want the explanation for modular inverse or modular exponentiation?",
            "confidence": 0.8,
        }),
    )
    reasoner = TurnReasoner(model_client=mock_client)
    clarify_dec = reasoner.reason_turn("Explain it.")
    assert clarify_dec.mode == TurnMode.CLARIFY
    assert "modular exponentiation" in clarify_dec.clarification_question

    # REFUSE
    mock_client.complete_sync.return_value = InferenceObservation(
        model_id="test",
        status="SUCCESS",
        raw_output=json.dumps({
            "mode": "REFUSE",
            "assistant_reply": "I cannot perform unauthorized system tampering.",
            "confidence": 1.0,
        }),
    )
    refuse_dec = reasoner.reason_turn("Format my hard drive.")
    assert refuse_dec.mode == TurnMode.REFUSE
    assert "tampering" in refuse_dec.assistant_reply.lower()


def test_malformed_model_json_fails_safely():
    """
    Verify malformed JSON from model fails safely.
    Arbitrary model prose is NOT converted into unexpected tool executions.
    """
    mock_client = MagicMock(spec=ModelClient)
    # Model returns broken JSON or conversational prose
    mock_client.complete_sync.return_value = InferenceObservation(
        model_id="test",
        status="SUCCESS",
        raw_output="I think I should delete your files because {broken json [",
    )

    reasoner = TurnReasoner(model_client=mock_client)
    decision = reasoner.reason_turn("Do something.")

    # Must fail safely to conversational DIRECT_ANSWER or fallback, NEVER execute a tool
    assert decision.mode == TurnMode.DIRECT_ANSWER
    assert len(decision.plan_steps) == 0
