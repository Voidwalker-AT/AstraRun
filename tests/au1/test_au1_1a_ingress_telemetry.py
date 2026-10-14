"""
AU-1.1A Ingress & Downstream Telemetry Observability Tests.

Verifies:
1. Every request emits REQUEST_INGRESS_CLASSIFIED with request_id, origin, and ingress_route.
2. Every request emits REQUEST_DOWNSTREAM_SELECTED with matching request_id and DownstreamPipeline enum.
3. Telemetry timeline links ingress classification to downstream selection causally.
"""

import pytest
from astrarun.app import AstraApplication
from astrarun.core.telemetry import CausalTelemetry, CausalEventType, DownstreamPipeline
from astrarun.ingress.models import IngressRoute, RequestEnvelope, RequestOrigin


@pytest.fixture
def astra_app():
    return AstraApplication()


def test_meta_command_telemetry(astra_app: AstraApplication):
    telem = CausalTelemetry.get_instance()
    initial_event_count = len(telem.events)

    env = RequestEnvelope.create("help", origin=RequestOrigin.CLI)
    res = astra_app.handle_request(env)
    assert res.success is True

    # Look for ingress classified and downstream selected events for this request
    classified_events = [
        e for e in telem.events[initial_event_count:]
        if e.event_type == CausalEventType.REQUEST_INGRESS_CLASSIFIED.value
        and e.data.get("request_id") == env.request_id
    ]
    assert len(classified_events) == 1
    clf = classified_events[0]
    assert clf.data["origin"] == RequestOrigin.CLI.value
    assert clf.data["ingress_route"] == IngressRoute.META_COMMAND.value
    assert clf.data["reason_code"] in ("META_HELP", "HELP")

    selected_events = [
        e for e in telem.events[initial_event_count:]
        if e.event_type == CausalEventType.REQUEST_DOWNSTREAM_SELECTED.value
        and e.data.get("request_id") == env.request_id
    ]
    assert len(selected_events) == 1
    sel = selected_events[0]
    assert sel.data["downstream_pipeline"] == DownstreamPipeline.META_HANDLER.value
    assert sel.data.get("meta_family") in ("HELP", "CAPABILITIES")


def test_operational_goal_pure_query_telemetry(astra_app: AstraApplication):
    telem = CausalTelemetry.get_instance()
    initial_event_count = len(telem.events)

    env = RequestEnvelope.create("calculate 5 * 5", origin=RequestOrigin.CLI)
    res = astra_app.handle_request(env)
    assert res.success is True

    classified_events = [
        e for e in telem.events[initial_event_count:]
        if e.event_type == CausalEventType.REQUEST_INGRESS_CLASSIFIED.value
        and e.data.get("request_id") == env.request_id
    ]
    assert len(classified_events) == 1
    assert classified_events[0].data["ingress_route"] == IngressRoute.OPERATIONAL_GOAL.value

    selected_events = [
        e for e in telem.events[initial_event_count:]
        if e.event_type == CausalEventType.REQUEST_DOWNSTREAM_SELECTED.value
        and e.data.get("request_id") == env.request_id
    ]
    assert len(selected_events) == 1
    assert selected_events[0].data["downstream_pipeline"] == DownstreamPipeline.PURE_QUERY.value


def test_fast_path_deterministic_telemetry(astra_app: AstraApplication):
    telem = CausalTelemetry.get_instance()
    initial_event_count = len(telem.events)

    env = RequestEnvelope.create("open notepad", origin=RequestOrigin.CLI, dry_run=True)
    res = astra_app.handle_request(env)
    assert res.success is True

    selected_events = [
        e for e in telem.events[initial_event_count:]
        if e.event_type == CausalEventType.REQUEST_DOWNSTREAM_SELECTED.value
        and e.data.get("request_id") == env.request_id
    ]
    assert len(selected_events) >= 1
    assert selected_events[0].data["downstream_pipeline"] == DownstreamPipeline.DETERMINISTIC_ROUTER.value
