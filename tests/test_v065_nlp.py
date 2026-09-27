"""Comprehensive test suite for AstraRun v0.6.5 Hybrid NLP Engine.

Covers:
- Deterministic extraction: ports, PIDs, URLs, Windows paths, projects, applications
- Clause decomposition: single clause, multi-clause AND, THEN, BEFORE, AFTER
- Negation detection and scoping (0.00% leakage rate)
- Local workstation temporal understanding (yesterday, today, most_recent, etc.)
- Coreference extraction, contextual binding, and ambiguity detection
- Directed semantic relations (PROCESS LISTENS_ON PORT, PROJECT OPEN_WITH APP)
- WorkflowCompiler: capability boundary, mixed-risk, policy blocking, partial support
- Fallback mechanics and AI Bridge escalation triggers
- Zero raw shell execution invariant
"""

import pytest
from datetime import datetime, timedelta

from astrarun.core.models import ToolRisk
from astrarun.nlp.models import (
    Clause,
    ContextualReference,
    NLPEntity,
    NLPEntityType,
    OrderingRelation,
    ReasoningRequired,
    RelationType,
    StructuredUtterance,
    UserRequest,
)
from astrarun.nlp.deterministic import (
    extract_applications,
    extract_file_extensions,
    extract_percentages,
    extract_pids,
    extract_ports,
    extract_projects,
    extract_urls,
    extract_windows_paths,
)
from astrarun.nlp.temporal import extract_temporal_expressions, resolve_local_time_range
from astrarun.nlp.clause_decomposer import decompose_clauses, strip_politeness
from astrarun.nlp.negation import apply_negation_scope, verify_negation_safety
from astrarun.nlp.coreference import extract_contextual_references, resolve_coreference_with_context
from astrarun.nlp.relations import extract_relations
from astrarun.nlp.engine import NLPEngine
from astrarun.workflows.compiler import WorkflowCompiler
from astrarun.context.models import (
    DevPortInfo,
    RecentAction,
    RecentProjectRecord,
    WorkstationContext,
)


# ---------------------------------------------------------------------------
# 1. Deterministic Extraction Tests
# ---------------------------------------------------------------------------

def test_port_extraction():
    """Verify high-certainty port extraction across multiple notations."""
    cases = [
        ("inspect port 3000", 3000),
        ("what is on :5173?", 5173),
        ("check port number 8080 please", 8080),
        ("process on localhost:8000", 8000),
    ]
    for text, expected in cases:
        ports = extract_ports(text)
        assert len(ports) >= 1, f"Failed to extract port from '{text}'"
        assert ports[0].normalized == expected
        assert ports[0].type == NLPEntityType.PORT
        assert ports[0].start < ports[0].end


def test_pid_extraction():
    """Verify PID extraction with exact value normalization."""
    cases = [
        ("kill pid 14236", 14236),
        ("inspect process 9820", 9820),
        ("status of PID: 404", 404),
    ]
    for text, expected in cases:
        pids = extract_pids(text)
        assert len(pids) >= 1, f"Failed to extract PID from '{text}'"
        assert pids[0].normalized == expected
        assert pids[0].type == NLPEntityType.PROCESS


def test_url_extraction():
    """Verify extraction of HTTP/HTTPS URLs."""
    text = "open https://github.com/astral-sh/uv and check repo"
    urls = extract_urls(text)
    assert len(urls) == 1
    assert urls[0].type == NLPEntityType.URL
    assert urls[0].normalized == "https://github.com/astral-sh/uv"


def test_path_extraction():
    """Verify absolute Windows filesystem path extraction."""
    text = r"open folder E:\Workspace\Active\AstraRun for me"
    paths = extract_windows_paths(text)
    assert len(paths) == 1
    assert paths[0].type in (NLPEntityType.FOLDER, NLPEntityType.FILE)
    assert r"E:\Workspace\Active\AstraRun" in paths[0].normalized


def test_project_entity():
    """Verify known project recognition from ProjectRegistry."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="open AstraRun in vscode")
    utterance = engine.parse(req)
    proj_ents = [e for e in utterance.entities if e.type == NLPEntityType.PROJECT]
    assert len(proj_ents) == 1
    assert proj_ents[0].normalized == "astrarun"


def test_app_entity():
    """Verify known application entity recognition."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="launch terminal and open vscode")
    utterance = engine.parse(req)
    app_ents = [e for e in utterance.entities if e.type == NLPEntityType.APPLICATION]
    assert len(app_ents) == 2
    app_names = {e.normalized for e in app_ents}
    assert "terminal" in app_names
    assert "vscode" in app_names


# ---------------------------------------------------------------------------
# 2. Clause Decomposition & Ordering Tests
# ---------------------------------------------------------------------------

