"""Test suite for Phase F0-18: Universal Computer-Use Architecture,
Semantic Entity Resolution & General Agent Execution.
"""

from __future__ import annotations

import os
import sys
import pytest
from pathlib import Path

from astrarun.discovery.apps import AppDiscoveryCache
from astrarun.discovery.entity_resolver import SemanticEntityResolver, resolve_lnk_target
from astrarun.search.index import SearchIndex
from astrarun.search.models import CandidateCategory
from astrarun.computer_use.facade import ComputerUse
from astrarun.computer_use.models import (
    ActionBackend,
    ComputerUseObservation,
    ControlType,
    RecoveryAction,
    UIAction,
    UIElement,
    VerificationCondition,
    VerificationResult,
)
from astrarun.app import AstraApplication
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.security.execution_broker import ExecutionBroker
from astrarun.policy.action_gate import ActionGate


# =============================================================================
# 1. ENTITY RESOLUTION & CANDIDATE NORMALIZATION
# =============================================================================

def test_vlc_entity_resolution_no_maintenance_candidates():
    """Verify 'vlc' resolves to canonical VLC and excludes maintenance/skin shortcuts."""
    cache = AppDiscoveryCache()
    idx = SearchIndex()
    idx.build_from_sources(cache.apps, {}, {}, {})

    resolver = SemanticEntityResolver(app_cache=cache, search_index=idx)
    resolved = resolver.resolve_application("vlc")

    assert resolved is not None, "Failed to resolve VLC entity"
    assert "vlc" in resolved.name.lower()
    # Must NOT be a maintenance reset variant
    assert "reset" not in resolved.name.lower()
    assert "cache" not in resolved.name.lower()
    assert "skinned" not in resolved.name.lower()
    assert resolved.confidence >= 0.90


def test_search_index_deduplication_vlc():
    """Verify search index contains only single canonical VLC candidate >= 0.60 score."""
    cache = AppDiscoveryCache()
    idx = SearchIndex()
    idx.build_from_sources(cache.apps, {}, {}, {})

    results = idx.search("vlc", limit=10)
    high_score = [r for r in results if r.score >= 0.60]

    # Exactly 1 high-confidence VLC candidate should be present
    vlc_candidates = [r for r in high_score if "vlc" in r.name.lower() or "videolan" in r.target.lower()]
    assert len(vlc_candidates) == 1, f"Expected 1 VLC candidate, got: {[c.name for c in vlc_candidates]}"
    assert "reset" not in vlc_candidates[0].name.lower()
    assert "skinned" not in vlc_candidates[0].name.lower()


def test_lnk_target_resolution():
    """Verify pure-python .lnk target resolution extracts physical .exe without COM."""
    start_dirs = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    resolved_any = False
    for d in start_dirs:
        if d.exists():
            for lnk in d.rglob("*.lnk"):
                target = resolve_lnk_target(lnk)
                if target and target.lower().endswith(".exe") and os.path.exists(target):
                    resolved_any = True
                    break
        if resolved_any:
            break
    assert resolved_any, "Expected at least one Start Menu .lnk to resolve to physical .exe"


def test_nonexistent_application_resolution():
    """Verify nonexistent application returns None rather than inventing paths."""
    cache = AppDiscoveryCache()
    idx = SearchIndex()
    idx.build_from_sources(cache.apps, {}, {}, {})

    resolver = SemanticEntityResolver(app_cache=cache, search_index=idx)
    resolved = resolver.resolve_application("completely_nonexistent_application_987654")
    assert resolved is None


# =============================================================================
# 2. GENERAL INTENT ROUTING ACROSS 12 SEMANTIC CLASSES
# =============================================================================

@pytest.fixture(scope="module")
def app_instance():
    return AstraApplication()


def test_intent_computational_count(app_instance):
    """Semantic Class 7: COMPUTATIONAL_TASK ('count to 100') must evaluate computationally."""
    res = app_instance.handle_request("count to 100", dry_run=True)
    assert res.success is True
    assert res.type == "computational"
    assert "1, 2, 3" in res.message
    assert res.data.get("n") == 100


def test_intent_computational_math(app_instance):
    """Semantic Class 7: COMPUTATIONAL_TASK ('what is 25 * 4') must evaluate math."""
    res = app_instance.handle_request("what is 25 * 4", dry_run=True)
    assert res.success is True
    assert res.type == "computational"
    assert "100" in res.message


def test_intent_observation_installed(app_instance):
    """Semantic Class 4: SYSTEM_OBSERVATION ('is vlc installed?') must not launch app."""
    res = app_instance.handle_request("is vlc installed?", dry_run=True)
    assert res.success is True
    assert res.type == "observation"
    assert "installed" in res.message.lower()


def test_intent_observation_running(app_instance):
    """Semantic Class 4: SYSTEM_OBSERVATION ('is vlc running?') must return process status."""
    res = app_instance.handle_request("is vlc running?", dry_run=True)
    assert res.success is True
    assert res.type == "observation"
    assert "running" in res.message.lower()


