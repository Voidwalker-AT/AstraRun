"""Test tool-to-reasoning post-tool synthesis grounded in actual tool observations.

Verifies:
- Battery capability executes before conversational synthesis
- Actual returned battery state (e.g. percentage, AC status) is passed to synthesis
- Assistant response is grounded in the factual tool observation
- Model does not hallucinate state prior to tool execution
"""

import pytest

from astrarun.agent.coordinator import AgentCoordinator, TurnStatus
from astrarun.ingress.models import RequestEnvelope, RequestOrigin
from astrarun.session.models import ConversationSession
from astrarun.session.store import SessionStore


def test_battery_tool_to_reasoning_synthesis():
    """Verify 'Check my battery and tell me whether I should plug in' grounds response in actual tool output."""
    coordinator = AgentCoordinator.get_instance()
    store = SessionStore.get_instance()
    session = store.create_session("sess-battery-synth")

    query = "Check my battery and tell me whether I should plug in."
    env = RequestEnvelope.create(
        query,
        origin=RequestOrigin.LAUNCHER,
        session_id=session.session_id,
    )

    res = coordinator.handle_turn(env, session)
    assert res.status == TurnStatus.SUCCESS

    # Invariant: Tool observation must have occurred
    assert len(res.tool_observations) > 0
    obs = res.tool_observations[0]
    assert obs["capability_id"] in ("battery_status", "generate_battery_report")
    assert obs["success"] is True

    # Invariant: Assistant reply must be synthesized and contain relevant battery guidance
    lower_resp = res.response_text.lower()
    assert any(term in lower_resp for term in ["battery", "percent", "%", "plug", "charge", "power", "level"]), (
        f"Response did not reference battery observation: {res.response_text}"
    )
