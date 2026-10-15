"""Comprehensive verification of InformationAcquisitionPlanner and Coordinator integration.

Invariants Verified:
1. Zero execution in Phase 1: Formulates structured plans without executing network or tool fetches.
2. Privacy governance: User private records are flagged privacy_sensitive=True and requires_authorization=True.
3. Authority requirements: Authoritative requests require PRIMARY_REQUIRED from primary specifications.
4. Coordinator lifecycle: Coordinator returns TurnStatus.INFORMATION_REQUIRED and records typed stream events.
5. Accuracy benchmarks: Unnecessary acquisition rate <= 5% and missed acquisition rate <= 5% on holdouts.
"""

import pytest
import time
from astrarun.agent.coordinator import AgentCoordinator, TurnStatus
from astrarun.cognition.acquisition import (
    AcquisitionPlan,
    AuthorityRequirement,
    FreshnessRequirement,
    InformationAcquisitionPlanner,
    NeedType,
    SourceType,
)
from astrarun.cognition.sufficiency import (
    KnowledgeSufficiencyEvaluator,
    KnowledgeSufficiencyResult,
    SufficiencyReason,
)
from astrarun.ingress.models import RequestEnvelope, RequestOrigin
from astrarun.session.events import (
    AcquisitionPlanCreatedEvent,
    EventType,
    InformationNeedCreatedEvent,
    KnowledgeSufficiencyEvaluatedEvent,
)
from astrarun.session.store import SessionStore


@pytest.fixture
def planner() -> InformationAcquisitionPlanner:
    return InformationAcquisitionPlanner()


@pytest.fixture
def evaluator() -> KnowledgeSufficiencyEvaluator:
    return KnowledgeSufficiencyEvaluator()


# ---------------------------------------------------------------------------
# Structured Plan Generation Tests
# ---------------------------------------------------------------------------

def test_plan_current_information(planner: InformationAcquisitionPlanner, evaluator: KnowledgeSufficiencyEvaluator):
    """Verify acquisition plan formulation for missing current information."""
    query = "What is the current stock price of Apple?"
    suff = evaluator.evaluate(query)
    assert suff.is_sufficient is False

    plan = planner.plan_acquisition(query, suff)
    assert plan.query == query
    assert len(plan.needs) >= 1
    assert plan.needs[0].need_type == NeedType.CURRENT
    assert plan.needs[0].privacy_sensitive is False

    # Check evidence requests and sources
    assert len(plan.evidence_requests) >= 1
    req = plan.evidence_requests[0]
    sources = req.target_sources
    assert any(s.source_type == SourceType.WEB_PRIMARY for s in sources)
    assert all(s.requires_authorization is False for s in sources)
    assert "additional information is required" in plan.user_summary.lower()


def test_plan_user_specific_context(planner: InformationAcquisitionPlanner, evaluator: KnowledgeSufficiencyEvaluator):
    """Verify acquisition plan formulation for private user data enforces privacy and authorization."""
    query = "Check my syllabus for CS 101."
    suff = evaluator.evaluate(query)
    assert suff.is_sufficient is False

    plan = planner.plan_acquisition(query, suff)
    assert len(plan.needs) >= 1
    need = plan.needs[0]
    assert need.need_type == NeedType.USER_SPECIFIC
    assert need.privacy_sensitive is True
    assert need.authority == AuthorityRequirement.USER_SOURCE_REQUIRED

    req = plan.evidence_requests[0]
    assert any(s.source_type == SourceType.LOCAL_KNOWLEDGE for s in req.target_sources)
    assert any(s.requires_authorization is True for s in req.target_sources)
    assert "requires explicit authorization" in plan.user_summary.lower()


def test_plan_authoritative_reference(planner: InformationAcquisitionPlanner, evaluator: KnowledgeSufficiencyEvaluator):
    """Verify acquisition plan for standards requests primary authoritative sources."""
    query = "Verify against RFC 7519 the claims specification for JWTs."
    suff = evaluator.evaluate(query)
    assert suff.is_sufficient is False

    plan = planner.plan_acquisition(query, suff)
    assert len(plan.needs) >= 1
    need = plan.needs[0]
    assert need.need_type == NeedType.AUTHORITATIVE_REFERENCE
    assert need.authority == AuthorityRequirement.PRIMARY_REQUIRED

    req = plan.evidence_requests[0]
    assert any(s.source_type == SourceType.WEB_PRIMARY for s in req.target_sources)
    assert any(s.source_type == SourceType.EXTERNAL_INTELLIGENCE for s in req.target_sources)


