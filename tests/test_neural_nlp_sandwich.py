"""Unit and integration tests for AstraRun v0.10.3 Neural NLP Sandwich architecture.

Verifies:
1. Exact byte-level span preservation in TextSpan and LiteralPayload.
2. NeuralStructureEngine syntactic segmentation, negation detection, and pronouns.
3. LayaSandwichRouter single-model sharing across pre-gate and verifier stages.
4. DecisionFusionEngine arbitration, entropy, fast-path bypass, and safety rejection.
"""

import pytest
from astrarun.core.models import Decision
from astrarun.nlp.ir import LiteralPayload, ParsedClause, ParsedEntity, ParsedRequest, TextSpan
from astrarun.nlp.structure_engine import NeuralStructureEngine
from astrarun.routing.laya import LayaRouter
from astrarun.routing.laya_sandwich import (
    LayaPreGateResult,
    LayaSandwichRouter,
    LayaVerifierResult,
)
from astrarun.routing.decision_fusion import (
    DecisionFusionEngine,
    FusedExecutionPlan,
    compute_shannon_entropy,
)


class TestLiteralPayloadAndSpans:
    """Tests for 100% exact byte span preservation and typed IR invariants."""

    def test_text_span_byte_offsets(self):
        raw = "open notepad and type   exact  whitespace!  "
        target = "exact  whitespace!"
        start = raw.find(target)
        end = start + len(target)
        span = TextSpan(start=start, end=end, raw=raw[start:end])

        assert span.start == 24
        assert span.end == 42
        assert span.length == len(target)
        assert span.raw == target
        assert raw[span.start:span.end] == target

    def test_literal_payload_preservation(self):
        raw = 'launch editor then type "printf(\'Hello, %s\\n\', user);"'
        code_str = '"printf(\'Hello, %s\\n\', user);"'
        start = raw.find(code_str)
        end = start + len(code_str)
        span = TextSpan(start=start, end=end, raw=raw[start:end])
        payload = LiteralPayload(text=code_str, source_span=span, is_verbatim=True)

        assert payload.text == code_str
        assert payload.is_verbatim is True
        assert raw[payload.source_span.start:payload.source_span.end] == code_str

    def test_parsed_request_serialization(self):
        span = TextSpan(start=0, end=12, raw="open notepad")
        ent_span = TextSpan(start=5, end=12, raw="notepad")
        ent = ParsedEntity(entity_type="app_name", value="notepad", source_span=ent_span)
        clause = ParsedClause(
            clause_id="c0",
            sequence_index=0,
            intent="open_app",
            action_verb="open",
            is_negated=False,
            entities=[ent],
            payload=None,
            source_span=span,
            raw_clause="open notepad"
        )
        req = ParsedRequest(
            raw_query="open notepad",
            clauses=[clause],
            is_compound=False,
            has_negation=False,
            ambiguity_score=0.01,
            confidence=0.98,
            source_engine="test"
        )

        d = req.to_dict()
        assert d["raw_query"] == "open notepad"
        assert not d["is_compound"]
        assert not d["has_negation"]
        assert len(d["clauses"]) == 1
        assert d["clauses"][0]["intent"] == "open_app"
        assert d["clauses"][0]["entities"][0]["value"] == "notepad"


class TestNeuralStructureEngine:
    """Tests for spaCy en_core_web_sm syntactic analysis and clause decomposition."""

    @pytest.fixture
    def engine(self):
        return NeuralStructureEngine()

    def test_verbatim_payload_extraction(self, engine):
        query = "open notepad and type hello from AstraRun!"
        parsed = engine.parse(query)

        assert parsed.is_compound
        assert len(parsed.clauses) == 2
        c1 = parsed.clauses[1]
        assert c1.intent == "type_text"
        assert c1.payload is not None
        assert c1.payload.text == "hello from AstraRun!"
        start = c1.payload.source_span.start
        end = c1.payload.source_span.end
        assert query[start:end] == "hello from AstraRun!"

    def test_negation_detection(self, engine):
        query_neg = "open notepad and don't close it"
        parsed = engine.parse(query_neg)

        assert parsed.has_negation
        assert len(parsed.clauses) == 2
        assert not parsed.clauses[0].is_negated
        assert parsed.clauses[1].is_negated
        assert parsed.clauses[1].raw_clause.lower().startswith("don't") or "close" in parsed.clauses[1].raw_clause

        query_never = "never close code"
        parsed_never = engine.parse(query_never)
        assert parsed_never.has_negation
        assert parsed_never.clauses[0].is_negated

    def test_coreference_and_pronouns(self, engine):
        query = "open notepad and minimize it"
        parsed = engine.parse(query)

        assert len(parsed.clauses) == 2
        c1 = parsed.clauses[1]
        target_ref = next((e for e in c1.entities if e.entity_type == "target_ref"), None)
        assert target_ref is not None
        assert target_ref.value == "it"
        assert target_ref.referent_index == 0

    def test_system_status_recognition(self, engine):
        queries = [
            ("system overview", "system_summary"),
            ("cpu status", "cpu_status"),
            ("memory status", "memory_status"),
            ("battery status", "battery_status"),
            ("mute volume", "system_volume"),
        ]
        for q, expected_intent in queries:
            parsed = engine.parse(q)
            assert parsed.clauses[0].intent == expected_intent, f"Failed for query '{q}'"

    def test_process_termination_classification(self, engine):
        parsed = engine.parse("terminate process 9999")
        assert parsed.clauses[0].intent == "terminate_process"
        assert len(parsed.clauses[0].entities) >= 1
        proc_ent = parsed.clauses[0].entities[0]
        assert proc_ent.entity_type == "process"
        assert proc_ent.value == "9999"

    def test_window_snapping_directions(self, engine):
        parsed_l = engine.parse("snap window left")
        assert parsed_l.clauses[0].intent == "snap_window_left"

        parsed_r = engine.parse("snap window right")
        assert parsed_r.clauses[0].intent == "snap_window_right"