def test_intent_negation_safety(app_instance):
    """Semantic Class 11: NEGATION_SAFETY ('don't open vlc') must be blocked."""
    res = app_instance.handle_request("don't open vlc", dry_run=True)
    assert res.success is False
    assert res.type == "blocked"
    assert "negation" in res.message.lower()


def test_intent_conversational(app_instance):
    """Semantic Class 9: CONVERSATIONAL_REQUEST ('hello', 'who are you') must respond directly."""
    res = app_instance.handle_request("hello", dry_run=True)
    assert res.success is True
    assert res.type == "conversational"

    res2 = app_instance.handle_request("who are you", dry_run=True)
    assert res2.success is True
    assert res2.type == "conversational"


def test_intent_application_launch(app_instance):
    """Semantic Class 1: APPLICATION_LAUNCH ('open vlc', 'can u open calculator')."""
    res1 = app_instance.handle_request("open vlc", dry_run=True)
    assert res1.success is True

    res2 = app_instance.handle_request("can u open calculator", dry_run=True)
    assert res2.success is True


def test_intent_application_close(app_instance):
    """Semantic Class 2: APPLICATION_CLOSE ('close vlc', 'quit paint')."""
    res = app_instance.handle_request("close vlc", dry_run=True)
    # Even if vlc is not running, close command must be recognized and safe ownership enforced
    assert res.type in ("capability_result", "fast_path", "error")
    assert "close" in str(res.message).lower() or "running instance" in str(res.message).lower() or res.success


# =============================================================================
# 3. UNIFIED COMPUTER-USE FACADE CONTRACTS
# =============================================================================

def test_computer_use_observe():
    """Verify ComputerUse.observe() returns valid ComputerUseObservation."""
    cu = ComputerUse.get_instance()
    obs = cu.observe()

    assert isinstance(obs, ComputerUseObservation)
    assert obs.timestamp > 0
    assert obs.source_backend == ActionBackend.UIA
    assert isinstance(obs.available_actions, list)
    assert "click" in obs.available_actions
    assert not obs.is_stale(max_age_seconds=10.0)


def test_computer_use_discover():
    """Verify ComputerUse.discover() finds installed applications."""
    cu = ComputerUse.get_instance()
    apps = cu.discover()
    assert len(apps) > 10, "Expected at least 10 discovered apps"

    vlc_apps = cu.discover("vlc")
    assert len(vlc_apps) >= 1, "Expected to find VLC"


def test_computer_use_resolve():
    """Verify ComputerUse.resolve() resolves canonical entity."""
    cu = ComputerUse.get_instance()
    resolved = cu.resolve("vlc")
    assert resolved is not None
    assert "vlc" in resolved.name.lower()
    assert "reset" not in resolved.name.lower()


def test_computer_use_verify():
    """Verify ComputerUse.verify() detects environmental ground truth."""
    cu = ComputerUse.get_instance()

    # Process check
    cond_true = VerificationCondition(condition_type="process_running", target="python.exe", timeout_seconds=1.0)
    res_true = cu.verify(cond_true)
    assert res_true.verified is True
    assert res_true.observed_value is not None

    cond_false = VerificationCondition(condition_type="process_running", target="fictitious_process_9999.exe", timeout_seconds=0.3)
    res_false = cu.verify(cond_false)
    assert res_false.verified is False


def test_computer_use_recover():
    """Verify ComputerUse.recover() enforces bounded retry budget."""
    cu = ComputerUse.get_instance()

    # Attempt 1 -> retry
    rec1 = cu.recover("Connection reset", attempt=1, max_attempts=3)
    assert rec1.action == "retry"

    # Attempt 2 stale element -> reobserve
    rec2 = cu.recover("Element is stale", attempt=2, max_attempts=3)
    assert rec2.action == "reobserve"

    # Attempt 3 -> fail
    rec3 = cu.recover("Fatal error", attempt=3, max_attempts=3)
    assert rec3.action == "fail"
    assert "budget exceeded" in rec3.reason.lower()


# =============================================================================
# 4. SECURITY BOUNDARIES & INVARIANTS
# =============================================================================

def test_action_gate_authoritative_for_destructive_actions(app_instance):
    """Verify ActionGate enforces security policies on computer-use actions."""
    reg = app_instance.capability_registry
    cap = reg.get("open_application")
    assert cap is not None
    assert cap.permission.value in ("AUTO", "CONFIRM")

    # Non-registered tool must fail closed in ExecutionBroker
    from astrarun.security.execution_broker import ActionProposal, ActionCategory
    prop = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="arbitrary_unregistered_hack",
        parameters={},
    )
    res = app_instance.execution_broker.execute(prop)
    assert res.blocked is True
    assert res.verdict == "BLOCK"
    assert "SECURITY_DENY" in res.message

    # ActionGate fail-closed check
    from astrarun.routing.entity_resolver import ProposedAction
    pa = ProposedAction(
        action_type="arbitrary_unregistered_hack",
        arguments={},
        target="unknown",
        policy_allowed=False,
        status="blocked",
        raw_query="delete system32",
    )
    decision = app_instance.action_gate.evaluate(pa)
    assert decision.status.value.lower() == "block"
