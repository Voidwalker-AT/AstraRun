"""
AU-1.1A Request Boundary Router Tests.

Tests the two-route ingress classifier:
- META_COMMAND: strictly static panels, help, greetings, acknowledgements, empty input.
- OPERATIONAL_GOAL: any workstation action, query, compound instruction, or unknown input.
"""

import pytest
from astrarun.ingress.models import IngressRoute, RequestEnvelope, RequestOrigin
from astrarun.ingress.request_boundary import RequestBoundaryRouter


@pytest.fixture
def boundary_router() -> RequestBoundaryRouter:
    return RequestBoundaryRouter()


def test_empty_and_whitespace_classification(boundary_router: RequestBoundaryRouter):
    decision_empty = boundary_router.classify("")
    assert decision_empty.route == IngressRoute.META_COMMAND
    assert decision_empty.meta_family == "EMPTY_INPUT"
    assert decision_empty.reason_code == "EMPTY_INPUT"

    decision_ws = boundary_router.classify("   \t\n  ")
    assert decision_ws.route == IngressRoute.META_COMMAND
    assert decision_ws.meta_family == "EMPTY_INPUT"


def test_meta_command_families(boundary_router: RequestBoundaryRouter):
    meta_cases = [
        ("help", "HELP"),
        ("what can you do", "HELP"),
        ("capabilities", "HELP"),
        ("commands", "HELP"),
        ("history", "HISTORY_PANEL"),
        ("open history", "HISTORY_PANEL"),
        ("show history", "HISTORY_PANEL"),
        ("memory", "MEMORY_PANEL"),
        ("show memory", "MEMORY_PANEL"),
        ("learned aliases", "MEMORY_PANEL"),
        ("skills", "SKILLS_PANEL"),
        ("show skills", "SKILLS_PANEL"),
        ("settings", "SETTINGS_PANEL"),
        ("preferences", "SETTINGS_PANEL"),
        ("config", "SETTINGS_PANEL"),
        ("diagnostics", "DIAGNOSTICS_PANEL"),
        ("system diagnostics", "DIAGNOSTICS_PANEL"),
        ("hotkey", "HOTKEY_STATUS"),
        ("hotkey status", "HOTKEY_STATUS"),
        ("hello", "EXACT_GREETING"),
        ("hi", "EXACT_GREETING"),
        ("thanks", "EXACT_ACKNOWLEDGEMENT"),
        ("thank you", "EXACT_ACKNOWLEDGEMENT"),
    ]
    for query, expected_family in meta_cases:
        dec = boundary_router.classify(query)
        assert dec.route == IngressRoute.META_COMMAND, f"Query '{query}' did not classify as META_COMMAND"
        assert dec.meta_family == expected_family, f"Query '{query}' expected family {expected_family}, got {dec.meta_family}"


def test_meta_command_case_and_punctuation_insensitivity(boundary_router: RequestBoundaryRouter):
    punct_cases = [
        "Help?",
        "HELP!",
        "capabilities...",
        "Settings?",
        "hello!",
        "Thanks.",
    ]
    for query in punct_cases:
        dec = boundary_router.classify(query)
        assert dec.route == IngressRoute.META_COMMAND, f"Query '{query}' failed punctuation strip check"


def test_composite_queries_fail_closed_to_operational_goal(boundary_router: RequestBoundaryRouter):
    composite_cases = [
        "help and open notepad",
        "show diagnostics then delete file",
        "hello; open calculator",
        "settings & list files",
        "help, close chrome",
        "open calculator and help",
    ]
    for query in composite_cases:
        dec = boundary_router.classify(query)
        assert dec.route == IngressRoute.OPERATIONAL_GOAL, f"Composite query '{query}' was not routed to OPERATIONAL_GOAL"
        assert dec.reason_code == "COMPOSITE_CONTAINS_OPERATIONAL_CLAUSE"


def test_operational_goals_classification(boundary_router: RequestBoundaryRouter):
    operational_cases = [
        "open notepad",
        "launch calculator",
        "close chrome",
        "calculate 2 + 2",
        "what is 10 * 5",
        "count to 10",
        "battery report",
        "is notepad running",
        "cpu status",
        "memory status",
        "undo last window move",
        "click submit",
        "type hello into search",
        "inspect ui",
        "move window to left",
        "snap window right",
        "unknown gibberish query that is not meta",
    ]
    for query in operational_cases:
        dec = boundary_router.classify(query)
        assert dec.route == IngressRoute.OPERATIONAL_GOAL, f"Operational query '{query}' failed to classify as OPERATIONAL_GOAL"


def test_envelope_origin_preservation(boundary_router: RequestBoundaryRouter):
    envelope = RequestEnvelope.create(
        raw_query="open calc",
        origin=RequestOrigin.CLI,
        dry_run=True,
    )
    assert envelope.origin == RequestOrigin.CLI
    assert envelope.dry_run is True
    dec = boundary_router.classify(envelope)
    assert dec.route == IngressRoute.OPERATIONAL_GOAL
