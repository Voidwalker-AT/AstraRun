"""Tests for Context Integrity and Adversarial Cross-Topic Resilience.

Verifies:
- Topic switching prevents topic bleed (no cross-contamination from prior topics)
- Semantic lineage resolves conversational references ('that example', 'the explanation', 'it')
  to the correct turn and artifact provenance rather than recency alone
- Deterministic MathClaimVerifier validates and corrects modular arithmetic claims
- Complete session isolation between separate conversations
"""

import pytest

from astrarun.agent.coordinator import AgentCoordinator, TurnStatus
from astrarun.cognition.math_verifier import MathClaimVerifier
from astrarun.ingress.models import RequestEnvelope, RequestOrigin
from astrarun.session.models import (
    ArtifactKind,
    ConversationSession,
    PinnedArtifact,
    TurnRecord,
)
from astrarun.session.store import SessionStore


@pytest.fixture
def coordinator():
    return AgentCoordinator()


@pytest.fixture
def session_store():
    store = SessionStore.get_instance()
    store.clear()
    return store


def test_adversarial_topic_switch_no_bleed(coordinator: AgentCoordinator, session_store: SessionStore):
    """
    Adversarial cross-topic test:
    1. Discuss operating systems deadlock.
    2. Switch deliberately to modular inverses.
    3. Ask for an example ('Give me an example.').
    4. Ask to shorten ('Make that shorter.').

    Invariants:
    - Turns 3 and 4 MUST reference modular inverses / mathematics.
    - Zero mentions of 'deadlock', 'mutex', or 'thread lock' in turns 3 and 4.
    """
    session = session_store.create_session("sess-adversarial")

    # Turn 1: Deadlock
    env1 = RequestEnvelope.create(
        "Explain deadlock in operating systems briefly.",
        origin=RequestOrigin.LAUNCHER,
        session_id=session.session_id,
    )
    res1 = coordinator.handle_turn(env1, session)
    assert res1.status == TurnStatus.SUCCESS
    assert any(w in res1.response_text.lower() for w in ["deadlock", "resource", "process", "thread", "lock"])

    # Turn 2: Deliberate topic switch to modular inverses
    env2 = RequestEnvelope.create(
        "Now let's switch topics completely. Explain what a modular inverse is in mathematics.",
        origin=RequestOrigin.LAUNCHER,
        session_id=session.session_id,
    )
    res2 = coordinator.handle_turn(env2, session)
    assert res2.status == TurnStatus.SUCCESS
    assert any(w in res2.response_text.lower() for w in ["modular", "inverse", "modulo", "mod", "math", "remainder"])

    # Turn 3: Give me an example
    env3 = RequestEnvelope.create(
        "Give me an example.",
        origin=RequestOrigin.LAUNCHER,
        session_id=session.session_id,
    )
    res3 = coordinator.handle_turn(env3, session)
    assert res3.status == TurnStatus.SUCCESS
    t3_lower = res3.response_text.lower()
    # Must NOT contain deadlock bleed
    assert "deadlock" not in t3_lower
    assert "mutex" not in t3_lower
    assert "thread lock" not in t3_lower
    # Must contain math / modular inverse content
    assert any(c.isdigit() for c in res3.response_text) or "mod" in t3_lower

    # Turn 4: Make that shorter
    env4 = RequestEnvelope.create(
        "Make that shorter.",
        origin=RequestOrigin.LAUNCHER,
        session_id=session.session_id,
    )
    res4 = coordinator.handle_turn(env4, session)
    assert res4.status == TurnStatus.SUCCESS
    t4_lower = res4.response_text.lower()
    # Invariant: Must NOT revert to deadlock
    assert "deadlock" not in t4_lower
    assert "mutex" not in t4_lower
    assert "thread lock" not in t4_lower


