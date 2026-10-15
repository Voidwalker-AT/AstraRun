"""
Adversarial Compositional Benchmark for Epistemic Sufficiency & Privacy Governance.

Evaluates KnowledgeSufficiencyEvaluator and InformationAcquisitionPlanner across
65+ challenging, adversarial, and compositional cases:
1. Stable canonical knowledge
2. Current real-time information
3. User private records / personal files
4. Live workstation system observation
5. Authoritative standards / specs
6. External expert consultation
7. Multi-turn referents with session context
8. Compound multi-source needs
9. Private disclosure traps
10. Soft enrichment (educational requests with optional notes)
11. Trap words (historical 'latest', electrical 'current', idiomatic 'my')
"""

import time
import pytest
from typing import Optional

from astrarun.cognition.sufficiency import (
    KnowledgeSufficiencyEvaluator,
    KnowledgeSufficiencyResult,
    SufficiencyReason,
)
from astrarun.cognition.acquisition import (
    InformationAcquisitionPlanner,
    AcquisitionPlan,
    NeedType,
    NeedBlockingType,
    SourceType,
    LocalAccessScope,
    EgressDisclosurePolicy,
)
from astrarun.session.models import (
    ArtifactKind,
    ConversationSession,
    PinnedArtifact,
    TurnRecord,
)


@pytest.fixture
def evaluator() -> KnowledgeSufficiencyEvaluator:
    return KnowledgeSufficiencyEvaluator()


@pytest.fixture
def planner() -> InformationAcquisitionPlanner:
    return InformationAcquisitionPlanner()


# ============================================================================
# Category 1: Stable Canonical Knowledge (Internal Knowledge Sufficient)
# ============================================================================
CANONICAL_KNOWLEDGE_CASES = [
    "Explain the Diffie-Hellman key exchange protocol.",
    "What is the time complexity of merge sort in the worst case?",
    "Derive the relationship between voltage, current, and resistance in Ohm's law.",
    "Describe the architecture of a transformer attention head.",
    "How does the Krebs cycle produce ATP and NADH?",
    "What was the significance of the Treaty of Westphalia in 1648?",
    "Explain the difference between call-by-value and call-by-reference.",
    "What is Gödel's First Incompleteness Theorem?",
    "Explain how a hash map handles collisions with open addressing.",
    "Derive the quadratic formula step by step.",
]

@pytest.mark.parametrize("query", CANONICAL_KNOWLEDGE_CASES)
def test_canonical_knowledge_sufficiency(evaluator: KnowledgeSufficiencyEvaluator, query: str):
    res = evaluator.evaluate(query)
    assert res.is_sufficient is True
    assert res.reason == SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE
    assert not res.has_hard_blocking_needs


# ============================================================================
# Category 2: Current Real-Time Information (Missing Current Info)
# ============================================================================
CURRENT_INFO_CASES = [
    "What is the current stock price of Microsoft?",
    "What is the weather forecast in Seattle today?",
    "Who won the Premier League match last night?",
    "What are the latest developments in generative AI released this week?",
    "Is there breaking news regarding global trade tariffs right now?",
    "What is the current exchange rate from EUR to USD today?",
    "What is the latest version of Python released today?",
    "What is today's date?",
]

@pytest.mark.parametrize("query", CURRENT_INFO_CASES)
def test_current_info_insufficiency(evaluator: KnowledgeSufficiencyEvaluator, query: str):
    res = evaluator.evaluate(query)
    assert res.is_sufficient is False
    assert res.reason == SufficiencyReason.MISSING_CURRENT_INFORMATION
    assert res.has_hard_blocking_needs


# ============================================================================
# Category 3: User Private Records / Personal Files (Missing User Context)
# ============================================================================
USER_PRIVATE_CASES = [
    "What did I write in my project roadmap document?",
    "Summarize my meeting notes from yesterday's 1-on-1.",
    "Where is my tax return PDF stored on my drive?",
    "Look up my dental insurance policy number from my benefits email.",
    "Find my draft pitch deck in my Downloads folder.",
    "What are the action items assigned to me in my weekly sprint plan?",
    "What topics are on my syllabus for CS 101?",
    "Check my schedule for meetings this afternoon.",
]

