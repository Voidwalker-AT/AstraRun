"""Comprehensive verification of KnowledgeSufficiencyEvaluator across diverse domains.

Invariants Verified:
1. Zero domain hardcoding: Generalizes across cryptography, physics, biology, history, computer science, law, and mathematics.
2. Latency bound: Local heuristic evaluation executes in < 15ms with zero network round trips.
3. Taxonomies: Correctly categorizes SUFFICIENT_INTERNAL_KNOWLEDGE, SUFFICIENT_SESSION_CONTEXT,
   MISSING_CURRENT_INFORMATION, MISSING_USER_SPECIFIC_CONTEXT, MISSING_LOCAL_CONTEXT,
   MISSING_AUTHORITATIVE_SOURCE, and AMBIGUOUS_GOAL.
4. Session context precedence: Conversational referents resolve against active session state.
"""

import time
import pytest
from astrarun.cognition.sufficiency import (
    KnowledgeSufficiencyEvaluator,
    KnowledgeSufficiencyResult,
    SufficiencyReason,
)
from astrarun.session.models import ConversationSession, TurnRecord
from astrarun.session.store import SessionStore


@pytest.fixture
def evaluator() -> KnowledgeSufficiencyEvaluator:
    return KnowledgeSufficiencyEvaluator()


@pytest.fixture
def active_session() -> ConversationSession:
    store = SessionStore.get_instance()
    sess = store.create_session("test-suff-session")
    sess.set_active_topic("modular_inverses")
    sess.add_turn(
        TurnRecord(
            turn_id="turn-1",
            timestamp=time.time(),
            user_text="Explain modular inverses.",
            assistant_text="A modular inverse of an integer a modulo m is an integer x such that a*x = 1 (mod m).",
            decision_mode="DIRECT_ANSWER",
            topic="modular_inverses",
        )
    )
    return sess


# ---------------------------------------------------------------------------
# Domain Generalization: Self-Sufficient Internal Knowledge
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query,domain",
    [
        # Cryptography
        ("Explain how Diffie-Hellman key exchange works.", "cryptography"),
        ("What is the difference between AES and RSA?", "cryptography"),
        ("Teach me Hill cipher.", "cryptography"),
        ("Why does Fermat's Little Theorem apply to primality testing?", "cryptography"),
        # Computer Science & Algorithms
        ("Explain Dijkstra's shortest path algorithm.", "computer_science"),
        ("What is the difference between a mutex and a spinlock?", "computer_science"),
        ("Describe tail call optimization in functional programming.", "computer_science"),
        ("How does a B-tree maintain balance during insertions?", "computer_science"),
        ("Explain deadlock prevention vs deadlock avoidance.", "computer_science"),
        # Physics & Mathematics
        ("Derive the quadratic formula step by step.", "mathematics"),
        ("Explain Kepler's second law of planetary motion.", "physics"),
        ("What are eigenvalues and eigenvectors geometrically?", "mathematics"),
        ("How does the photoelectric effect prove the particle nature of light?", "physics"),
        # Biology & Life Sciences
        ("How does mRNA translation occur at the ribosome?", "biology"),
        ("Explain the difference between mitosis and meiosis.", "biology"),
        ("Describe the function of ATP synthase in cellular respiration.", "biology"),
        # History & Humanities
        ("What were the primary economic causes of the French Revolution?", "history"),
        ("Explain the philosophical difference between deontology and utilitarianism.", "philosophy"),
        ("Describe the doctrine of separation of powers in constitutional law.", "law"),
        # Deterministic Operations
        ("open notepad", "desktop_operation"),
        ("launch calculator", "desktop_operation"),
        ("battery status", "desktop_operation"),
        ("2 + 2", "arithmetic"),
        ("125 * 8", "arithmetic"),
    ],
)
def test_self_sufficient_generalization(evaluator: KnowledgeSufficiencyEvaluator, query: str, domain: str):
    """Verify that broad theoretical and operational domains evaluate as self-sufficient."""
    t0 = time.perf_counter()
    result = evaluator.evaluate(query)
    latency_ms = (time.perf_counter() - t0) * 1000

    assert result.is_sufficient is True
    assert result.reason in (
        SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
        SufficiencyReason.SUFFICIENT_SESSION_CONTEXT,
    )
    assert latency_ms < 15.0, f"Latency {latency_ms:.2f}ms exceeded 15ms bound for '{query}'"


