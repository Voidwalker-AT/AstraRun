"""Tests for explicit LEGACY_FALLBACK_USED telemetry when legacy paths are exercised.

Verifies:
- Unmigrated operational goals fall back safely to legacy pipeline
- LEGACY_FALLBACK_USED telemetry event is affirmatively emitted
- Telemetry event includes request_id, reason, and legacy_pipeline
"""

import pytest

from astrarun.app import AstraApplication
from astrarun.core.telemetry import CausalEventType, CausalTelemetry
from astrarun.ingress.models import RequestEnvelope, RequestOrigin


def test_legacy_fallback_emits_telemetry():
    """Verify legacy operational goals emit structured LEGACY_FALLBACK_USED telemetry."""
    telem = CausalTelemetry.get_instance()
    initial_event_count = len(telem.events)

    app = AstraApplication()

    # Legacy command that exercises legacy pipeline (e.g. legacy system inspection or direct macro)
    env = RequestEnvelope.create("terminate process 9999", origin=RequestOrigin.CLI, dry_run=True)
    res = app.handle_request(env, dry_run=True)

    # Check telemetry for LEGACY_FALLBACK_USED event
    fallback_events = [
        e for e in telem.events[initial_event_count:]
        if e.event_type == CausalEventType.LEGACY_FALLBACK_USED.value
        and e.data.get("request_id") == env.request_id
    ]

    assert len(fallback_events) >= 1, "LEGACY_FALLBACK_USED event was not emitted for unmigrated goal"
    ev = fallback_events[0]
    assert "request_id" in ev.data
    assert "reason" in ev.data
    assert "legacy_pipeline" in ev.data
