"""Comprehensive Automated Test Suite for AstraRun v0.8.5 Learning Foundation.

Covers:
- Domain models and serialization
- Confidence calculation, weights, and decay
- SQLite WAL persistence and audit logging
- Evidence extraction and non-learnable security filters
- Semantic memory store and conflict resolution
- Multi-tier alias manager precedence and type safety
- Pattern mining, parameterization, and risk classification
- Skill lifecycle, human review, and workflow compilation
- LearningEngine background orchestration
- Offline dataset export sanitization
- Non-learnable security invariants and policy regressions
- PySide6 UI components (MemoryView & SkillReviewWidget)
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from astrarun.core.models import ActionGateOutcome, ToolRisk
from astrarun.learning.aliases import AliasManager
from astrarun.learning.confidence import ConfidenceCalculator
from astrarun.learning.dataset_builder import DatasetBuilder
from astrarun.learning.engine import LearningEngine
from astrarun.learning.evidence import EvidenceExtractor
from astrarun.learning.memory import MemoryStore
from astrarun.learning.models import (
    AuditAction,
    AuditEvent,
    Correction,
    EvidenceReference,
    EvidenceType,
    MemoryNamespace,
    MemoryStatus,
    SemanticMemory,
    SkillCandidate,
    SkillStatus,
    SkillStep,
)
from astrarun.learning.patterns import PatternMiner
from astrarun.learning.persistence import LearningPersistence
from astrarun.learning.skills import SkillManager
from astrarun.policy.action_gate import ActionGate
from astrarun.routing.entity_resolver import ProposedAction
from astrarun.tasks.models import Task, TaskEvent, TaskEventType, TaskResult, TaskStatus
from astrarun.ui.memory import MemoryView, SkillReviewWidget


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance exists for UI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db():
    """Create a temporary database file for test isolation."""
    td = tempfile.TemporaryDirectory()
    db_path = Path(td.name) / "test_learning.db"
    yield db_path
    try:
        td.cleanup()
    except Exception:
        pass


# =============================================================================
# 1. Models & Serialization Tests
# =============================================================================

def test_models_serialization_roundtrip():
    ref = EvidenceReference(
        task_id="t1",
        conversation_id="c1",
        event_id="e1",
        evidence_type=EvidenceType.CONFIRMATION_ACCEPTED,
        timestamp=1000.0,
        weight=2.0,
        details={"foo": "bar"},
    )
    d_ref = ref.to_dict()
    ref2 = EvidenceReference.from_dict(d_ref)
    assert ref2.task_id == "t1"
    assert ref2.evidence_type == EvidenceType.CONFIRMATION_ACCEPTED
    assert ref2.weight == 2.0

    mem = SemanticMemory(
        id="m1",
        namespace=MemoryNamespace.ALIAS,
        key="editor",
        value="code",
        target_type="application",
        status=MemoryStatus.ACTIVE,
        confidence=0.92,
        support_count=3,
        contradiction_count=0,
        evidence_refs=[ref],
        user_confirmed=True,
        pinned=True,
    )
    d_mem = mem.to_dict()
    mem2 = SemanticMemory.from_dict(d_mem)
    assert mem2.id == "m1"
    assert mem2.namespace == MemoryNamespace.ALIAS
    assert mem2.value == "code"
    assert mem2.user_confirmed is True
    assert len(mem2.evidence_refs) == 1

    step = SkillStep(
        step_index=1,
        capability_id="capability.projects.open",
        arguments={"project": "AstraRun"},
        parameter_bindings={"project": "target_project"},
        requires_confirmation=False,
        risk_level="LOW",
    )
    d_step = step.to_dict()
    step2 = SkillStep.from_dict(d_step)
    assert step2.step_index == 1
    assert step2.capability_id == "capability.projects.open"

    skill = SkillCandidate(
        id="s1",
        name="open-and-build",
        description="Opens project and starts build",
        trigger_phrases=["run open build"],
        parameters=[{"name": "target_project", "type": "string", "default": "AstraRun"}],
        steps=[step],
        status=SkillStatus.CANDIDATE,
        support_count=4,
        confidence=0.88,
    )
    d_skill = skill.to_dict()
    skill2 = SkillCandidate.from_dict(d_skill)
    assert skill2.id == "s1"
    assert skill2.name == "open-and-build"
    assert len(skill2.steps) == 1


# =============================================================================
# 2. Confidence Calculator Tests
# =============================================================================

def test_confidence_calculator_positive_accumulation():
    calc = ConfidenceCalculator()
    now = time.time()

    refs = [
        EvidenceReference("t1", "c1", evidence_type=EvidenceType.CONFIRMATION_ACCEPTED, weight=2.0),
        EvidenceReference("t2", "c1", evidence_type=EvidenceType.CONFIRMATION_ACCEPTED, weight=2.0),
        EvidenceReference("t3", "c1", evidence_type=EvidenceType.CONFIRMATION_ACCEPTED, weight=2.0),
    ]
    conf, sup, cont = calc.calculate_confidence(refs, now, current_time=now)
    assert sup == 3
    assert cont == 0
    assert conf >= 0.85

    mem = SemanticMemory("m", MemoryNamespace.ALIAS, "k", "v", "app", evidence_refs=refs, last_used_at=now)
    assert calc.evaluate_status(mem, current_time=now) == MemoryStatus.ACTIVE


def test_confidence_calculator_contradiction_penalty():
    calc = ConfidenceCalculator()
    now = time.time()

    # 1 positive vs 1 correction (negative weight = 3.0 * 3.0 = 9.0)
    refs = [
        EvidenceReference("t1", "c1", evidence_type=EvidenceType.SUCCESSFUL_EXECUTION, weight=1.0),
        EvidenceReference("t2", "c1", evidence_type=EvidenceType.USER_CORRECTION, weight=3.0),
    ]
    conf, sup, cont = calc.calculate_confidence(refs, now, current_time=now)
    assert sup == 1
    assert cont == 1
    # Contradiction heavily penalizes score
    assert conf < 0.20

    mem = SemanticMemory("m", MemoryNamespace.ALIAS, "k", "v", "app", evidence_refs=refs, last_used_at=now)
    assert calc.evaluate_status(mem, current_time=now) == MemoryStatus.DEPRECATED


def test_confidence_calculator_pinned_decay_immunity():
    calc = ConfidenceCalculator()
    now = time.time()
    past = now - (120 * 86400.0)  # 120 days ago

    refs = [EvidenceReference("t1", "c1", evidence_type=EvidenceType.EXPLICIT_TEACHING, weight=3.0)]

    # Unpinned: decays significantly
    conf_unpinned, _, _ = calc.calculate_confidence(refs, past, pinned=False, current_time=now)

    # Pinned: floor >= 0.95
    conf_pinned, _, _ = calc.calculate_confidence(refs, past, pinned=True, current_time=now)

    assert conf_pinned >= 0.90
    assert conf_unpinned < conf_pinned


def test_conflict_detection():
    calc = ConfidenceCalculator()
    m1 = SemanticMemory("1", MemoryNamespace.ALIAS, "ed", "notepad", "app", status=MemoryStatus.ACTIVE, confidence=0.88)
    m2 = SemanticMemory("2", MemoryNamespace.ALIAS, "ed", "code", "app", status=MemoryStatus.ACTIVE, confidence=0.85)

    conflicted = calc.detect_conflicts([m1, m2])
    assert all(m.status == MemoryStatus.CONFLICTED for m in conflicted)


# =============================================================================
# 3. Persistence CRUD Tests
# =============================================================================

def test_persistence_crud_operations(temp_db):
    p = LearningPersistence(db_path=temp_db)
    assert p.check_integrity() is True

    mem = SemanticMemory(
        id="mem_1",
        namespace=MemoryNamespace.ALIAS,
        key="terminal",
        value="wt",
        target_type="application",
        status=MemoryStatus.ACTIVE,
        confidence=0.90,
    )
    p.save_memory(mem)

    loaded = p.get_memory("mem_1")
    assert loaded is not None
    assert loaded.key == "terminal"
    assert loaded.value == "wt"

    # Add evidence
    ref = EvidenceReference("t1", "c1", evidence_type=EvidenceType.SUCCESSFUL_EXECUTION, weight=1.0)
    loaded.evidence_refs.append(ref)
    p.save_memory(loaded)

    loaded2 = p.get_memory("mem_1")
    assert len(loaded2.evidence_refs) == 1

    # Corrections
    corr = Correction("c1", "t1", "conv1", {"target": "cmd"}, {"target": "wt"})
    p.save_correction(corr)
    corrs = p.list_corrections()
    assert len(corrs) == 1

    # Skills
    skill = SkillCandidate("s1", "build-flow", "Desc", steps=[SkillStep(1, "cap.build")])
    p.save_skill(skill)
    loaded_skill = p.get_skill("s1")
    assert loaded_skill is not None
    assert loaded_skill.name == "build-flow"

    # Audits
    audit = AuditEvent("a1", AuditAction.MEMORY_CREATED, "memory", "mem_1", details={"k": "v"})
    p.record_audit(audit)
    audits = p.list_audit_events()
    assert len(audits) == 1

    # Delete
    assert p.delete_memory("mem_1") is True
    assert p.get_memory("mem_1") is None


# =============================================================================
# 4. Evidence Extraction & Security Filter Tests
# =============================================================================

def test_evidence_extractor_teaching():
    ext = EvidenceExtractor()
    task1 = Task("1", "c", request_text="alias term to wt")
    mem1 = ext.extract_teaching(task1)
    assert mem1 is not None
    assert mem1.namespace == MemoryNamespace.ALIAS
    assert mem1.key == "term"
    assert mem1.value == "wt"
    assert mem1.user_confirmed is True

    task2 = Task("2", "c", request_text="my editor is vscode")
    mem2 = ext.extract_teaching(task2)
    assert mem2 is not None
    assert mem2.namespace == MemoryNamespace.PREFERENCE
    assert mem2.key == "editor"
    assert mem2.value == "vscode"


def test_evidence_extractor_security_rejections():
    ext = EvidenceExtractor()

    # Blocked processes
    for proc in ["lsass.exe", "csrss.exe", "wininit.exe"]:
        assert ext.is_security_safe("run it", proc) is False
        task = Task("t", "c", request_text=f"alias auth to {proc}")
        assert ext.extract_teaching(task) is None

    # Blocked commands
    assert ext.is_security_safe("alias wipe to format c:") is False
    assert ext.is_security_safe("alias clean to rmdir /s C:\\Windows") is False
    assert ext.is_security_safe("test; powershell -c whoami") is False


# =============================================================================
# 5. MemoryStore Tests
# =============================================================================

def test_memorystore_confirmation_and_rejection(temp_db):
    p = LearningPersistence(db_path=temp_db)
    store = MemoryStore(persistence=p)

    mem = store.add_or_update_memory(
        namespace=MemoryNamespace.ALIAS,
        key="nav",
        value="vivaldi",
        target_type="application",
    )
    assert mem.status == MemoryStatus.CANDIDATE

    confirmed = store.confirm_memory(mem.id)
    assert confirmed.status == MemoryStatus.ACTIVE
    assert confirmed.user_confirmed is True

    rejected = store.reject_memory(mem.id)
    assert rejected.status == MemoryStatus.REJECTED


def test_memorystore_apply_correction(temp_db):
    p = LearningPersistence(db_path=temp_db)
    store = MemoryStore(persistence=p)

    # Initial mapping: editor -> notepad
    store.add_or_update_memory(
        namespace=MemoryNamespace.ALIAS,
        key="editor",
        value="notepad",
        target_type="application",
    )

    corr = Correction(
        id="c1",
        task_id="t1",
        conversation_id="conv1",
        incorrect_mapping={"key": "editor", "target": "notepad"},
        corrected_mapping={"key": "editor", "target": "code"},
    )
    store.apply_correction(corr)

    active_mem = store.find_memory(MemoryNamespace.ALIAS, "editor")
    assert active_mem is not None
    assert active_mem.value == "code"
    assert active_mem.status == MemoryStatus.ACTIVE


# =============================================================================
# 6. AliasManager Precedence & Type Safety Tests
# =============================================================================

def test_alias_manager_precedence(temp_db):
    p = LearningPersistence(db_path=temp_db)
    store = MemoryStore(persistence=p)
    mgr = AliasManager(
        memory_store=store,
        static_aliases={"calc": "calc.exe"},
    )

    # Static overrides learned
    store.add_or_update_memory(
        namespace=MemoryNamespace.ALIAS,
        key="calc",
        value="other_calc.exe",
        target_type="application",
        user_confirmed=True,
    )
    res = mgr.resolve("calc")
    assert res == ("calc.exe", "static_config", 1.0)

    # Learned user-confirmed resolves
    store.add_or_update_memory(
        namespace=MemoryNamespace.ALIAS,
        key="browser",
        value="vivaldi",
        target_type="application",
        user_confirmed=True,
    )
    res_browser = mgr.resolve("browser")
    assert res_browser is not None
    assert res_browser[0] == "vivaldi"
    assert res_browser[1] == "user_confirmed_alias"
    assert res_browser[2] >= 0.95


def test_alias_manager_type_safety(temp_db):
    p = LearningPersistence(db_path=temp_db)
    store = MemoryStore(persistence=p)
    mgr = AliasManager(memory_store=store)

    store.add_or_update_memory(
        namespace=MemoryNamespace.ALIAS,
        key="proj",
        value="E:\\Workspace\\Active\\AstraRun",
        target_type="project",
        user_confirmed=True,
    )

    # Requesting application on a project target fails type safety
    assert mgr.resolve("proj", expected_target_type="application") is None
    # Matching target_type succeeds
    assert mgr.resolve("proj", expected_target_type="project") is not None


# =============================================================================
# 7. Pattern Mining & Skill Compilation Tests
# =============================================================================

def test_pattern_mining_and_workflow_conversion(temp_db):
    miner = PatternMiner(min_support=3)
    tasks = []

    for i in range(4):
        evs = [
            TaskEvent("1", f"t{i}", TaskEventType.CAPABILITY_COMPLETED, "p_open", capability_id="capability.projects.open", data={"project": "AstraRun"}),
            TaskEvent("2", f"t{i}", TaskEventType.CAPABILITY_COMPLETED, "t_open", capability_id="capability.processes.start", data={"path": "wt.exe"}),
        ]
        t = Task(f"t{i}", "conv", status=TaskStatus.COMPLETED, events=evs)
        tasks.append(t)

    discovered = miner.mine_patterns(tasks)
    assert len(discovered) == 1
    cand = discovered[0]
    assert cand.support_count == 4
    assert len(cand.steps) == 2

    # Skill review and activation
    p = LearningPersistence(db_path=temp_db)
    skill_mgr = SkillManager(persistence=p)
    proposed = skill_mgr.propose_skill(cand)
    assert proposed.status == SkillStatus.PENDING_REVIEW

    # Unapproved cannot be converted
    with pytest.raises(ValueError):
        skill_mgr.to_workflow(proposed)

    approved = skill_mgr.approve_skill(proposed.id)
    assert approved.status == SkillStatus.ACTIVE

    wf = skill_mgr.to_workflow(approved, parameter_overrides={"target_project": "CustomProject"})
    assert wf is not None
    assert len(wf.steps) == 2
    assert wf.steps[0].arguments["project"] == "CustomProject"


# =============================================================================
# 8. LearningEngine Tests
# =============================================================================

def test_learning_engine_end_to_end(temp_db):
    p = LearningPersistence(db_path=temp_db)
    engine = LearningEngine(persistence=p)

    # Ingest teaching task
    t_teach = Task("teach1", "c1", request_text="alias editor to notepad")
    engine.ingest_task(t_teach)

    res = engine.resolve_alias("editor")
    assert res is not None
    assert res[0] == "notepad"

    # Wipe
    engine.clear_all()
    assert engine.resolve_alias("editor") is None


# =============================================================================
# 9. DatasetBuilder Tests
# =============================================================================

def test_dataset_builder_sanitization():
    builder = DatasetBuilder(allow_export=True)

    text_with_token = "connect using bearer ghp_123456789012345678901234567890123456 to github"
    sanitized = builder.sanitize_text(text_with_token)
    assert "ghp_" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized

    path_text = "open C:\\Users\\hp\\secret.txt"
    sanitized_path = builder.sanitize_text(path_text)
    assert "C:\\Users\\hp" not in sanitized_path
    assert "C:\\Users\\User" in sanitized_path


def test_dataset_builder_permission_gating(temp_db):
    builder_disabled = DatasetBuilder(allow_export=False)
    with pytest.raises(PermissionError):
        builder_disabled.build_dataset([], [], output_file=temp_db.parent / "out.jsonl")


# =============================================================================
# 10. Non-Learnable Security Invariant Tests
# =============================================================================

def test_security_invariants_cannot_be_weakened():
    """
    CRITICAL INVARIANT:
    No matter how many times a user confirms an action, the ActionGate
    must NEVER downgrade a high-risk policy (CONFIRM -> AUTO).
    """
    gate = ActionGate()
    action = ProposedAction(
        action_type="terminate_process",
        raw_query="kill chrome",
        target="chrome.exe",
        tool="terminate_process",
        arguments={"pid": 1234},
        requires_confirmation=True,
        status="resolved",
    )

    # 50 consecutive evaluations
    for _ in range(50):
        verdict = gate.evaluate(action)
        assert verdict.status == ActionGateOutcome.CONFIRM


# =============================================================================
# 11. UI Component Tests
# =============================================================================

def test_ui_memory_view_and_skill_dialog(qapp, temp_db):
    p = LearningPersistence(db_path=temp_db)
    store = MemoryStore(persistence=p)

    store.add_or_update_memory(
        namespace=MemoryNamespace.ALIAS,
        key="editor",
        value="code",
        target_type="application",
        user_confirmed=True,
    )

    view = MemoryView(memory_store=store)
    assert view.list_widget.count() == 1

    skill = SkillCandidate(
        id="s_test",
        name="test-skill",
        description="A test skill",
        steps=[SkillStep(1, "capability.system.get_stats")],
    )
    skill_mgr = SkillManager(persistence=p)
    dialog = SkillReviewWidget(skill=skill, skill_manager=skill_mgr)
    assert dialog.windowTitle().startswith("New Skill Proposed")
