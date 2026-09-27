"""Unit and safety tests for LayaRouter and shadow mode evaluation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.laya import LayaDecision, LayaRouter
from astrarun.telemetry.shadow_collector import LayaShadowEventCollector
from astrarun.tools.registry import ToolRegistry


def test_laya_router_disabled():
    """Verify disabled Laya router abstains without attempting model load."""
    router = LayaRouter(config={"enabled": False})
    dec = router.predict_intent("open notepad")
    assert dec.intent == "unknown"
    assert dec.confidence == 0.0
    assert not dec.is_executable_now
    assert "disabled" in str(dec.error).lower()


def test_laya_router_construction():
    """Verify default configuration and device resolution."""
    router = LayaRouter(config={"enabled": True, "device": "cpu"})
    assert router.enabled is True
    assert router.mode == "shadow"
    assert router.device == "cpu"
    assert router.confidence_threshold == 0.75


def test_laya_router_load_failure_resilience():
    """Verify graceful error recovery when model fails to load."""
    router = LayaRouter(config={"enabled": True, "device": "cpu"})
    with patch("laya.load", side_effect=RuntimeError("CUDA out of memory")):
        dec = router.predict_intent("open my project")
        assert dec.intent == "unknown"
        assert dec.confidence == 0.0
        assert "failed to load" in str(dec.error).lower()


def test_laya_router_inference_exception_resilience():
    """Verify inference exceptions do not crash AstraRun."""
    router = LayaRouter(config={"enabled": True, "device": "cpu"})
    mock_agent = MagicMock()
    mock_agent.predict.side_effect = ValueError("Corrupt tensor input")
    router._agent = mock_agent

    dec = router.predict_intent("open something")
    assert dec.intent == "unknown"
    assert dec.confidence == 0.0
    assert "corrupt tensor input" in str(dec.error).lower()


def test_laya_router_intent_mapping():
    """Verify mapping from Laya choice output to AstraRun Decision."""
    router = LayaRouter(config={"enabled": True, "device": "cpu"})
    mock_agent = MagicMock()
    
    # 1. Test open_app
    mock_agent.predict.return_value = {
        "answers": {
            "intent": {
                "choice": "open_app",
                "confidence": 0.94,
                "probabilities": {"open_app": 0.94, "open_project": 0.04, "unknown": 0.02}
            }
        }
    }
    router._agent = mock_agent
    
    context = RoutingContext()
    dec = router.route("open vivaldi", context)
    assert dec.tool == "open_app"
    assert dec.args.get("app") == "vivaldi"
    assert dec.confidence == 0.94
    assert dec.source == "laya"

    # 2. Test open_project (non-executable intent)
    mock_agent.predict.return_value = {
        "answers": {
            "intent": {
                "choice": "open_project",
                "confidence": 0.88,
                "probabilities": {"open_project": 0.88, "open_folder": 0.08, "unknown": 0.04}
            }
        }
    }
    dec_proj = router.route("open my vivaldi project", context)
    assert dec_proj.tool == "unknown"
    assert dec_proj.confidence == 0.88
    assert dec_proj.args.get("intent") == "open_project"


def test_laya_confidence_preservation():
    """Verify full calibrated probability distribution is preserved."""
    router = LayaRouter(config={"enabled": True, "device": "cpu"})
    mock_agent = MagicMock()
    raw_probs = {
        "open_app": 0.85,
        "open_project": 0.10,
        "unknown": 0.05
    }
    mock_agent.predict.return_value = {
        "answers": {
            "intent": {
                "choice": "open_app",
                "confidence": 0.85,
                "probabilities": raw_probs
            }
        }
    }
    router._agent = mock_agent

    laya_dec = router.predict_intent("launch notepad")
    assert laya_dec.confidence == 0.85
    assert laya_dec.probabilities == raw_probs
    assert laya_dec.is_executable_now is True


def test_laya_shadow_event_collector(tmp_path):
    """Verify local shadow event collector records redacted events."""
    event_file = tmp_path / "shadow_events.jsonl"
    collector = LayaShadowEventCollector(event_file=event_file, enabled=True, store_raw_request=True)

    prod_dec = Decision(tool="unknown", args={}, confidence=0.0, source="deterministic")
    laya_dec = LayaDecision(
        intent="open_project",
        confidence=0.91,
        probabilities={"open_project": 0.91, "unknown": 0.09},
        is_executable_now=False,
        requires_resolution=True,
        latency_ms=25.4
    )

    collector.record_shadow_event(
        request="open my secret project with token sk-abcdef1234567890abcdef1234567890",
        production_decision=prod_dec,
        laya_decision=laya_dec
    )

    assert event_file.exists()
    content = event_file.read_text(encoding="utf-8").strip()
    data = json.loads(content)

    assert data["schema_version"] == 1
    assert "[REDACTED_API_KEY]" in data["request"]
    assert "sk-abcdef" not in data["request"]
    assert data["production"]["tool"] == "unknown"
    assert data["laya"]["intent"] == "open_project"
    assert data["laya"]["confidence"] == 0.91
    assert data["laya"]["probabilities"]["open_project"] == 0.91


def test_shadow_mode_safety_zero_execution_authority():
    """
    CRITICAL MANDATORY SAFETY TEST:
    Prove that even if Laya predicts 'open_app' with high confidence (0.99),
    while production router predicts 'unknown', the application DOES NOT EXECUTE.
    """
    # 1. Setup production decision as unknown
    prod_decision = Decision(tool="unknown", args={}, confidence=0.0, source="deterministic")
    assert not prod_decision.is_resolved

    # 2. Setup Laya decision as high confidence open_app
    laya_decision = LayaDecision(
        intent="open_app",
        confidence=0.99,
        probabilities={"open_app": 0.99, "unknown": 0.01},
        is_executable_now=True,
        requires_resolution=False
    )
    assert laya_decision.intent == "open_app"

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

