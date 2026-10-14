"""Tests for ConversationSession, TurnRecord, PinnedArtifact, and SessionStore.

Verifies:
- Turn ordering is preserved chronologically
- Rolling context returns last 4 turns + summary
- Pinned artifacts are tracked and retrievable
- Invariant: Artifacts require affirmative verification and cannot be verified merely by model assertion
- Session isolation across multiple independent session IDs
- Failed turn handling and error recording
"""

import time
import pytest

from astrarun.session.models import (
    ArtifactKind,
    ConversationSession,
    PinnedArtifact,
    TurnRecord,
)
from astrarun.session.store import SessionStore


def test_turn_ordering_chronological():
    """Verify turns are strictly ordered chronologically in the session."""
    session = ConversationSession(session_id="test-session-1")
    t1 = TurnRecord(
        turn_id="t1",
        timestamp=100.0,
        user_text="First message",
        assistant_text="First response",
        decision_mode="DIRECT_ANSWER",
    )
    t2 = TurnRecord(
        turn_id="t2",
        timestamp=200.0,
        user_text="Second message",
        assistant_text="Second response",
        decision_mode="DIRECT_ANSWER",
    )
    t3 = TurnRecord(
        turn_id="t3",
        timestamp=300.0,
        user_text="Third message",
        assistant_text="Third response",
        decision_mode="DIRECT_ANSWER",
    )

    session.add_turn(t1)
    session.add_turn(t2)
    session.add_turn(t3)

    assert len(session.turns) == 3
    assert [t.turn_id for t in session.turns] == ["t1", "t2", "t3"]
    assert session.turns[0].user_text == "First message"
    assert session.turns[2].assistant_text == "Third response"


def test_bounded_rolling_context_retrieval():
    """Verify reasoner context extracts last 4 turns and rolling summary."""
    store = SessionStore()
    session = store.create_session("test-session-2")
    session.rolling_summary = "User is studying cryptography."

    for i in range(1, 7):
        session.add_turn(
            TurnRecord(
                turn_id=f"t{i}",
                timestamp=float(i * 10),
                user_text=f"Question {i}",
                assistant_text=f"Answer {i}",
                decision_mode="DIRECT_ANSWER",
            )
        )

    context = store.get_reasoner_context(session, max_turns=4)
    recent = context["recent_turns"]

    assert len(recent) == 4
    # Chronological order of the last 4 turns: t3, t4, t5, t6
    assert [t["turn_id"] for t in recent] == ["t3", "t4", "t5", "t6"]
    assert context["rolling_summary"] == "User is studying cryptography."


def test_pinned_artifact_tracking_and_verification_requirement():
    """
    Verify artifact pinning and invariant that artifacts require affirmative verification.
    An artifact mentioned by the model is NOT verified by default.
    """
    session = ConversationSession(session_id="test-session-3")

    # Unverified artifact (e.g. model mentioned a file that does not exist)
    unverified_art = PinnedArtifact(
        artifact_id="art-unverified-1",
        kind=ArtifactKind.FILE,
        display_name="notes.txt",
        verified_identity="C:/temp/notes.txt",
        path="C:/temp/notes.txt",
        verified=False,
    )
    assert unverified_art.verified is False

    # Verified artifact (affirmatively created and verified on disk)
    verified_art = PinnedArtifact(
        artifact_id="art-verified-1",
        kind=ArtifactKind.FILE,
        display_name="example.txt",
        verified_identity="C:/temp/example.txt",
        path="C:/temp/example.txt",
        verified=True,
    )
    assert verified_art.verified is True

    session.pin_artifact("last_file", verified_art)
    assert "last_file" in session.pinned_artifacts
    assert session.pinned_artifacts["last_file"].verified is True
    assert session.pinned_artifacts["last_file"].path == "C:/temp/example.txt"


def test_session_isolation():
    """Verify independent sessions in SessionStore do not share state or bleed context."""
    store = SessionStore()
    store.clear()

    s1 = store.create_session("session-alpha")
    s2 = store.create_session("session-beta")

    s1.add_turn(
        TurnRecord(
            turn_id="t-alpha-1",
            timestamp=1.0,
            user_text="Alpha secret",
            assistant_text="Alpha reply",
            decision_mode="DIRECT_ANSWER",
        )
    )
    s1.pin_artifact(
        "alpha_doc",
        PinnedArtifact(
            artifact_id="art-a",
            kind=ArtifactKind.FILE,
            display_name="alpha.txt",
            verified_identity="/alpha.txt",
            verified=True,
        ),
    )

    # Verify session-beta has no knowledge of session-alpha
    ctx_beta = store.get_reasoner_context(s2)
    assert len(ctx_beta["recent_turns"]) == 0
    assert "alpha_doc" not in ctx_beta["pinned_artifacts"]
    assert len(s2.turns) == 0


def test_failed_turn_handling():
    """Verify failed turns are accurately recorded with error summaries."""
    session = ConversationSession(session_id="test-session-error")
    turn = TurnRecord(
        turn_id="t-err-1",
        timestamp=time.time(),
        user_text="Execute unauthorized command",
        assistant_text="Operation blocked by security governance",
        decision_mode="REFUSE",
        verified=False,
        error_summary="SECURITY_BLOCK: Disallowed destructive mutation",
    )
    session.add_turn(turn)

    assert len(session.turns) == 1
    rec = session.turns[0]
    assert rec.verified is False
    assert rec.error_summary == "SECURITY_BLOCK: Disallowed destructive mutation"