def test_lineage_artifact_resolution_by_topic():
    """Verify conversational lineage resolves artifacts matching the active topic."""
    session = ConversationSession(session_id="lineage-test")

    # Topic A: Deadlocks
    session.set_active_topic("deadlocks")
    art_a_exp = PinnedArtifact(
        artifact_id="a1",
        kind=ArtifactKind.EXPLANATION,
        display_name="Deadlock explanation",
        content="Deadlock occurs when processes hold resources and wait for others.",
        topic="deadlocks",
        created_turn_id="t1",
    )
    art_a_ex = PinnedArtifact(
        artifact_id="a2",
        kind=ArtifactKind.EXAMPLE,
        display_name="Deadlock example",
        content="Process 1 has Lock A, waits for Lock B. Process 2 has Lock B, waits for Lock A.",
        topic="deadlocks",
        created_turn_id="t2",
    )
    session.pin_artifact(art_a_exp.display_name, art_a_exp)
    session.pin_artifact(art_a_ex.display_name, art_a_ex)

    # Topic B: Modular Inverses
    session.set_active_topic("modular inverses")
    art_b_exp = PinnedArtifact(
        artifact_id="b1",
        kind=ArtifactKind.EXPLANATION,
        display_name="Modular inverse explanation",
        content="A modular inverse of a mod m is an integer x such that a*x = 1 (mod m).",
        topic="modular inverses",
        created_turn_id="t3",
    )
    art_b_ex = PinnedArtifact(
        artifact_id="b2",
        kind=ArtifactKind.EXAMPLE,
        display_name="Modular inverse example",
        content="3 * 7 = 21 = 1 (mod 20), so the inverse of 3 mod 20 is 7.",
        topic="modular inverses",
        created_turn_id="t4",
    )
    session.pin_artifact(art_b_exp.display_name, art_b_exp)
    session.pin_artifact(art_b_ex.display_name, art_b_ex)

    # Resolution while active topic is modular inverses
    resolved_ex = session.resolve_conversational_artifact(ArtifactKind.EXAMPLE)
    assert resolved_ex is not None
    assert resolved_ex.artifact_id == "b2"
    assert "3 * 7" in resolved_ex.content

    resolved_exp = session.resolve_conversational_artifact(ArtifactKind.EXPLANATION)
    assert resolved_exp is not None
    assert resolved_exp.artifact_id == "b1"
    assert "modular inverse" in resolved_exp.content.lower()

    # Switch back to deadlocks: lineage should now resolve Topic A artifacts
    session.set_active_topic("deadlocks")
    resolved_a_ex = session.resolve_conversational_artifact(ArtifactKind.EXAMPLE)
    assert resolved_a_ex is not None
    assert resolved_a_ex.artifact_id == "a2"
    assert "Lock A" in resolved_a_ex.content


def test_deterministic_math_claim_verifier():
    """Verify MathClaimVerifier detects false modular claims and calculates verified truth."""
    verifier = MathClaimVerifier()

    # Case 1: False claim 7 * 11 = 1 (mod 143)
    false_text = "For example, 7 * 11 = 1 (mod 143), so 11 is the inverse."
    claims = verifier.verify_text(false_text)
    assert len(claims) >= 1
    assert claims[0].is_valid is False
    assert claims[0].operands["true_inv"] == 41  # 7 * 41 = 287 = 2 * 143 + 1 = 1 (mod 143)

    repaired = verifier.repair_text(false_text)
    assert "41" in repaired

    # Case 2: True claim 3 * 7 = 1 (mod 20)
    true_text = "For example, 3 * 7 = 1 (mod 20), so 7 is the inverse."
    claims_true = verifier.verify_text(true_text)
    assert len(claims_true) >= 1
    assert claims_true[0].is_valid is True

    # Case 3: No claim
    neutral_text = "Operating systems use semaphores and mutexes."
    claims_none = verifier.verify_text(neutral_text)
    assert len(claims_none) == 0


def test_session_isolation_and_reset(session_store: SessionStore):
    """Verify complete isolation between separate sessions and clean reset."""
    s1 = session_store.create_session("sess-isolation-1")
    s1.set_active_topic("cryptography")
    s1.add_turn(TurnRecord(
        turn_id="t1",
        timestamp=1.0,
        user_text="User 1 query",
        assistant_text="User 1 answer",
        decision_mode="DIRECT_ANSWER",
        topic="cryptography",
    ))

    s2 = session_store.create_session("sess-isolation-2")
    assert s2.active_topic is None
    assert len(s2.turns) == 0
    assert len(s2.pinned_artifacts) == 0

    session_store.clear()
    assert session_store.get_session("sess-isolation-1") is None
    assert session_store.get_session("sess-isolation-2") is None