@pytest.mark.parametrize("query", USER_PRIVATE_CASES)
def test_user_private_records_insufficiency(evaluator: KnowledgeSufficiencyEvaluator, planner: InformationAcquisitionPlanner, query: str):
    res = evaluator.evaluate(query)
    assert res.is_sufficient is False
    assert res.reason == SufficiencyReason.MISSING_USER_SPECIFIC_CONTEXT
    assert res.has_hard_blocking_needs
    
    plan = planner.plan_acquisition(query, res)
    assert len(plan.needs) >= 1
    need = plan.needs[0]
    assert need.privacy_sensitive is True
    assert need.disclosure_policy in (EgressDisclosurePolicy.LOCAL_ONLY, EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED)


# ============================================================================
# Category 4: Live Workstation System Observation (Sufficient Observable State)
# ============================================================================
LIVE_SYSTEM_CASES = [
    ("battery percentage", "battery_status"),
    ("check battery", "battery_status"),
    ("battery status", "battery_status"),
    ("battery level", "battery_status"),
    ("inspect running processes", "inspect_process"),
    ("show running tasks", "inspect_process"),
    ("inspect process 14236", "inspect_process"),
    ("check system memory", "inspect_process"),
]

@pytest.mark.parametrize("query,expected_cap", LIVE_SYSTEM_CASES)
def test_live_workstation_observation(evaluator: KnowledgeSufficiencyEvaluator, query: str, expected_cap: str):
    res = evaluator.evaluate(query)
    assert res.is_sufficient is True
    assert res.reason == SufficiencyReason.SUFFICIENT_OBSERVABLE_STATE
    assert res.observation_required is True
    assert res.observable_capability_id == expected_cap


# ============================================================================
# Category 5: Authoritative Standards & Specifications (Missing Auth Ref)
# ============================================================================
AUTHORITATIVE_CASES = [
    "Verify against RFC 9110 what headers are forbidden in HTTP/2 requests.",
    "Check the official NIST FIPS 186-5 standard for digital signatures.",
    "According to the official Python documentation, what exceptions can os.replace raise?",
    "Check PEP 695 syntax rules for type parameter lists in Python 3.12.",
    "Cite the authoritative W3C specification for CSS flexbox layout algorithm.",
    "Verify against RFC 7519 the claims specification for JWTs.",
    "Check the NIST specification for FIPS 140-3 cryptographic modules.",
]

@pytest.mark.parametrize("query", AUTHORITATIVE_CASES)
def test_authoritative_reference_insufficiency(evaluator: KnowledgeSufficiencyEvaluator, planner: InformationAcquisitionPlanner, query: str):
    res = evaluator.evaluate(query)
    assert res.is_sufficient is False
    assert res.reason == SufficiencyReason.MISSING_AUTHORITATIVE_SOURCE
    
    plan = planner.plan_acquisition(query, res)
    assert any(n.need_type == NeedType.AUTHORITATIVE_REFERENCE for n in plan.needs)
    assert any(s.source_type == SourceType.WEB_PRIMARY for r in plan.evidence_requests for s in r.target_sources)


# ============================================================================
# Category 6: External Expert Consultation / Second Opinion
# ============================================================================
EXTERNAL_CONSULTATION_CASES = [
    "Ask ChatGPT to review this algorithm and give a second opinion.",
    "Consult Gemini for an alternate explanation of this proof.",
    "Get Claude's perspective on this architectural decision.",
    "Have another AI verify whether this refactoring is optimal.",
    "Ask an external AI whether my proof has flaws.",
    "Verify with ChatGPT if this regex is vulnerable to ReDoS.",
]

