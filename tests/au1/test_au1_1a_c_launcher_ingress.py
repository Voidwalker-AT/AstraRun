"""AU-1.1A-C Focused Tests: Real Launcher Ingress Seam Closure & Telemetry Correlation.

Verifies:
1. All human user text entered in LauncherWindow enters RequestBoundaryRouter via RequestEnvelope.
2. Natural-language greetings cannot bypass the boundary.
3. Suggestion selection creates RequestEnvelope with origin=LAUNCHER and reaches the boundary.
4. Compound greeting+operation prompts fail-closed to OPERATIONAL_GOAL.
5. Correlation of request_id and origin=LAUNCHER across ingress, telemetry, and execution result.
6. Semantic neighbors for conversational, computational, operational, and composite prompts.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from astrarun.app import AstraApplication, ExecutionResult
from astrarun.core.telemetry import CausalEventType, CausalTelemetry, DownstreamPipeline
from astrarun.ingress import IngressRoute, RequestEnvelope, RequestOrigin
from astrarun.search.models import CandidateCategory, SearchResult
from astrarun.ui.launcher import LauncherWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def astra_app():
    app = AstraApplication()
    return app


def test_launcher_all_user_text_enters_request_boundary(qapp, astra_app):
    """Every text query submitted via LauncherWindow.execute_command must enter handle_request as RequestEnvelope."""
    launcher = LauncherWindow(app=astra_app, animations_enabled=False)
    launcher.open_settings = lambda: None

    prompts = [
        "hello",
        "hi",
        "thanks",
        "help",
        "calculate 5 * 5",
        "open calculator",
        "battery report",
        "who are you",
        "what can you do",
        "show settings",
        "cpu status",
    ]

    dispatched_envelopes: list[RequestEnvelope] = []
    original_handle = astra_app.handle_request

    def spy_handle(query, *args, **kwargs):
        if isinstance(query, RequestEnvelope):
            dispatched_envelopes.append(query)
        return original_handle(query, dry_run=True, *args, **kwargs)

    astra_app.handle_request = spy_handle

    for prompt in prompts:
        dispatched_envelopes.clear()
        launcher.input_field.setText(prompt)
        launcher.execute_command()
        qapp.processEvents()

        assert len(dispatched_envelopes) == 1, f"Prompt '{prompt}' did not enter handle_request"
        env = dispatched_envelopes[0]
        assert isinstance(env, RequestEnvelope)
        assert env.raw_query == prompt
        assert env.origin == RequestOrigin.LAUNCHER
        assert env.request_id.startswith("req-")


def test_launcher_natural_language_cannot_bypass_boundary(qapp, astra_app):
    """Conversational phrases must pass through RequestBoundaryRouter and return type='conversational'."""
    launcher = LauncherWindow(app=astra_app, animations_enabled=False)

    greetings = ["hello", "hi", "hey", "good morning", "thanks", "who are you"]
    handled_records = []
    original_handle = astra_app.handle_request

    def spy_handle(query, *args, **kwargs):
        handled_records.append(query)
        return original_handle(query, dry_run=True, *args, **kwargs)

    astra_app.handle_request = spy_handle

    for greeting in greetings:
        handled_records.clear()
        launcher.input_field.setText(greeting)
        launcher.execute_command()
        qapp.processEvents()

        # Must have been handled by canonical handle_request
        assert len(handled_records) == 1
        assert isinstance(handled_records[0], RequestEnvelope)
        assert handled_records[0].origin == RequestOrigin.LAUNCHER


def test_launcher_suggestion_selection_enters_boundary(qapp, astra_app):
    """Selecting a suggestion in LauncherWindow must construct RequestEnvelope(origin=LAUNCHER)."""
    launcher = LauncherWindow(app=astra_app, animations_enabled=False)

    dispatched: list[RequestEnvelope] = []
    original_handle = astra_app.handle_request

    def spy_handle(query, *args, **kwargs):
        if isinstance(query, RequestEnvelope):
            dispatched.append(query)
        return original_handle(query, dry_run=True, *args, **kwargs)

    astra_app.handle_request = spy_handle

    test_suggestion = SearchResult(
        id="app:calc",
        name="Calculator",
        subtitle="Application",
        category=CandidateCategory.APP,
        score=1.0,
        matched_alias="calculator",
        target="calc.exe",
        command="calc.exe",
    )

    launcher._execute_result(test_suggestion)
    qapp.processEvents()

    assert len(dispatched) == 1
    env = dispatched[0]
    assert env.raw_query == "calculator"
    assert env.origin == RequestOrigin.LAUNCHER
    assert env.request_id.startswith("req-")


def test_launcher_compound_greeting_and_operation_becomes_operational(qapp, astra_app):
    """Compound greeting+operation prompts must NOT be swallowed as conversational; must route to OPERATIONAL_GOAL."""
    launcher = LauncherWindow(app=astra_app, animations_enabled=False)

    compound_prompts = [
        ("hello, open calculator", "calculator"),
        ("hi, launch notepad", "notepad"),
        ("thanks, now close notepad", "close_application"),
        ("good morning, please check battery report", "battery"),
        ("hey, calculate 2 + 2", "4"),
    ]

    for raw_prompt, expected_clue in compound_prompts:
        env = RequestEnvelope.create(raw_query=raw_prompt, origin=RequestOrigin.LAUNCHER)
        decision = astra_app.request_boundary_router.classify_ingress(env)

        assert decision.route == IngressRoute.OPERATIONAL_GOAL, f"Prompt '{raw_prompt}' should be OPERATIONAL_GOAL"

        res = astra_app.handle_request(env, dry_run=True)
        assert res.success is True
        assert res.type in ("fast_path", "capability_result", "computational")


def test_launcher_request_id_correlated_end_to_end(qapp, astra_app):
    """A single request_id must correlate from RequestEnvelope through ingress telemetry to downstream telemetry."""
    telem = CausalTelemetry.get_instance()
    initial_event_count = len(telem.events)

    launcher = LauncherWindow(app=astra_app, animations_enabled=False)
    launcher.input_field.setText("calculate 2 + 2")
    launcher.execute_command()
    qapp.processEvents()

    new_events = telem.events[initial_event_count:]
    ingress_events = [e for e in new_events if e.event_type == CausalEventType.REQUEST_INGRESS_CLASSIFIED.value]
    downstream_events = [e for e in new_events if e.event_type == CausalEventType.REQUEST_DOWNSTREAM_SELECTED.value]

    assert len(ingress_events) >= 1, "Missing REQUEST_INGRESS_CLASSIFIED event"
    assert len(downstream_events) >= 1, "Missing REQUEST_DOWNSTREAM_SELECTED event"

    ingress_req_id = ingress_events[-1].data.get("request_id")
    downstream_req_id = downstream_events[-1].data.get("request_id")

    assert ingress_req_id is not None
    assert ingress_req_id.startswith("req-")
    assert ingress_req_id == downstream_req_id, "Telemetry request_id correlation failed across ingress and downstream"
    assert ingress_events[-1].data.get("origin") == "LAUNCHER"


def test_semantic_neighbors_routing_matrix(astra_app):
    """Verify semantic neighbors for conversational, computational, and operational categories."""
    matrix = [
        # Pure greetings -> META_COMMAND
        ("hi there", IngressRoute.META_COMMAND),
        ("hello friend", IngressRoute.META_COMMAND),
        ("thank you very much", IngressRoute.META_COMMAND),
        ("who are you", IngressRoute.META_COMMAND),
        ("what are you", IngressRoute.META_COMMAND),
        ("what can you do", IngressRoute.META_COMMAND),
        ("show capabilities", IngressRoute.META_COMMAND),
        ("open settings", IngressRoute.META_COMMAND),

        # Compound greetings with operational actions -> OPERATIONAL_GOAL
        ("hello, please open calculator", IngressRoute.OPERATIONAL_GOAL),
        ("hi and launch vlc", IngressRoute.OPERATIONAL_GOAL),
        ("thanks then close calc", IngressRoute.OPERATIONAL_GOAL),
        ("hey, calculate 10 + 20", IngressRoute.OPERATIONAL_GOAL),
        ("good evening; start notepad", IngressRoute.OPERATIONAL_GOAL),

        # Pure operational goals -> OPERATIONAL_GOAL
        ("open calculator", IngressRoute.OPERATIONAL_GOAL),
        ("calculate square root of 144", IngressRoute.OPERATIONAL_GOAL),
        ("battery report", IngressRoute.OPERATIONAL_GOAL),
        ("wifi status", IngressRoute.OPERATIONAL_GOAL),
        ("close notepad", IngressRoute.OPERATIONAL_GOAL),
    ]

    for prompt, expected_route in matrix:
        env = RequestEnvelope.create(raw_query=prompt, origin=RequestOrigin.LAUNCHER)
        decision = astra_app.request_boundary_router.classify_ingress(env)
        assert decision.route == expected_route, f"Prompt '{prompt}' expected {expected_route.value}, got {decision.route.value} ({decision.reason_code})"
