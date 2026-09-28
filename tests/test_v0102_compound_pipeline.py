"""
Comprehensive automated test suite for AstraRun v0.10.2:
Capability Integration, Sequential Synchronization, Discourse Binding,
and Real Natural-Language Compound Request Execution.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from astrarun.app import AstraApplication, ExecutionResult
from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult, WindowEntity
from astrarun.core.models import Decision, RoutingContext
from astrarun.nlp.engine import NLPEngine
from astrarun.nlp.models import NLPEntityType, StructuredUtterance, UserRequest
from astrarun.routing.deterministic import DeterministicRouter, has_compound_indicators
from astrarun.tasks.models import TaskStatus
from astrarun.ui.launcher import LauncherWindow
from astrarun.workflows.compiler import WorkflowCompiler
from astrarun.workflows.context import WorkflowContext
from astrarun.workflows.models import WorkflowProposal, WorkflowStep


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def astra_app():
    return AstraApplication()


# =========================================================================
# 1. COMPOUND QUERY CLASSIFICATION & ROUTER REJECTION TESTS
# =========================================================================

def test_compound_query_indicators():
    """Verify compound queries with conjunctions and chained clauses are detected."""
    assert has_compound_indicators("open notepad and type pqr")
    assert has_compound_indicators("launch terminal and snap left")
    assert has_compound_indicators("open code then maximize window")
    assert has_compound_indicators("open notepad with title test")
    assert has_compound_indicators("open notepad ; type hello")

    # Non-compound single commands
    assert not has_compound_indicators("notepad")
    assert not has_compound_indicators("open notepad")
    assert not has_compound_indicators("launch code")
    assert not has_compound_indicators("snap window left")


def test_deterministic_router_rejects_compound_queries(astra_app):
    """Verify DeterministicRouter refuses to swallow compound multi-clause requests."""
    router = astra_app.deterministic_router
    context = astra_app.routing_context

    # Compound request must NOT resolve to a single app
    dec = router.route("open notepad and type pqr", context)
    assert not dec.is_resolved
    assert dec.tool == "unknown"

    dec2 = router.route("launch terminal and snap left", context)
    assert not dec2.is_resolved
    assert dec2.tool == "unknown"

    # Single app request DOES resolve
    dec_single = router.route("open notepad", context)
    assert dec_single.is_resolved
    assert dec_single.tool == "open_app"


# =========================================================================
# 2. SEQUENTIAL WORKFLOW COMPILATION & SYNCHRONIZATION TESTS
# =========================================================================

def test_workflow_compiler_text_entry_synchronization(astra_app):
    """
    Verify 'open notepad and type pqr' compiles into a 4-step synchronized workflow:
    1. open_application
    2. wait_for_window
    3. resolve_editable_element
    4. type_text
    """
    utterance = astra_app.nlp_engine.parse(UserRequest(text="open notepad and type pqr"))
    assert len(utterance.clauses) == 2
    assert utterance.clauses[0].action == "open_app"
    assert utterance.clauses[1].action == "type_text"

    proposal = astra_app.workflow_compiler.compile(utterance)
    assert proposal.status == "READY"
    assert len(proposal.steps) == 4

    # Step 1: Open app
    assert proposal.steps[0].tool == "open_application"
    assert proposal.steps[0].arguments["app"] == "notepad"

    # Step 2: Window synchronization
    assert proposal.steps[1].tool == "wait_for_window"
    assert proposal.steps[1].arguments["app"] == "notepad"

    # Step 3: Editable element resolution
    assert proposal.steps[2].tool == "resolve_editable_element"
    assert proposal.steps[2].arguments["window"] == "notepad"

    # Step 4: Text entry
    assert proposal.steps[3].tool == "type_text"
    assert proposal.steps[3].arguments["text"] == "pqr"


def test_workflow_compiler_window_action_synchronization(astra_app):
    """
    Verify 'open notepad and maximize window' compiles into a 3-step synchronized workflow:
    1. open_application
    2. wait_for_window
    3. maximize_window
    """
    utterance = astra_app.nlp_engine.parse(UserRequest(text="open notepad and maximize window"))
    proposal = astra_app.workflow_compiler.compile(utterance)
    assert proposal.status == "READY"
    assert len(proposal.steps) == 3

    assert proposal.steps[0].tool == "open_application"
    assert proposal.steps[0].arguments["app"] == "notepad"
    assert proposal.steps[1].tool == "wait_for_window"
    assert proposal.steps[1].arguments["app"] == "notepad"
    assert proposal.steps[2].tool == "maximize_window"


def test_workflow_compiler_snap_synchronization(astra_app):
    """
    Verify 'open terminal and snap left' compiles into a 3-step synchronized workflow:
    1. open_application
    2. wait_for_window
    3. snap_window_left
    """
    utterance = astra_app.nlp_engine.parse(UserRequest(text="open terminal and snap left"))
    proposal = astra_app.workflow_compiler.compile(utterance)
    assert proposal.status == "READY"
    assert len(proposal.steps) == 3

    assert proposal.steps[0].tool == "open_application"
    assert proposal.steps[1].tool == "wait_for_window"
    assert proposal.steps[2].tool == "snap_window_left"


# =========================================================================
# 3. WORKFLOW CONTEXT & DISCOURSE BINDING TESTS
# =========================================================================

def test_workflow_context_binding():
    """Verify WorkflowContext correctly binds preceding step outputs into subsequent steps."""
    wf_ctx = WorkflowContext()

    step_open = WorkflowStep(step_id="s1", name="Open", tool="open_application", arguments={"app": "notepad"})
    res_open = CapabilityResult.ok("open_application", "Opened", data={"app": "notepad"})
    wf_ctx.record_step_result(step_open, res_open)
    assert wf_ctx.last_opened_application == "notepad"

    step_wait = WorkflowStep(step_id="s2", name="Wait", tool="wait_for_window", arguments={})
    wf_ctx.bind_step_arguments(step_wait)
    assert step_wait.arguments.get("app") == "notepad"

    res_wait = CapabilityResult.ok("wait_for_window", "Ready", data={"hwnd": 2048, "title": "Untitled - Notepad"})
    wf_ctx.record_step_result(step_wait, res_wait)
    assert wf_ctx.last_resolved_ui_root == 2048
    assert wf_ctx.last_opened_window is not None
    assert wf_ctx.last_opened_window.hwnd == 2048

    step_resolve = WorkflowStep(step_id="s3", name="Resolve", tool="resolve_editable_element", arguments={})
    wf_ctx.bind_step_arguments(step_resolve)
    assert step_resolve.arguments.get("hwnd") == 2048

    res_resolve = CapabilityResult.ok("resolve_editable_element", "Found", data={"element": {"name": "Editor", "type": "Document"}, "hwnd": 2048})
    wf_ctx.record_step_result(step_resolve, res_resolve)
    assert wf_ctx.last_ui_element is not None

    step_type = WorkflowStep(step_id="s4", name="Type", tool="type_text", arguments={"text": "pqr"})
    wf_ctx.bind_step_arguments(step_type)
    assert isinstance(step_type.arguments.get("target_element"), dict)
    assert step_type.arguments.get("target_element")["name"] == "Editor"


# =========================================================================
# 4. CANONICAL APP PIPELINE DRY RUN & PARTIAL EXECUTION TESTS
# =========================================================================

def test_handle_request_compound_dry_run(astra_app):
    """Verify full end-to-end handle_request execution for 'open notepad and type pqr' with dry_run."""
    exec_res = astra_app.handle_request("open notepad and type pqr", dry_run=True)
    assert exec_res.success
    assert exec_res.task is not None
    assert exec_res.task.status == TaskStatus.COMPLETED
    assert "Workflow executed 4 step(s)" in exec_res.message
    assert "Entered 3 characters." in exec_res.message

    # Verify task data contains all 4 step outputs
    steps_data = exec_res.data.get("steps", [])
    assert len(steps_data) == 4
    assert steps_data[0]["capability"] == "open_application"
    assert steps_data[1]["capability"] == "wait_for_window"
    assert steps_data[2]["capability"] == "resolve_editable_element"
    assert steps_data[3]["capability"] == "type_text"


def test_handle_request_partial_failure(astra_app, monkeypatch):
    """
    Verify that if step 1 succeeds but step 2 fails, the task transitions to
    PARTIALLY_COMPLETED rather than false-positive completed or silent drop.
    """
    call_count = 0

    def mock_execute_capability(task_id, capability_id, arguments, registry):
        nonlocal call_count
        call_count += 1
        if capability_id == "open_application":
            return CapabilityResult.ok("open_application", "Opened Notepad", data={"app": "notepad"})
        elif capability_id == "wait_for_window":
            return CapabilityResult.fail("wait_for_window", "Timed out waiting for Notepad window.", error_code=CapabilityErrorCode.TIMEOUT)
        return CapabilityResult.fail(capability_id, "Should not be reached")

    monkeypatch.setattr(astra_app.task_manager, "execute_capability", mock_execute_capability)

    exec_res = astra_app.handle_request("open notepad and type pqr")
    assert not exec_res.success
    assert exec_res.task is not None
    assert exec_res.task.status == TaskStatus.PARTIALLY_COMPLETED
    assert "Workflow partially completed" in exec_res.message
    assert "1/4 steps succeeded" in exec_res.message


# =========================================================================
# 5. LAUNCHER SUGGESTION BYPASS & FOCUS SAFETY TESTS
# =========================================================================

def test_launcher_bypasses_suggestions_on_compound(qapp, astra_app):
    """
    CRITICAL PRODUCT TEST:
    Verify that typing 'open notepad and type pqr' into LauncherWindow
    does NOT get hijacked by the 'notepad' search suggestion when hitting Enter.
    """
    launcher = LauncherWindow(app=astra_app, animations_enabled=False)
    launcher.input_field.setText("open notepad and type pqr")

    # In v0.10.2, compound queries automatically hide suggestions list
    assert launcher._is_compound_or_nlp_query("open notepad and type pqr")
    assert not launcher.suggestions_list.isVisible()

    # Track requests handled by app
    handled_queries = []
    original_handle = astra_app.handle_request

    def spy_handle(query, *args, **kwargs):
        handled_queries.append(query)
        return original_handle(query, dry_run=True, *args, **kwargs)

    astra_app.handle_request = spy_handle

    # Press Enter
    launcher.execute_command()
    qapp.processEvents()

    # Must have dispatched full compound command, NOT "notepad"!
    assert len(handled_queries) == 1
    assert handled_queries[0] == "open notepad and type pqr"

    launcher.dismiss()


def test_type_literal_text_focus_safety():
    """Verify type_literal_text fails safely when window does not exist or focus cannot be confirmed."""
    from astrarun.interaction.service import type_literal_text

    # Invalid HWND
    res = type_literal_text("hello", hwnd=99999999)
    assert not res.success
    assert res.error_code in (CapabilityErrorCode.NOT_FOUND, CapabilityErrorCode.FOCUS_FAILED)
    assert "not found" in res.message.lower() or "focus" in res.message.lower() or "invalid" in res.message.lower()
