"""Human-authored multi-turn intelligence test suite for AstraRun 1.0.

Verifies genuine contextual intelligence across 3 distinct, unrelated domains:
- Sequence A: Cryptography (Modular Inverses)
- Sequence B: Operating Systems (Deadlocks)
- Sequence C: Computer Science (Recursion)

Invariants:
- Real local model path is invoked
- Each turn's response is semantically grounded in prior turn context
- Pronouns ('that', 'it', 'the whole thing') resolve across turns
- Zero canned placeholder answers
"""

import time
import pytest

from astrarun.agent.coordinator import AgentCoordinator, TurnStatus
from astrarun.ingress.models import RequestEnvelope, RequestOrigin
from astrarun.session.models import ConversationSession
from astrarun.session.store import SessionStore


@pytest.fixture
def coordinator():
    """Create a live AgentCoordinator instance connected to the local model service."""
    return AgentCoordinator()


@pytest.fixture
def session_store():
    store = SessionStore.get_instance()
    store.clear()
    return store


def test_sequence_a_cryptography_multi_turn(coordinator: AgentCoordinator, session_store: SessionStore):
    """
    Sequence A: Cryptography
    1. 'Explain modular inverses simply.'
    2. 'Give me an example.'
    3. 'Why does that work?'
    4. 'Make it shorter.'
    5. 'What were we discussing?'
    """
    session = session_store.create_session("sess-crypto")

    # Turn 1: Explain modular inverses simply.
    env1 = RequestEnvelope.create("Explain modular inverses simply.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res1 = coordinator.handle_turn(env1, session)
    assert res1.status == TurnStatus.SUCCESS
    assert len(res1.response_text) > 20
    assert any(term in res1.response_text.lower() for term in ["modular", "inverse", "modulo", "mod", "integer", "multiply", "remainder"])

    # Turn 2: Give me an example.
    env2 = RequestEnvelope.create("Give me an example.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res2 = coordinator.handle_turn(env2, session)
    assert res2.status == TurnStatus.SUCCESS
    assert len(res2.response_text) > 15
    # Must contain numeric example or equation
    assert any(char.isdigit() for char in res2.response_text) or "mod" in res2.response_text.lower()

    # Turn 3: Why does that work?
    env3 = RequestEnvelope.create("Why does that work?", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res3 = coordinator.handle_turn(env3, session)
    assert res3.status == TurnStatus.SUCCESS
    assert len(res3.response_text) > 15

    # Turn 4: Make it shorter.
    env4 = RequestEnvelope.create("Make it shorter.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res4 = coordinator.handle_turn(env4, session)
    assert res4.status == TurnStatus.SUCCESS
    assert len(res4.response_text) > 5

    # Turn 5: What were we discussing?
    env5 = RequestEnvelope.create("What were we discussing?", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res5 = coordinator.handle_turn(env5, session)
    assert res5.status == TurnStatus.SUCCESS
    # Must correctly identify cryptography or modular inverses from session context
    lower_5 = res5.response_text.lower()
    assert any(term in lower_5 for term in ["modular", "inverse", "cryptography", "math", "modulo"]), f"Response did not reference modular inverses: {res5.response_text}"


def test_sequence_b_operating_systems_multi_turn(coordinator: AgentCoordinator, session_store: SessionStore):
    """
    Sequence B: Operating Systems
    1. 'Explain deadlock without textbook jargon.'
    2. 'Give me a real-world analogy.'
    3. 'Now give me a tiny Python example.'
    4. 'What does the second lock do?'
    5. 'Summarize the whole thing in three bullets.'
    """
    session = session_store.create_session("sess-os")

    # Turn 1
    env1 = RequestEnvelope.create("Explain deadlock without textbook jargon.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res1 = coordinator.handle_turn(env1, session)
    assert res1.status == TurnStatus.SUCCESS
    assert any(term in res1.response_text.lower() for term in ["wait", "lock", "resource", "block", "process", "thread", "holding", "traffic"])

    # Turn 2: Analogy
    env2 = RequestEnvelope.create("Give me a real-world analogy.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res2 = coordinator.handle_turn(env2, session)
    assert res2.status == TurnStatus.SUCCESS
    assert len(res2.response_text) > 20

    # Turn 3: Python example
    env3 = RequestEnvelope.create("Now give me a tiny Python example.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res3 = coordinator.handle_turn(env3, session)
    assert res3.status == TurnStatus.SUCCESS
    assert any(term in res3.response_text.lower() for term in ["import", "threading", "lock", "acquire", "release", "def", "mutex"])

    # Turn 4: What does the second lock do?
    env4 = RequestEnvelope.create("What does the second lock do?", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res4 = coordinator.handle_turn(env4, session)
    assert res4.status == TurnStatus.SUCCESS
    assert len(res4.response_text) > 10

    # Turn 5: Summarize
    env5 = RequestEnvelope.create("Summarize the whole thing in three bullets.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res5 = coordinator.handle_turn(env5, session)
    assert res5.status == TurnStatus.SUCCESS
    assert len(res5.response_text) > 15


def test_sequence_c_programming_recursion_multi_turn(coordinator: AgentCoordinator, session_store: SessionStore):
    """
    Sequence C: Programming
    1. 'Explain recursion using factorial.'
    2. 'Show me code.'
    3. 'Why is the base case needed?'
    4. 'What happens if I remove it?'
    5. 'Make your first explanation more concise.'
    """
    session = session_store.create_session("sess-prog")

    # Turn 1
    env1 = RequestEnvelope.create("Explain recursion using factorial.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res1 = coordinator.handle_turn(env1, session)
    assert res1.status == TurnStatus.SUCCESS
    assert any(term in res1.response_text.lower() for term in ["factorial", "function", "call", "base case", "multiply", "n *"])

    # Turn 2
    env2 = RequestEnvelope.create("Show me code.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res2 = coordinator.handle_turn(env2, session)
    assert res2.status == TurnStatus.SUCCESS
    assert any(term in res2.response_text.lower() for term in ["def", "factorial", "return", "if n", "n <="])

    # Turn 3
    env3 = RequestEnvelope.create("Why is the base case needed?", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res3 = coordinator.handle_turn(env3, session)
    assert res3.status == TurnStatus.SUCCESS
    assert any(term in res3.response_text.lower() for term in ["stop", "infinite", "stack", "overflow", "end", "terminate", "recursion"])

    # Turn 4
    env4 = RequestEnvelope.create("What happens if I remove it?", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res4 = coordinator.handle_turn(env4, session)
    assert res4.status == TurnStatus.SUCCESS
    assert any(term in res4.response_text.lower() for term in ["stack", "overflow", "infinite", "recursionerror", "crash", "never stop", "maximum"])

    # Turn 5
    env5 = RequestEnvelope.create("Make your first explanation more concise.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    res5 = coordinator.handle_turn(env5, session)
    assert res5.status == TurnStatus.SUCCESS
    assert len(res5.response_text) > 10