def test_single_clause():
    """Verify single clause decomposition and politeness stripping."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="could you please open AstraRun?")
    utterance = engine.parse(req)
    assert len(utterance.clauses) == 1
    assert utterance.clauses[0].action == "open_project"
    assert not utterance.clauses[0].negated


def test_multi_clause_and():
    """Verify multi-action decomposition on conjunction 'and'."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="open AstraRun and inspect port 3000")
    utterance = engine.parse(req)
    assert len(utterance.clauses) == 2
    assert utterance.clauses[0].action == "open_project"
    assert utterance.clauses[1].action == "inspect_port"
    assert utterance.ordering_relations[0][1] == OrderingRelation.CONJUNCTION


def test_multi_clause_then():
    """Verify sequential decomposition on 'then' / 'and then'."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="open AstraRun then open terminal")
    utterance = engine.parse(req)
    assert len(utterance.clauses) == 2
    assert utterance.ordering_relations[0][1] == OrderingRelation.THEN


def test_before_after():
    """Verify explicit ordering preservation for 'before' and 'after'."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="open vscode before opening the project folder")
    utterance = engine.parse(req)
    assert len(utterance.clauses) == 2
    assert utterance.ordering_relations[0][1] == OrderingRelation.BEFORE


# ---------------------------------------------------------------------------
# 3. Negation & Scope Safety Tests
# ---------------------------------------------------------------------------

def test_negation():
    """Verify direct negation detection on actions."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="don't open AstraRun")
    utterance = engine.parse(req)
    assert len(utterance.clauses) == 1
    assert utterance.clauses[0].negated is True
    assert utterance.clauses[0].action == "open_project"


def test_negation_scope():
    """Verify negation applies selectively to the targeted clause."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="open AstraRun but don't start the server")
    utterance = engine.parse(req)
    assert len(utterance.clauses) == 2
    assert utterance.clauses[0].negated is False
    assert utterance.clauses[1].negated is True


def test_dont_kill_just_inspect():
    """Verify prime benchmark pattern: 'don't kill node, just inspect it'."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="don't kill node, just inspect it")
    utterance = engine.parse(req)
    assert len(utterance.clauses) == 2
    # Clause 0: terminate_process -> NEGATED
    assert utterance.clauses[0].action == "terminate_process"
    assert utterance.clauses[0].negated is True
    # Clause 1: inspect -> ACTIVE
    assert utterance.clauses[1].negated is False
    # Ensure compiler never proposes termination
    compiler = WorkflowCompiler()
    proposal = compiler.compile(utterance)
    for step in proposal.steps:
        assert "terminate" not in step.tool


# ---------------------------------------------------------------------------
# 4. Temporal Understanding Tests
# ---------------------------------------------------------------------------

def test_temporal_yesterday():
    """Verify 'yesterday' resolves to local-time start and end of previous day."""
    exprs = extract_temporal_expressions("open the project I worked on yesterday")
    assert len(exprs) == 1
    assert exprs[0].value == "yesterday"
    assert exprs[0].resolved_range is not None
    start_ts, end_ts = exprs[0].resolved_range
    # Check that range duration is exactly ~24 hours
    assert 86300 <= (end_ts - start_ts) <= 86401


def test_most_recent():
    """Verify superlative modifier 'most recent' / 'latest'."""
    exprs = extract_temporal_expressions("open my most recent project")
    assert len(exprs) == 1
    assert exprs[0].value == "most_recent"
    assert exprs[0].relation == "exact"


def test_previous_project():
    """Verify 'previous project' temporal/contextual identification."""
    exprs = extract_temporal_expressions("open the previous project")
    assert len(exprs) == 1
    assert exprs[0].value == "previous"


# ---------------------------------------------------------------------------
# 5. Coreference & Context Resolution Tests
# ---------------------------------------------------------------------------

def test_coreference_detection():
    """Verify syntactic identification of anaphoric tokens."""
    refs = extract_contextual_references("what is using port 3000 and how much memory is it using?")
    assert len(refs) == 1
    assert refs[0].text == "it"


def test_context_resolution():
    """Verify binding of contextual reference using local WorkstationContext."""
    mock_context = WorkstationContext(
        recent_actions=[
            RecentAction(action_type="inspect_port", entity_id="14236", metadata={"port": 3000, "pid": 14236})
        ],
        recent_projects=[
            RecentProjectRecord(project_id="astrarun", last_interacted=1700000000.0)
        ]
    )
    ref = ContextualReference(text="it", target_type="process", start=0, end=2)
    resolved = resolve_coreference_with_context(ref, context=mock_context)
    assert resolved.resolved_value == 14236
    assert resolved.ambiguous is False


def test_ambiguous_coreference():
    """Verify ambiguous coreference sets ambiguous=True and requires clarification."""
    mock_context = WorkstationContext(
        recent_actions=[
            RecentAction(action_type="inspect_process", entity_id="1100", metadata={"pid": 1100}),
            RecentAction(action_type="inspect_process", entity_id="2200", metadata={"pid": 2200}),
        ]
    )
    ref = ContextualReference(text="it", target_type="process", start=0, end=2)
    resolved = resolve_coreference_with_context(ref, context=mock_context)
    assert resolved.ambiguous is True
    assert len(resolved.candidate_ids) == 2



# ---------------------------------------------------------------------------
# 6. Directed Relation Tests
# ---------------------------------------------------------------------------

def test_relation_process_port():
    """Verify PROCESS LISTENS_ON PORT relation extraction."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="inspect process using port 3000")
    utterance = engine.parse(req)
    listen_rels = [r for r in utterance.relations if r.type == RelationType.LISTENS_ON]
    assert len(listen_rels) >= 1
    assert "3000" in listen_rels[0].target_entity


