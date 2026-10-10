"""Targeted Regression and Acceptance Tests for Phase F0-17.

Validates end-to-end production routing for natural-language application requests,
politeness stripping, spaCy / fallback parity, and rejection of ambiguous / non-actionable queries.
"""

import os
import pytest

from astrarun.nlp.structure_engine import NeuralStructureEngine
from astrarun.workflows.compiler import WorkflowCompiler
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.policy.action_gate import ActionGate


@pytest.fixture
def structure_engine():
    return NeuralStructureEngine()


@pytest.fixture
def compiler():
    return WorkflowCompiler()


class TestF017NaturalLanguageRouting:
    """Empirical verification of natural-language application opening."""

    @pytest.mark.parametrize("query,expected_app", [
        ("can u open calculator", "calculator"),
        ("open calculator", "calculator"),
        ("could you open the calculator", "calculator"),
        ("launch calc", "calc"),
        ("start calculator", "calculator"),
        ("please bring up calculator", "calculator"),
        ("open notepad", "notepad"),
        ("can you launch notepad", "notepad"),
        ("start paint", "paint"),
        ("open settings", "settings"),
    ])
    def test_positive_app_launch_spacy(self, structure_engine, compiler, query, expected_app):
        """Verify spaCy neural parsing produces open_application step with correct app."""
        req = structure_engine.parse(query)
        assert len(req.clauses) >= 1
        assert not req.has_negation

        utt = req.to_structured_utterance()
        prop = compiler.compile(utt)

        assert prop.status == "READY", f"Failed for '{query}': {prop.status}, unsupported={prop.unsupported_clauses}"
        assert len(prop.steps) == 1
        assert prop.steps[0].tool == "open_application"
        assert prop.steps[0].arguments.get("app") == expected_app

    @pytest.mark.parametrize("query,expected_app", [
        ("can u open calculator", "calculator"),
        ("open calculator", "calculator"),
        ("could you open the calculator", "calculator"),
        ("launch calc", "calc"),
        ("start calculator", "calculator"),
        ("please bring up calculator", "calculator"),
        ("open notepad", "notepad"),
        ("can you launch notepad", "notepad"),
        ("start paint", "paint"),
        ("open settings", "settings"),
    ])
    def test_positive_app_launch_fallback(self, structure_engine, compiler, query, expected_app):
        """Verify deterministic fallback parser produces open_application step when spaCy is unavailable."""
        req = structure_engine._parse_fallback(query)
        assert len(req.clauses) >= 1
        assert not req.has_negation

        utt = req.to_structured_utterance()
        prop = compiler.compile(utt)

        assert prop.status == "READY", f"Failed for '{query}': {prop.status}, unsupported={prop.unsupported_clauses}"
        assert len(prop.steps) == 1
        assert prop.steps[0].tool == "open_application"
        assert prop.steps[0].arguments.get("app") == expected_app

    @pytest.mark.parametrize("query", [
        "calculator",
        "I was talking about calculator earlier",
        "why does calculator exist",
        "can you tell me whether calculator is installed",
    ])
    def test_negative_queries_do_not_launch_app(self, structure_engine, compiler, query):
        """Verify conversational statements and questions do not generate execution steps."""
        req = structure_engine.parse(query)
        utt = req.to_structured_utterance()
        prop = compiler.compile(utt)
        assert len(prop.steps) == 0

    def test_negation_safety_dont_open_calculator(self, structure_engine, compiler):
        """Verify explicit negation strictly prevents tool proposal."""
        req = structure_engine.parse("don't open calculator")
        assert req.has_negation
        utt = req.to_structured_utterance()
        prop = compiler.compile(utt)
        assert len(prop.steps) == 0

    def test_end_to_end_app_handle_request_dry_run(self):
        """Verify full AstraApplication pipeline from raw prompt to CapabilityResult."""
        os.environ["ASTRARUN_HEADLESS"] = "1"
        from astrarun.app import AstraApplication

        app = AstraApplication()
        res = app.handle_request("can u open calculator", dry_run=True)

        assert res.success is True
        assert res.type in ("fast_path", "capability_result")
        assert ("calc" in res.message.lower() or "calculator" in res.message.lower())
        assert "unknown" not in res.message.lower()
        assert not res.message.startswith("Blocked:")