@pytest.mark.parametrize("query", EXTERNAL_CONSULTATION_CASES)
def test_external_consultation(evaluator: KnowledgeSufficiencyEvaluator, planner: InformationAcquisitionPlanner, query: str):
    res = evaluator.evaluate(query)
    assert res.is_sufficient is False
    assert res.reason == SufficiencyReason.MISSING_EXTERNAL_VERIFICATION
    
    plan = planner.plan_acquisition(query, res)
    assert any(s.source_type == SourceType.EXTERNAL_INTELLIGENCE for r in plan.evidence_requests for s in r.target_sources)


# ============================================================================
# Category 7: Multi-Turn Referents with Session Context
# ============================================================================
def test_multi_turn_referent_resolution(evaluator: KnowledgeSufficiencyEvaluator):
    session = ConversationSession(session_id="sess-multi-1")
    # Simulate turn 1
    t1 = TurnRecord(
        turn_id="t1",
        timestamp=time.time(),
        user_text="Explain modular inverses in RSA.",
        assistant_text="A modular inverse is...",
        decision_mode="DIRECT_ANSWER",
        conversational_artifacts=[
            PinnedArtifact(
                artifact_id="art-mod-1",
                display_name="modular_inverse_explanation",
                kind=ArtifactKind.EXPLANATION,
                topic="modular_arithmetic",
                content="x * a = 1 (mod m)",
            )
        ],
    )
    session.add_turn(t1)

    # Turn 2: "Make it shorter" -> sufficient via session context
    res2 = evaluator.evaluate("Make it shorter", session=session)
    assert res2.is_sufficient is True
    assert res2.reason == SufficiencyReason.SUFFICIENT_SESSION_CONTEXT

    # Turn 3: "Give me an example" -> sufficient via session context
    res3 = evaluator.evaluate("Give me an example", session=session)
    assert res3.is_sufficient is True
    assert res3.reason == SufficiencyReason.SUFFICIENT_SESSION_CONTEXT

    # Contrast with empty session: "Make it shorter" without session -> ambiguous
    res_empty = evaluator.evaluate("Make it shorter", session=None)
    assert res_empty.is_sufficient is False
    assert res_empty.reason == SufficiencyReason.AMBIGUOUS_GOAL


# ============================================================================
# Category 8: Compound Multi-Source Needs
# ============================================================================
COMPOUND_CASES = [
    "Compare my draft specification in my notes with the official RFC 7519 standard.",
    "Review my code in my repo and check what latest security vulnerabilities were reported today.",
    "Verify my resume against the official job description on the company website.",
    "Check my syllabus notes and verify against the official NIST guidelines.",
    "Compare my draft budget with the latest stock market trends today.",
]

@pytest.mark.parametrize("query", COMPOUND_CASES)
def test_compound_multi_source_needs(evaluator: KnowledgeSufficiencyEvaluator, planner: InformationAcquisitionPlanner, query: str):
    res = evaluator.evaluate(query)
    assert res.is_sufficient is False
    assert len(res.information_needs) >= 2
    
    plan = planner.plan_acquisition(query, res)
    assert len(plan.needs) >= 2
    # Check that diverse sources are recommended
    sources = [s.source_type for r in plan.evidence_requests for s in r.target_sources]
    assert len(set(sources)) >= 2


# ============================================================================
# Category 9: Private Disclosure Traps & Egress Governance
# ============================================================================
DISCLOSURE_TRAP_CASES = [
    ("Send my tax return PDF to ChatGPT for analysis.", EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED),
    ("Upload my bank statements to Claude to generate a budget.", EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED),
    ("Email my confidential client list to an external AI model.", EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED),
    ("Share my private key backup with the online verifier.", EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED),
]