# ---------------------------------------------------------------------------
# Missing Current Information (Temporal Freshness)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "What is the current stock price of Apple?",
        "What is the weather in Tokyo right now?",
        "Who won the match last night?",
        "What is the latest version of Python released today?",
        "What is happening with breaking news in financial markets?",
        "What is today's date?",
    ],
)
def test_missing_current_information(evaluator: KnowledgeSufficiencyEvaluator, query: str):
    """Verify real-time and temporal queries evaluate to MISSING_CURRENT_INFORMATION."""
    result = evaluator.evaluate(query)
    assert result.is_sufficient is False
    assert result.reason == SufficiencyReason.MISSING_CURRENT_INFORMATION
    assert len(result.missing_aspects) > 0


# ---------------------------------------------------------------------------
# Missing User-Specific / Private Context
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "What topics are on my syllabus for CS 101?",
        "Summarize my exam notes for tomorrow's test.",
        "Check my schedule for meetings this afternoon.",
        "Where did I save my draft presentation?",
        "What did I write in my homework assignment?",
        "Review my resume in my documents folder.",
    ],
)
def test_missing_user_specific_context(evaluator: KnowledgeSufficiencyEvaluator, query: str):
    """Verify user private records evaluate to MISSING_USER_SPECIFIC_CONTEXT."""
    result = evaluator.evaluate(query)
    assert result.is_sufficient is False
    assert result.reason in (
        SufficiencyReason.MISSING_USER_SPECIFIC_CONTEXT,
        SufficiencyReason.MISSING_LOCAL_CONTEXT,
    )
    assert len(result.missing_aspects) > 0


# ---------------------------------------------------------------------------
# Missing Authoritative Reference / Verification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "Verify against RFC 7519 the claims specification for JWTs.",
        "Check the NIST specification for FIPS 140-3 cryptographic modules.",
        "According to the official documentation, what are the parameters for open()?",
        "Cite the authoritative source for HTTP 418 status code.",
    ],
)
def test_missing_authoritative_reference(evaluator: KnowledgeSufficiencyEvaluator, query: str):
    """Verify explicit authoritative standard requirements evaluate to MISSING_AUTHORITATIVE_SOURCE."""
    result = evaluator.evaluate(query)
    assert result.is_sufficient is False
    assert result.reason in (
        SufficiencyReason.MISSING_AUTHORITATIVE_SOURCE,
        SufficiencyReason.MISSING_EXTERNAL_VERIFICATION,
    )
    assert len(result.missing_aspects) > 0


# ---------------------------------------------------------------------------
# Ambiguous & Underspecified Queries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "do it",
        "fix it",
        "check",
        "run that",
    ],
)
def test_ambiguous_queries_without_session(evaluator: KnowledgeSufficiencyEvaluator, query: str):
    """Verify underspecified queries without prior context evaluate to AMBIGUOUS_GOAL."""
    result = evaluator.evaluate(query)
    assert result.is_sufficient is False
    assert result.reason == SufficiencyReason.AMBIGUOUS_GOAL


# ---------------------------------------------------------------------------
# Session Context Lineage Resolution
# ---------------------------------------------------------------------------

def test_conversational_pronoun_resolves_with_session(
    evaluator: KnowledgeSufficiencyEvaluator,
    active_session: ConversationSession,
):
    """Verify conversational pronouns evaluate to SUFFICIENT_SESSION_CONTEXT when session exists."""
    result = evaluator.evaluate("Make that explanation shorter.", session=active_session)
    assert result.is_sufficient is True
    assert result.reason == SufficiencyReason.SUFFICIENT_SESSION_CONTEXT

    result2 = evaluator.evaluate("Put that example in a text file at C:\\out.txt", session=active_session)
    assert result2.is_sufficient is True
    assert result2.reason == SufficiencyReason.SUFFICIENT_SESSION_CONTEXT
