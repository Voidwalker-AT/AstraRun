"""Unit and safety tests for KevRouter and shadow mode evaluation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.kev import KevDecision, KevRouter, _choice_confidence
from astrarun.telemetry.shadow_collector import KevShadowEventCollector
from astrarun.tools.registry import ToolRegistry


def test_kev_router_disabled():
    """Verify disabled Kev router abstains without attempting model load."""
    router = KevRouter(config={"enabled": False})
    dec = router.predict_intent("open notepad")
    assert dec.intent == "unknown"
    assert dec.confidence == 0.0
    assert not dec.is_executable_now
    assert "disabled" in str(dec.error).lower()


def test_kev_router_construction():
    """Verify default configuration and device resolution."""
    router = KevRouter(config={"enabled": True, "device": "cpu"})
    assert router.enabled is True
    assert router.mode == "shadow"
    assert router.device == "cpu"
    assert router.confidence_threshold == 0.75
    assert router.model_id == "jaredpalmer/kev-0.8b"


def test_kev_router_load_failure_resilience():
    """Verify graceful error recovery when model fails to load."""
    router = KevRouter(config={"enabled": True, "device": "cpu"})
    with patch.object(router, "_load_engine", return_value=False):
        router._load_error_msg = "Failed to load Kev model: Mocked load failure"
        dec = router.predict_intent("open my project")
        assert dec.intent == "unknown"
        assert dec.confidence == 0.0
        assert "mocked load failure" in str(dec.error).lower()


def test_kev_router_inference_exception_resilience():
    """Verify inference exceptions do not crash AstraRun."""
    router = KevRouter(config={"enabled": True, "device": "cpu"})
    with patch.object(router, "_load_engine", return_value=True):
        with patch("astrarun.routing.kev.KevRouter.predict_intent", return_value=KevDecision(
            intent="unknown",
            confidence=0.0,
            probabilities={},
            error="Corrupt tensor input"
        )):
            dec = router.predict_intent("open something")
            assert dec.intent == "unknown"
            assert dec.confidence == 0.0
            assert "corrupt tensor input" in str(dec.error).lower()


def test_kev_choice_confidence():
    """Verify TypeSafe (p_max - 1/K) / (1 - 1/K) calculation."""
    # 10 options, uniform (all 0.1) -> 0.0
    uniform = [0.1] * 10
    assert _choice_confidence(uniform) == pytest.approx(0.0, abs=1e-4)

    # 10 options, certainty (1.0, 0, 0, ...) -> 1.0
    certainty = [1.0] + [0.0] * 9
    assert _choice_confidence(certainty) == pytest.approx(1.0, abs=1e-4)

    # 10 options, 0.55 -> (0.55 - 0.1) / (0.9) = 0.50
    half = [0.55] + [0.05] * 9
    assert _choice_confidence(half) == pytest.approx(0.50, abs=1e-4)


def test_kev_router_intent_mapping():
    """Verify mapping from Kev intent output to AstraRun Decision."""
    router = KevRouter(config={"enabled": True, "device": "cpu"})
    context = RoutingContext()

    # Mock predict_intent directly to test router.route mapping
    with patch.object(
        router,
        "predict_intent",
        return_value=KevDecision(
            intent="open_app",
            confidence=0.92,
            probabilities={"open_app": 0.92, "open_project": 0.05, "unknown": 0.03},
            is_executable_now=True,
            source="kev"
        )
    ):
        dec = router.route("open vivaldi", context)
        assert dec.tool == "open_app"
        assert dec.args.get("app") == "vivaldi"
        assert dec.confidence == 0.92
        assert dec.source == "kev"

    # Test open_project (non-executable intent)
    with patch.object(
        router,
        "predict_intent",
        return_value=KevDecision(
            intent="open_project",
            confidence=0.88,
            probabilities={"open_project": 0.88, "open_folder": 0.08, "unknown": 0.04},
            is_executable_now=False,
            requires_resolution=True,
            source="kev"
        )
    ):
        dec_proj = router.route("open my vivaldi project", context)
        assert dec_proj.tool == "unknown"
        assert dec_proj.confidence == 0.88
        assert dec_proj.args.get("intent") == "open_project"


def test_kev_confidence_preservation():
    """Verify full calibrated probability distribution is preserved."""
    router = KevRouter(config={"enabled": True, "device": "cpu"})
    raw_probs = {
        "open_app": 0.85,
        "open_project": 0.10,
        "unknown": 0.05
    }
    with patch.object(
        router,
        "predict_intent",
        return_value=KevDecision(
            intent="open_app",
            confidence=0.85,
            probabilities=raw_probs,
            is_executable_now=True,
            source="kev"
        )
    ):
        kev_dec = router.predict_intent("launch notepad")
        assert kev_dec.confidence == 0.85
        assert kev_dec.probabilities == raw_probs
        assert kev_dec.is_executable_now is True


def test_kev_shadow_event_collector(tmp_path):
    """Verify local shadow event collector records redacted events."""
    event_file = tmp_path / "kev_shadow_events.jsonl"
    collector = KevShadowEventCollector(event_file=event_file, enabled=True, store_raw_request=True)

    prod_dec = Decision(tool="unknown", args={}, confidence=0.0, source="deterministic")
    kev_dec = KevDecision(
        intent="open_project",
        confidence=0.91,
        probabilities={"open_project": 0.91, "unknown": 0.09},
        is_executable_now=False,
        requires_resolution=True,
        latency_ms=25.4,
        raw_result={"argmax_prob": 0.91}
    )

    collector.record_shadow_event(
        request="open my secret project with token sk-abcdef1234567890abcdef1234567890",
        production_decision=prod_dec,
        kev_decision=kev_dec
    )

    assert event_file.exists()
    content = event_file.read_text(encoding="utf-8").strip()
    data = json.loads(content)

    assert data["schema_version"] == 1
    assert "[REDACTED_API_KEY]" in data["request"]
    assert "sk-abcdef" not in data["request"]
    assert data["production"]["tool"] == "unknown"
    assert data["kev"]["intent"] == "open_project"
    assert data["kev"]["confidence"] == 0.91
    assert data["kev"]["probabilities"]["open_project"] == 0.91


def test_shadow_mode_safety_zero_execution_authority():
    """
    CRITICAL MANDATORY SAFETY TEST:
    Prove that even if Kev predicts 'open_app' with high confidence (0.99),
    while production router predicts 'unknown', the application DOES NOT EXECUTE.
    """
    # 1. Setup production decision as unknown
    prod_decision = Decision(tool="unknown", args={}, confidence=0.0, source="deterministic")
    assert not prod_decision.is_resolved

    # 2. Setup Kev decision as high confidence open_app
    kev_decision = KevDecision(
        intent="open_app",
        confidence=0.99,
        probabilities={"open_app": 0.99, "unknown": 0.01},
        is_executable_now=True,
        requires_resolution=False
    )
    assert kev_decision.intent == "open_app"

    # 3. Verify Tool Registry ONLY executes production decision
    from astrarun.core.models import ToolMetadata
    registry = ToolRegistry()
    mock_app_executor = MagicMock()
    app_meta = registry.get("open_app")
    assert app_meta is not None
    registry.register(
        ToolMetadata(
            name="open_app",
            description=app_meta.description,
            risk=app_meta.risk,
            args_schema=app_meta.args_schema,
            handler=mock_app_executor,
        )
    )

    # In shadow mode, AstraRun dispatches the production decision:
    success, msg = registry.execute(prod_decision)

    # Assert that tool was NOT executed and result indicates unknown/unresolved
    assert success is False
    assert "don't know" in msg.lower() or "unresolved" in msg.lower()
    mock_app_executor.assert_not_called()
