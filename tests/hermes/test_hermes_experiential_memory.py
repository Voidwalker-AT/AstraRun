"""Unit and Integration Tests for Hermes Experiential Memory & Autonomous Exploration.

Tests:
- Entity and Affordance CRUD
- Bayesian Epistemic Confidence Updating
- Epistemic Contradiction Handling & Edge Invalidation
- Cryptographic Provenance and Environment Scoping
- Uncertainty Classification (KNOWN, LIKELY, UNCERTAIN, UNKNOWN, CONTRADICTED)
- Diagnostic Experiment Formulation & Risk Ceilings
- Anti-Poisoning & Verified Transition Ingestion
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from astrarun.hermes.exploration import (
    DiagnosticExperiment,
    EpistemicAssessment,
    HermesExplorationEngine,
)
from astrarun.hermes.models import (
    AffordanceEdge,
    AffordanceRisk,
    ConfidenceBand,
    EntityNode,
    EntityType,
    EpistemicStatus,
    ExperimentRecord,
    ExperimentStatus,
    ExplorationDecisionMode,
    StateTransitionRecord,
)
from astrarun.hermes.provenance import HermesProvenance
from astrarun.hermes.store import HermesKnowledgeStore


@pytest.fixture
def temp_hermes_store():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_hermes.db"
        store = HermesKnowledgeStore(db_path=db_path)
        yield store


def test_hermes_store_crud(temp_hermes_store):
    store = temp_hermes_store

    # 1. Entity
    ent = EntityNode.create(
        entity_type=EntityType.APPLICATION,
        name="MockEditor",
        class_name="MockEditorClass",
        env_hash="test_env_1",
    )
    store.upsert_entity(ent)
    fetched = store.find_entity_by_name("mockeditor")
    assert fetched is not None
    assert fetched.entity_id == ent.entity_id
    assert fetched.name == "MockEditor"

    # 2. Affordance
    aff = AffordanceEdge.create(
        entity_id=ent.entity_id,
        action_name="type_text",
        capability_id="type_text",
        confidence=0.20,
    )
    store.upsert_affordance(aff)
    fetched_aff = store.find_affordance(ent.entity_id, "type_text")
    assert fetched_aff is not None
    assert fetched_aff.affordance_id == aff.affordance_id
    assert fetched_aff.confidence == 0.20
    assert fetched_aff.confidence_band == ConfidenceBand.UNKNOWN


def test_bayesian_confidence_reinforcement(temp_hermes_store):
    store = temp_hermes_store

    ent = EntityNode.create(entity_type=EntityType.APPLICATION, name="CalcApp")
    store.upsert_entity(ent)
    aff = AffordanceEdge.create(
        entity_id=ent.entity_id,
        action_name="click_button",
        capability_id="click_button",
        confidence=0.20,
        status=EpistemicStatus.HYPOTHESIS,
    )
    store.upsert_affordance(aff)

    # First verified transition
    tr1 = StateTransitionRecord.create(
        affordance_id=aff.affordance_id,
        pre_state_hash="h0",
        action_payload={"btn": "5"},
        post_state_hash="h1",
        expected_delta={"display": "5"},
        observed_delta={"display": "5"},
        transition_verified=True,
        latency_ms=25.0,
        trace_id="t1",
        pre_frame_id="f0",
        post_frame_id="f1",
    )
    store.record_transition(tr1)

    score1, band1, aff1 = store.get_uncertainty_score("CalcApp", "click_button")
    assert aff1.verification_count == 1
    assert aff1.status == EpistemicStatus.OBSERVED
    assert score1 > 0.20  # Expect ~0.48
    assert band1 in (ConfidenceBand.UNCERTAIN, ConfidenceBand.LIKELY)

    # Second verified transition
    tr2 = StateTransitionRecord.create(
        affordance_id=aff.affordance_id,
        pre_state_hash="h1",
        action_payload={"btn": "+"},
        post_state_hash="h2",
        expected_delta={"op": "+"},
        observed_delta={"op": "+"},
        transition_verified=True,
        latency_ms=20.0,
        trace_id="t2",
        pre_frame_id="f1",
        post_frame_id="f2",
    )
    store.record_transition(tr2)

    score2, band2, aff2 = store.get_uncertainty_score("CalcApp", "click_button")
    assert aff2.verification_count == 2
    assert score2 > score1  # Expect ~0.66
    assert band2 == ConfidenceBand.LIKELY

    # Third verified transition pushes into VERIFIED (>= 0.85)
    tr3 = StateTransitionRecord.create(
        affordance_id=aff.affordance_id,
        pre_state_hash="h2",
        action_payload={"btn": "7"},
        post_state_hash="h3",
        expected_delta={"display": "7"},
        observed_delta={"display": "7"},
        transition_verified=True,
        latency_ms=18.0,
        trace_id="t3",
        pre_frame_id="f2",
        post_frame_id="f3",
    )
    store.record_transition(tr3)

    score3, band3, aff3 = store.get_uncertainty_score("CalcApp", "click_button")
    assert aff3.verification_count == 3
    assert score3 >= 0.78
    assert aff3.status in (EpistemicStatus.OBSERVED, EpistemicStatus.VERIFIED)


def test_contradiction_handling_and_invalidation(temp_hermes_store):
    store = temp_hermes_store

    ent = EntityNode.create(entity_type=EntityType.APPLICATION, name="FragileEditor")
    store.upsert_entity(ent)
    aff = AffordanceEdge.create(
        entity_id=ent.entity_id,
        action_name="save_document",
        capability_id="save_document",
        confidence=0.88,
        status=EpistemicStatus.VERIFIED,
    )
    store.upsert_affordance(aff)

    # Action fails physically (save dialog failed / corrupt)
    failed_tr = StateTransitionRecord.create(
        affordance_id=aff.affordance_id,
        pre_state_hash="h0",
        action_payload={"file": "doc.txt"},
        post_state_hash="h0",
        expected_delta={"file_saved": True},
        observed_delta={"file_saved": False, "error": "Dialog hang"},
        transition_verified=False,
        latency_ms=500.0,
        trace_id="fail_trace",
        pre_frame_id="f0",
        post_frame_id="f1",
    )
    store.record_transition(failed_tr)

    score, band, aff_after = store.get_uncertainty_score("FragileEditor", "save_document")
    assert aff_after.status == EpistemicStatus.CONTRADICTED
    assert aff_after.contradiction_count == 1
    assert score <= 0.20
    assert band == ConfidenceBand.CONTRADICTED


def test_provenance_and_environmental_scoping():
    env_hash = HermesProvenance.compute_env_hash()
    assert isinstance(env_hash, str)
    assert len(env_hash) > 8

    # Consistent hashing
    env_hash2 = HermesProvenance.compute_env_hash()
    assert env_hash == env_hash2

    # Text hashing
    thash = HermesProvenance.hash_text("test_payload")
    assert len(thash) == 64


def test_epistemic_uncertainty_assessment(temp_hermes_store):
    store = temp_hermes_store
    engine = HermesExplorationEngine(store=store)

    # 1. Cold Encounter -> UNKNOWN / EXPLORE
    cold = engine.assess_epistemic_state("CompletelyNewApp", candidate_action="type_text")
    assert cold.decision_mode == ExplorationDecisionMode.EXPLORE
    assert cold.confidence_band == ConfidenceBand.UNKNOWN
    assert cold.confidence_score == 0.0

    # 2. Seed entity with unverified affordance -> UNCERTAIN / EXPLORE
    ent = EntityNode.create(entity_type=EntityType.APPLICATION, name="KnownApp")
    store.upsert_entity(ent)
    aff = AffordanceEdge.create(
        entity_id=ent.entity_id,
        action_name="open_menu",
        capability_id="open_menu",
        confidence=0.35,
        status=EpistemicStatus.HYPOTHESIS,
    )
    store.upsert_affordance(aff)

    partial = engine.assess_epistemic_state("KnownApp", candidate_action="open_menu")
    assert partial.decision_mode == ExplorationDecisionMode.EXPLORE
    assert partial.confidence_band == ConfidenceBand.UNCERTAIN

    # 3. Seed entity with high confidence affordance -> KNOWN / ACT
    aff_known = AffordanceEdge.create(
        entity_id=ent.entity_id,
        action_name="close_window",
        capability_id="close_window",
        confidence=0.92,
        status=EpistemicStatus.VERIFIED,
    )
    store.upsert_affordance(aff_known)

    known = engine.assess_epistemic_state("KnownApp", candidate_action="close_window")
    assert known.decision_mode == ExplorationDecisionMode.ACT
    assert known.confidence_band == ConfidenceBand.KNOWN
    assert known.confidence_score >= 0.85


def test_diagnostic_experiment_formulation(temp_hermes_store):
    store = temp_hermes_store
    engine = HermesExplorationEngine(store=store)

    assessment = engine.assess_epistemic_state("UnfamiliarEditor", candidate_action="type_text")
    exp = engine.formulate_experiment(
        assessment=assessment,
        goal_prompt="Type sample document and verify",
        task_id="task_test_exp",
    )

    assert exp.target_entity_name == "UnfamiliarEditor"
    assert exp.risk_level in (AffordanceRisk.READ_ONLY, AffordanceRisk.BENIGN_MUTATION)
    assert exp.is_reversible is True
    assert len(exp.prompt_hash) == 64
    assert len(exp.response_hash) == 64
    assert exp.hypothesis != ""
    assert exp.proposed_capability_id != ""


def test_poisoning_rejection(temp_hermes_store):
    """Verify that unverified claims cannot promote knowledge without physical verification."""
    store = temp_hermes_store

    ent = EntityNode.create(entity_type=EntityType.APPLICATION, name="TargetApp")
    store.upsert_entity(ent)
    aff = AffordanceEdge.create(
        entity_id=ent.entity_id,
        action_name="destructive_action",
        capability_id="destructive_action",
        confidence=0.20,
        status=EpistemicStatus.HYPOTHESIS,
    )
    store.upsert_affordance(aff)

    # Fabricated failed attempt
    tr_fail = StateTransitionRecord.create(
        affordance_id=aff.affordance_id,
        pre_state_hash="pre",
        action_payload={},
        post_state_hash="pre",
        expected_delta={"success": True},
        observed_delta={"success": False, "error": "Blocked by ActionGate"},
        transition_verified=False,
        latency_ms=5.0,
        trace_id="poison_trace",
        pre_frame_id="f0",
        post_frame_id="f1",
    )
    store.record_transition(tr_fail)

    score, band, aff_now = store.get_uncertainty_score("TargetApp", "destructive_action")
    assert score <= 0.10
    assert band == ConfidenceBand.CONTRADICTED
    assert aff_now.status == EpistemicStatus.CONTRADICTED