def test_relation_project_application():
    """Verify PROJECT OPEN_WITH APPLICATION relation extraction."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="open AstraRun in vscode")
    utterance = engine.parse(req)
    open_rels = [r for r in utterance.relations if r.type == RelationType.OPEN_WITH]
    assert len(open_rels) == 1
    assert "astrarun" in open_rels[0].source_entity
    assert "vscode" in open_rels[0].target_entity


# ---------------------------------------------------------------------------
# 7. Workflow Compiler, Policy & Risk Tests
# ---------------------------------------------------------------------------

def test_workflow_compiler():
    """Verify compiler emits registered tool steps from structured utterance."""
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="open AstraRun in vscode and inspect port 3000")
    utterance = engine.parse(req)
    proposal = compiler.compile(utterance)
    assert proposal.status == "READY"
    assert len(proposal.steps) == 2
    assert proposal.steps[0].tool == "open_project_in_vscode"
    assert proposal.steps[1].tool == "inspect_port"


def test_mixed_risk_request():
    """Verify mixed-risk request adopts ToolRisk.HIGH and requires confirmation."""
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    # "open AstraRun and kill pid 9000"
    req = UserRequest(text="open AstraRun and kill pid 9000")
    utterance = engine.parse(req)
    proposal = compiler.compile(utterance)
    assert proposal.overall_risk == ToolRisk.HIGH
    assert proposal.requires_confirmation is True


def test_blocked_clause_blocks_workflow():
    """Conservative Policy Invariant: If one clause is blocked, block entire request."""
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="open AstraRun and delete system32")
    utterance = engine.parse(req)
    proposal = compiler.compile(utterance)
    assert proposal.status == "BLOCKED"
    assert len(proposal.steps) == 0
    assert len(proposal.blocked_reasons) > 0


def test_partial_support():
    """Verify request with supported + unsupported actions returns PARTIALLY_SUPPORTED."""
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="open AstraRun and deploy it to production")
    utterance = engine.parse(req)
    proposal = compiler.compile(utterance)
    assert proposal.status == "PARTIALLY_SUPPORTED"
    assert len(proposal.steps) == 1
    assert len(proposal.unsupported_clauses) >= 1


def test_unsupported_action():
    """Verify wholly unsupported action returns UNSUPPORTED without executing."""
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="make me a cup of coffee")
    utterance = engine.parse(req)
    proposal = compiler.compile(utterance)
    assert proposal.status == "UNSUPPORTED"
    assert len(proposal.steps) == 0


# ---------------------------------------------------------------------------
# 8. Fallback, Escalation & Shell Invariants
# ---------------------------------------------------------------------------

def test_nlp_failure_fallback():
    """Verify engine produces valid fallback StructuredUtterance if parsing crashes."""
    engine = NLPEngine(enable_spacy=False)
    # Simulate corrupted request
    fallback = engine._fallback_parse(UserRequest(text="open AstraRun"))
    assert isinstance(fallback, StructuredUtterance)
    assert fallback.clauses[0].source == "emergency_fallback"


def test_reasoning_required():
    """Verify complex context queries escalate to ReasoningRequired envelope."""
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="get me back to whatever I was doing before I switched over to AstraRun")
    utterance = engine.parse(req)
    escalation = engine.check_reasoning_escalation(utterance)
    assert isinstance(escalation, ReasoningRequired)
    assert escalation.reason == "complex_context_restoration"


def test_no_raw_shell():
    """Prime Security Invariant: Compiler outputs data structures, never shell strings."""
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="open AstraRun in vscode && format c:")
    utterance = engine.parse(req)
    proposal = compiler.compile(utterance)
    # The format c: command triggers hard policy block
    assert proposal.status == "BLOCKED"
    for step in proposal.steps:
        assert "format" not in str(step.arguments)
        assert "shell" not in step.tool
