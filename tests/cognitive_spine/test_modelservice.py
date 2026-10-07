"""Cognitive Spine Regression Suite: ModelService Schema & Routing Tests."""

import pytest
import os
from pathlib import Path

from astrarun.cognition.models import ModelRole, IntentDecision, PlanDAG
from astrarun.cognition.service import ModelService
from astrarun.security.secret_broker import SecretBroker


@pytest.fixture(scope="module")
def model_service():
    ms = ModelService.get_instance()
    return ms


def test_modelservice_loopback_endpoints(model_service):
    """Verify loopback isolation and canonical endpoints."""
    assert "127.0.0.1" in model_service.spark_endpoint
    assert "127.0.0.1" in model_service.deep_endpoint
    assert model_service.spark_port == 8090
    assert model_service.qwen_port == 8089


def test_modelservice_fast_route(model_service):
    """Verify fast routing and intent classification via Spark or deterministic fallback."""
    decision = model_service.route("find the document notes.txt in Documents folder")
    assert isinstance(decision, IntentDecision)
    assert decision.intent is not None
    assert decision.confidence > 0.0


def test_modelservice_deep_code_synthesis(model_service):
    """Verify Qwen2.5-Coder candidate tool generation with strict provenance."""
    # Ensure deep backend is running
    backend_ok = model_service.ensure_backend(ModelRole.DEEP, timeout=15.0)
    assert backend_ok, "Qwen2.5-Coder backend failed to become healthy on port 8089."

    cand = model_service.generate_code("Compute the first 10 Fibonacci numbers and print them")
    assert cand is not None
    assert cand.tool_id.startswith("dyn_tool_")
    assert cand.entrypoint in cand.source_files
    assert cand.provenance is not None
    assert cand.provenance.model == "qwen2.5-coder"
    assert len(cand.provenance.source_hash) == 64
    assert cand.provenance.revision == 1


def test_modelservice_secret_scrubbing(model_service):
    """Verify that sensitive tokens are never passed unscrubbed."""
    broker = SecretBroker.get_instance()
    scrubbed, was_redacted = broker.scrub_text("export OPENAI_API_KEY=sk-proj-1234567890abcdef1234567890")
    assert was_redacted
    assert "sk-proj-1234567890abcdef1234567890" not in scrubbed