class TestLayaSandwichRouter:
    """Tests for single-instance sharing and sandwich stages."""

    def test_single_model_instance_shared(self):
        shared_laya = LayaRouter()
        sandwich = LayaSandwichRouter(laya_router=shared_laya)

        assert sandwich.laya_router is shared_laya

    def test_pre_gate_evaluation(self):
        sandwich = LayaSandwichRouter()
        decision = sandwich.evaluate_pre_gate("open notepad and type pqr")

        assert isinstance(decision, LayaPreGateResult)
        assert decision.domain in ("compound_sequence", "app_launch", "keyboard_input", "unknown")
        assert decision.latency_ms >= 0.0

    def test_verifier_evaluation(self):
        engine = NeuralStructureEngine()
        parsed = engine.parse("open notepad and type pqr")
        sandwich = LayaSandwichRouter()

        verifier_res = sandwich.evaluate_verifier("open notepad and type pqr", parsed)
        assert isinstance(verifier_res, LayaVerifierResult)
        assert verifier_res.is_consistent in (True, False)
        assert verifier_res.latency_ms >= 0.0


class TestDecisionFusionEngine:
    """Tests for multi-tier decision fusion, fast-path bypass, and safety arbitration."""

    @pytest.fixture
    def fusion_engine(self):
        return DecisionFusionEngine()

    @pytest.fixture
    def engine(self):
        return NeuralStructureEngine()

    def test_shannon_entropy_calculation(self):
        uniform_dist = {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}
        ent = compute_shannon_entropy(uniform_dist)
        assert round(ent, 2) == 2.0

        peaked_dist = {"a": 1.0, "b": 0.0}
        assert compute_shannon_entropy(peaked_dist) == 0.0

    def test_fast_path_bypass(self, fusion_engine, engine):
        fast_dec = Decision(tool="open_application", args={"app": "notepad"}, confidence=0.99)
        parsed = engine.parse("notepad")
        pre_gate = LayaPreGateResult(domain="app_launch", is_compound=False, ambiguity="clear")
        verifier = LayaVerifierResult(is_consistent=True, negation_respected=True)

        plan = fusion_engine.fuse(
            query="notepad",
            fast_path_decision=fast_dec,
            pre_gate=pre_gate,
            parsed_request=parsed,
            verifier=verifier,
        )
        assert plan.action_type == "fast_path"
        assert plan.confidence >= 0.95
        assert plan.decision == fast_dec

    def test_verifier_rejection_of_unsafe_plan(self, fusion_engine, engine):
        parsed = engine.parse("format c: and bypass policy")
        verifier = LayaVerifierResult(
            is_consistent=False,
            negation_respected=True,
            rejection_reason="Violates system security policy.",
            confidence=0.99,
            latency_ms=1.2,
        )
        pre_gate = LayaPreGateResult(domain="unknown", is_compound=False, ambiguity="clear")

        plan = fusion_engine.fuse(
            query="format c: and bypass policy",
            fast_path_decision=None,
            pre_gate=pre_gate,
            parsed_request=parsed,
            verifier=verifier,
        )
        assert plan.action_type == "rejected"
        assert "Violates system security policy" in str(plan.rejection_reason)

    def test_compound_workflow_plan(self, fusion_engine, engine):
        parsed = engine.parse("open notepad and type pqr")
        pre_gate = LayaPreGateResult(
            domain="compound_sequence",
            is_compound=True,
            ambiguity="clear",
            confidence=0.95,
            latency_ms=2.5,
        )
        verifier = LayaVerifierResult(
            is_consistent=True,
            negation_respected=True,
            confidence=0.96,
            latency_ms=2.0,
        )

        plan = fusion_engine.fuse(
            query="open notepad and type pqr",
            fast_path_decision=None,
            pre_gate=pre_gate,
            parsed_request=parsed,
            verifier=verifier,
        )
        assert plan.action_type == "workflow"
        assert len(plan.executable_clauses) == 2