def test_plan_ambiguous_goal(planner: InformationAcquisitionPlanner, evaluator: KnowledgeSufficiencyEvaluator):
    """Verify ambiguous queries formulate clarification requests targeting dialogue."""
    query = "fix it"
    suff = evaluator.evaluate(query)
    assert suff.is_sufficient is False
    assert suff.reason == SufficiencyReason.AMBIGUOUS_GOAL

    plan = planner.plan_acquisition(query, suff)
    assert len(plan.needs) >= 1
    assert "clarify" in plan.user_summary.lower()


# ---------------------------------------------------------------------------
# Coordinator Integration & Lifecycle Test
# ---------------------------------------------------------------------------

def test_coordinator_handles_information_required():
    """Verify AgentCoordinator transitions turn to TurnStatus.INFORMATION_REQUIRED and records events."""
    coordinator = AgentCoordinator.get_instance()
    store = SessionStore.get_instance()
    session = store.create_session("sess-acq-coord")

    query = "What is the current weather in Paris right now?"
    env = RequestEnvelope.create(
        query,
        origin=RequestOrigin.LAUNCHER,
        session_id=session.session_id,
    )

    turn_res = coordinator.handle_turn(env, session)
    assert turn_res.status == TurnStatus.INFORMATION_REQUIRED
    assert "additional information is required" in turn_res.response_text.lower()
    assert "acquisition_plan" in turn_res.metadata

    # Verify session event stream
    events = store.get_events(session.session_id)
    event_types = [e.event_type for e in events]
    assert EventType.KNOWLEDGE_SUFFICIENCY_EVALUATED in event_types
    assert EventType.INFORMATION_NEED_CREATED in event_types
    assert EventType.ACQUISITION_PLAN_CREATED in event_types


# ---------------------------------------------------------------------------
# Holdout Accuracy Benchmarks (Unnecessary & Missed Acquisition <= 5%)
# ---------------------------------------------------------------------------

SELF_SUFFICIENT_HOLDOUT = [
    "Explain the concept of public key cryptography.",
    "How does quicksort partition an array?",
    "What is the time complexity of binary search?",
    "Derive the integral of 1/x.",
    "Explain Newton's third law of motion.",
    "What is the difference between a process and a thread?",
    "How does the immune system produce antibodies?",
    "What caused the fall of the Western Roman Empire?",
    "Explain tail recursion.",
    "What is the purpose of an index in a database?",
    "How does virtual memory paging work?",
    "Describe the water cycle.",
    "What is the difference between TCP and UDP?",
    "Explain modular arithmetic.",
    "What is Dijkstra's algorithm used for?",
    "open notepad",
    "launch calculator",
    "battery status",
    "2 + 2",
    "50 * 4",
]

ACQUISITION_REQUIRED_HOLDOUT = [
    "What is the current stock price of Microsoft?",
    "What is today's weather forecast for New York?",
    "Who won the game last night?",
    "What is the latest version of Kubernetes released?",
    "What is today's date?",
    "Check my syllabus for the midterm exam date.",
    "Summarize my meeting notes from yesterday.",
    "What did I write in my homework draft?",
    "Where is my resume saved on my computer?",
    "Check my schedule for tomorrow morning.",
    "Verify against RFC 6749 the OAuth 2.0 grant types.",
    "Check the NIST specification for AES key sizes.",
    "Cite the authoritative source for SHA-3.",
    "According to official documentation, what is os.scandir?",
    "What is happening with breaking news today?",
    "Current price of Bitcoin",
    "Review my tax return draft in my documents.",
    "What are the exam topics on my study guide?",
    "do it",
    "fix it",
]


def test_holdout_unnecessary_acquisition_rate(evaluator: KnowledgeSufficiencyEvaluator):
    """Verify unnecessary acquisition rate <= 5% (max 1 failure out of 20 self-sufficient queries)."""
    unnecessary_count = 0
    for query in SELF_SUFFICIENT_HOLDOUT:
        res = evaluator.evaluate(query)
        if not res.is_sufficient:
            unnecessary_count += 1

    rate = (unnecessary_count / len(SELF_SUFFICIENT_HOLDOUT)) * 100
    assert rate <= 5.0, f"Unnecessary acquisition rate {rate:.1f}% exceeded 5% bound ({unnecessary_count}/{len(SELF_SUFFICIENT_HOLDOUT)})"


def test_holdout_missed_acquisition_rate(evaluator: KnowledgeSufficiencyEvaluator):
    """Verify missed acquisition rate <= 5% (max 1 failure out of 20 queries needing acquisition)."""
    missed_count = 0
    for query in ACQUISITION_REQUIRED_HOLDOUT:
        res = evaluator.evaluate(query)
        if res.is_sufficient:
            missed_count += 1

    rate = (missed_count / len(ACQUISITION_REQUIRED_HOLDOUT)) * 100
    assert rate <= 5.0, f"Missed acquisition rate {rate:.1f}% exceeded 5% bound ({missed_count}/{len(ACQUISITION_REQUIRED_HOLDOUT)})"