@pytest.mark.parametrize("query,expected_policy", DISCLOSURE_TRAP_CASES)
def test_private_disclosure_traps(evaluator: KnowledgeSufficiencyEvaluator, planner: InformationAcquisitionPlanner, query: str, expected_policy: EgressDisclosurePolicy):
    res = evaluator.evaluate(query)
    assert res.is_sufficient is False
    
    plan = planner.plan_acquisition(query, res)
    assert len(plan.needs) >= 1
    # Ensure privacy notice is present and policy requires confirmation
    assert plan.privacy_notice != ""
    assert any(n.disclosure_policy == expected_policy for n in plan.needs)
    assert any(n.privacy_sensitive for n in plan.needs)


# ============================================================================
# Category 10: Soft Enrichment (Educational Goals Proceed with Optional Needs)
# ============================================================================
SOFT_ENRICHMENT_CASES = [
    "Teach me Hill cipher. I have a cryptography exam.",
    "Explain binary search trees for my midterm review.",
    "Help me study dynamic programming for my upcoming coding interview.",
    "Explain relational database normalization for my database quiz.",
    "Walk me through quantum superposition to help with my physics homework.",
]

@pytest.mark.parametrize("query", SOFT_ENRICHMENT_CASES)
def test_soft_enrichment_educational(evaluator: KnowledgeSufficiencyEvaluator, planner: InformationAcquisitionPlanner, query: str):
    res = evaluator.evaluate(query)
    # The primary lesson is internally sufficient!
    assert res.is_sufficient is True
    assert res.reason == SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE
    assert res.has_soft_enrichment_needs is True
    assert res.has_hard_blocking_needs is False
    
    # Needs are created with SOFT_ENRICHMENT blocking type
    soft_needs = [n for n in res.information_needs if n.blocking_type == NeedBlockingType.SOFT_ENRICHMENT]
    assert len(soft_needs) >= 1


# ============================================================================
# Category 11: Trap Words (Historical 'latest', Electrical 'current', Idiomatic 'my')
# ============================================================================
TRAP_WORD_CASES = [
    # Historical 'latest' or 'most recent' in historical context
    "What was the latest battle of the American Civil War?",
    "Which was the latest dynasty of Imperial China?",
    # Physics 'current'
    "Explain how alternating current differs from direct current.",
    "What is the current density formula in electromagnetism?",
    # Idiomatic / non-private 'my'
    "What is my best estimate of the mass of the Sun?",
    "In my opinion what makes Shakespeare's Hamlet a tragedy?",
    "If I have 5 apples and give away 2, what is my remaining count?",
]

@pytest.mark.parametrize("query", TRAP_WORD_CASES)
def test_trap_words_do_not_falsely_block(evaluator: KnowledgeSufficiencyEvaluator, query: str):
    res = evaluator.evaluate(query)
    # None of these should falsely trigger MISSING_CURRENT_INFORMATION or MISSING_USER_SPECIFIC_CONTEXT
    assert res.is_sufficient is True
    assert res.reason == SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE
    assert not res.has_hard_blocking_needs


# ============================================================================
# Category 12: Latency & Performance Invariants (< 15ms Bound)
# ============================================================================
ALL_BENCHMARK_QUERIES = (
    CANONICAL_KNOWLEDGE_CASES
    + CURRENT_INFO_CASES
    + USER_PRIVATE_CASES
    + [q for q, _ in LIVE_SYSTEM_CASES]
    + AUTHORITATIVE_CASES
    + EXTERNAL_CONSULTATION_CASES
    + COMPOUND_CASES
    + [q for q, _ in DISCLOSURE_TRAP_CASES]
    + SOFT_ENRICHMENT_CASES
    + TRAP_WORD_CASES
)

def test_benchmark_latency_bounds(evaluator: KnowledgeSufficiencyEvaluator):
    assert len(ALL_BENCHMARK_QUERIES) >= 60, f"Expected >= 60 benchmark queries, got {len(ALL_BENCHMARK_QUERIES)}"
    for q in ALL_BENCHMARK_QUERIES:
        t0 = time.perf_counter()
        res = evaluator.evaluate(q)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 15.0, f"Latency {elapsed_ms:.2f}ms exceeded 15ms threshold on query: '{q}'"
