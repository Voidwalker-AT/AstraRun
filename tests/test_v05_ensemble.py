"""Unit and safety regression tests for AstraRun v0.5.

Covers:
- DecisionFusionEngine and ensemble modes (E0-E5)
- Statistical disagreement metrics (JSD, Shannon Entropy)
- Disagreement-gated abstention
- Ambiguity and risk gating
- Deterministic EntityResolutionEngine and hard policy boundaries
- Disambiguation logic for ambiguous workstation entities
- Jev reference router fallback and telemetry quarantine
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch
import pytest

from astrarun.routing.fusion import (
    DecisionFusionEngine,
    FusedDecision,
    jensen_shannon_divergence,
    shannon_entropy,
)
from astrarun.routing.laya import LayaDecision, LayaRouter
from astrarun.routing.entity_resolver import (
    EntityResolutionEngine,
    ProposedAction,
    PROTECTED_PROCESSES,
    PROTECTED_PORT_MAX,
)
from astrarun.routing.jev import JevDecision, JevRouter


# =========================================================================
# 1. Statistical Disagreement Metrics & Shannon Entropy
# =========================================================================

def test_shannon_entropy():
    # Certain distribution: H = 0.0
    certain = {"open_app": 1.0, "unknown": 0.0}
    assert shannon_entropy(certain) == 0.0

    # Uniform binary distribution: H = 1.0 bit
    uniform_2 = {"open_app": 0.5, "open_project": 0.5}
    assert math.isclose(shannon_entropy(uniform_2), 1.0, abs_tol=1e-3)


def test_jensen_shannon_divergence_identical():
    p = {"open_app": 0.9, "open_project": 0.1}
    q = {"open_app": 0.9, "open_project": 0.1}
    jsd = jensen_shannon_divergence(p, q)
    assert jsd == 0.0


def test_jensen_shannon_divergence_orthogonal():
    p = {"open_app": 1.0, "open_project": 0.0}
    q = {"open_app": 0.0, "open_project": 1.0}
    jsd = jensen_shannon_divergence(p, q)
    # Complete disagreement yields maximum divergence ~1.0
    assert math.isclose(jsd, 1.0, abs_tol=1e-2)


# =========================================================================
# 2. Decision Fusion Engine & Ensemble Modes (E0 - E5)
# =========================================================================

@pytest.fixture
def mock_generic_router():
    router = MagicMock(spec=LayaRouter)
    return router


@pytest.fixture
def mock_finetuned_router():
    router = MagicMock(spec=LayaRouter)
    return router


def test_fusion_mode_e0_generic(mock_generic_router, mock_finetuned_router):
    mock_generic_router.predict_intent.return_value = LayaDecision(
        intent="open_app",
        confidence=0.82,
        probabilities={"open_app": 0.82, "unknown": 0.18},
    )
    engine = DecisionFusionEngine(mock_generic_router, mock_finetuned_router)
    decision = engine.fuse("open notepad", mode="E0")

    assert decision.intent == "open_app"
    assert decision.confidence == 0.82
    assert decision.ensemble_mode == "E0"
    assert not decision.abstain


def test_fusion_mode_e1_finetuned(mock_generic_router, mock_finetuned_router):
    mock_finetuned_router.predict_intent.return_value = LayaDecision(
        intent="open_project",
        confidence=0.91,
        probabilities={"open_project": 0.91, "open_folder": 0.09},
    )
    engine = DecisionFusionEngine(mock_generic_router, mock_finetuned_router)
    decision = engine.fuse("open server", mode="E1")

    assert decision.intent == "open_project"
    assert decision.confidence == 0.91
    assert decision.ensemble_mode == "E1"
    assert not decision.abstain


def test_fusion_mode_e2_equal_weight(mock_generic_router, mock_finetuned_router):
    gen_dec = LayaDecision(
        intent="open_app",
        confidence=0.80,
        probabilities={"open_app": 0.80, "open_project": 0.20},
    )
    ft_dec = LayaDecision(
        intent="open_app",
        confidence=0.90,
        probabilities={"open_app": 0.90, "open_project": 0.10},
    )
    engine = DecisionFusionEngine(mock_generic_router, mock_finetuned_router)
    decision = engine.fuse("launch app", mode="E2", generic_decision=gen_dec, ft_decision=ft_dec)

    assert decision.intent == "open_app"
    assert math.isclose(decision.confidence, 0.85, abs_tol=1e-3)
    assert decision.ensemble_mode == "E2"
    assert decision.agreement is True


def test_disagreement_abstention_e4(mock_generic_router, mock_finetuned_router):
    """Verify E4 forces abstention (UNKNOWN) when models disagree on top intent."""
    gen_dec = LayaDecision(
        intent="open_app",
        confidence=0.75,
        probabilities={"open_app": 0.75, "unknown": 0.25},
    )
    ft_dec = LayaDecision(
        intent="open_project",
        confidence=0.78,
        probabilities={"open_project": 0.78, "unknown": 0.22},
    )
    engine = DecisionFusionEngine(mock_generic_router, mock_finetuned_router, js_threshold=0.25)
    decision = engine.fuse("open something", mode="E4", generic_decision=gen_dec, ft_decision=ft_dec)

    assert decision.intent == "unknown"
    assert decision.abstain is True
    assert "disagreement" in decision.abstain_reason.lower()
    assert decision.agreement is False


def test_ambiguity_gating_e5(mock_generic_router, mock_finetuned_router):
    """Verify E5 aborts execution when ambiguity is flagged."""
    gen_dec = LayaDecision(intent="open_app", confidence=0.85)
    ft_dec = LayaDecision(
        intent="open_app",
        confidence=0.88,
        raw_result={"answers": {"ambiguity": {"choice": "ambiguous"}, "risk": {"choice": "LOW"}}},
    )
    engine = DecisionFusionEngine(mock_generic_router, mock_finetuned_router)
    decision = engine.fuse("open it", mode="E5", generic_decision=gen_dec, ft_decision=ft_dec)

    assert decision.intent == "unknown"
    assert decision.abstain is True
    assert "ambiguity" in decision.abstain_reason.lower()
    assert decision.ambiguity_verdict == "ambiguous"


def test_risk_gating_e5_blocked(mock_generic_router, mock_finetuned_router):
    """Verify E5 strictly blocks dangerous commands when risk is BLOCKED."""
    gen_dec = LayaDecision(intent="process_action", confidence=0.90)
    ft_dec = LayaDecision(
        intent="process_action",
        confidence=0.92,
        raw_result={"answers": {"ambiguity": {"choice": "safe_to_resolve"}, "risk": {"choice": "BLOCKED"}}},
    )
    engine = DecisionFusionEngine(mock_generic_router, mock_finetuned_router)
    decision = engine.fuse("format c:", mode="E5", generic_decision=gen_dec, ft_decision=ft_dec)

    assert decision.intent == "unknown"
    assert decision.abstain is True
    assert decision.risk_verdict == "BLOCKED"
    assert "blocked" in decision.abstain_reason.lower()


# =========================================================================
# 3. Deterministic Entity Resolution Engine & Safety Policy
# =========================================================================

@pytest.fixture
def entity_resolver():
    return EntityResolutionEngine()


def test_entity_resolver_project_exact(entity_resolver):
    action = entity_resolver.resolve("open_project", "open server")
    assert action.status == "resolved"
    assert action.target == "Active/server"
    assert action.policy_allowed is True
    assert action.is_executable is True


def test_entity_resolver_project_ambiguous(entity_resolver):
    # If a query matches multiple projects with very close scores
    mock_resolver = EntityResolutionEngine()
    mock_resolver._projects_cache = [
        {"id": "test-core", "name": "Test Core", "path": "Active/test-core", "tags": ["test"]},
        {"id": "test-cli", "name": "Test CLI", "path": "Active/test-cli", "tags": ["test"]},
    ]
    action = mock_resolver.resolve("open_project", "open test")
    assert action.status == "ambiguous"
    assert action.target is None
    assert len(action.candidate_matches) >= 2
    assert not action.is_executable


def test_entity_resolver_protected_system_port(entity_resolver):
    """Verify ports <= 1023 are blocked by hard policy."""
    action = entity_resolver.resolve("process_action", "kill port 80")
    assert action.status == "blocked"
    assert action.policy_allowed is False
    assert "protected system port" in action.block_reason.lower()
    assert not action.is_executable


def test_entity_resolver_allowed_dev_port(entity_resolver):
    """Verify non-system ports (> 1023) resolve safely requiring confirmation."""
    action = entity_resolver.resolve("process_action", "kill port 3000")
    assert action.status == "resolved"
    assert action.target == "port:3000"
    assert action.requires_confirmation is True
    assert action.policy_allowed is True


def test_entity_resolver_protected_system_process(entity_resolver):
    """Verify Windows system processes cannot be targeted."""
    for proc in ("lsass", "svchost", "csrss"):
        action = entity_resolver.resolve("process_action", f"kill {proc}")
        assert action.status == "blocked"
        assert action.policy_allowed is False
        assert "protected windows system process" in action.block_reason.lower()


def test_entity_resolver_hard_policy_dangerous_command(entity_resolver):
    """Verify hard policy blocks dangerous shell operations unconditionally."""
    dangerous = [
        "rmdir /s /q c:\\",
        "format d:",
        "del c:\\windows\\system32",
    ]
    for cmd in dangerous:
        action = entity_resolver.resolve("system_action", cmd)
        assert action.status == "blocked"
        assert action.policy_allowed is False
        assert not action.is_executable


# =========================================================================
# 4. Jev Reference Router
# =========================================================================

def test_jev_unconfigured_fallback():
    """Verify Jev router gracefully degrades when API key is missing."""
    router = JevRouter(api_key=None, mock_mode=False)
    with patch.dict("os.environ", {}, clear=True):
        router.api_key = None
        dec = router.predict_intent("open notepad")
        assert dec.intent == "unknown"
        assert dec.confidence == 0.0
        assert dec.available is False
        assert "not configured" in dec.error.lower()
        assert not dec.is_resolved


def test_jev_mock_mode_simulation():
    """Verify Jev mock simulation produces calibrated reference predictions."""
    router = JevRouter(mock_mode=True)
    dec = router.predict_intent("open notepad")
    assert dec.available is True
    assert dec.intent == "open_app"
    assert dec.confidence >= 0.90
    assert dec.is_resolved


def test_jev_telemetry_quarantine():
    """Verify workstation paths are quarantined prior to transmission."""
    router = JevRouter()
    sanitized = router._sanitize_text("open file E:\\Workspace\\Active\\secret.py")
    assert "E:\\Workspace" not in sanitized
    assert "<LOCAL_PATH>" in sanitized
