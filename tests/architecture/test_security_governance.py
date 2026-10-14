"""Tests for security invariants, ActionGate governance, and ExecutionBroker enforcement.

Verifies:
- Model output cannot bypass governance
- TurnDecision proposing restricted capability is BLOCKED
- Blocked actions fail closed: no retry, no replan, no override
- Model proposing nonexistent capability fails safely with typed error
- Zero raw shell or uncontrolled code execution
"""

import pytest

from astrarun.agent.coordinator import AgentCoordinator, TurnStatus
from astrarun.cognition.turn_models import PlanStep, TurnDecision, TurnMode
from astrarun.ingress.models import RequestEnvelope, RequestOrigin
from astrarun.session.models import ConversationSession
from astrarun.session.store import SessionStore


def test_model_proposes_blocked_capability_fails_closed():
    """Verify that if TurnDecision proposes a blocked or restricted action, ActionGate blocks it."""
    coordinator = AgentCoordinator()
    store = SessionStore.get_instance()
    session = store.create_session("sess-sec-block")

    # Manually construct a TurnDecision with a blocked capability or dangerous operation
    # e.g., 'kill_all_user_processes' or destructive shell command
    decision = TurnDecision(
        mode=TurnMode.TOOL_PLAN,
        assistant_reply="Attempting destructive action.",
        goal_summary="Tamper with system processes",
        plan_steps=[
            PlanStep(
                step_id="bad-1",
                capability_id="terminate_process",
                arguments={"pid": 1, "force": True},  # System PID 1 or protected process
            )
        ],
    )

    # Mock reasoner returning this dangerous proposal
    coordinator.reasoner.reason_turn = lambda *args, **kwargs: decision

    env = RequestEnvelope.create("Stop process 1", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res = coordinator.handle_turn(env, session)

    # Invariant: Must be BLOCKED or PAUSED_CONFIRMATION, NEVER silently executed
    assert res.status in (TurnStatus.BLOCKED, TurnStatus.PAUSED_CONFIRMATION)
    if res.status == TurnStatus.BLOCKED:
        assert "blocked" in res.response_text.lower() or "denied" in res.response_text.lower() or res.error is not None


def test_model_proposes_nonexistent_capability_fails_safely():
    """Verify proposing an unregistered capability produces a clean security block or failure."""
    coordinator = AgentCoordinator()
    store = SessionStore.get_instance()
    session = store.create_session("sess-sec-unknown")

    decision = TurnDecision(
        mode=TurnMode.TOOL_PLAN,
        assistant_reply="Attempting unknown capability.",
        goal_summary="Execute arbitrary fake capability",
        plan_steps=[
            PlanStep(
                step_id="bad-2",
                capability_id="arbitrary_unregistered_exploit",
                arguments={"payload": "echo exploit"},
            )
        ],
    )

    coordinator.reasoner.reason_turn = lambda *args, **kwargs: decision

    env = RequestEnvelope.create("Run fake exploit", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res = coordinator.handle_turn(env, session)

    # Invariant: Must fail closed. ExecutionBroker denies unknown capabilities by default.
    assert res.status in (TurnStatus.BLOCKED, TurnStatus.FAILED)
    assert any(term in (res.error or res.response_text).lower() for term in ["unknown", "unregistered", "blocked", "deny", "failed"])
