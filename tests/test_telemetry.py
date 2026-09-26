"""Unit tests for local routing telemetry and redaction."""

import json
from pathlib import Path
from astrarun.telemetry.collector import RoutingEventCollector
from astrarun.telemetry.redactor import redact_sensitive_text


def test_redact_sensitive_text():
    # OpenAI / Anthropic key
    t1 = "open my key sk-abc12345678901234567890"
    r1 = redact_sensitive_text(t1)
    assert "sk-" not in r1
    assert "[REDACTED_API_KEY]" in r1

    # Bearer token
    t2 = "connect Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    r2 = redact_sensitive_text(t2)
    assert "eyJhbGci" not in r2
    assert "Bearer [REDACTED_TOKEN]" in r2

    # Password parameter
    t3 = "start server password=supersecretpass123"
    r3 = redact_sensitive_text(t3)
    assert "supersecretpass123" not in r3
    assert "password=[REDACTED]" in r3


def test_telemetry_collector_logging(tmp_path: Path):
    event_file = tmp_path / "routing_events.jsonl"
    collector = RoutingEventCollector(event_file=event_file, enabled=True, store_raw_request=True)

    collector.record_event(
        request="open notepad",
        normalized_request="notepad",
        router="deterministic",
        outcome="resolved",
        tool="open_app",
        target_id="app:notepad",
        confidence=1.0,
        latency_ms=0.25,
    )

    assert event_file.exists()
    lines = event_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["request"] == "open notepad"
    assert data["outcome"] == "resolved"
    assert data["tool"] == "open_app"
    assert data["target_id"] == "app:notepad"


def test_telemetry_disabled(tmp_path: Path):
    event_file = tmp_path / "disabled_events.jsonl"
    collector = RoutingEventCollector(event_file=event_file, enabled=False)

    collector.record_event(
        request="open calc",
        normalized_request="calc",
        router="deterministic",
        outcome="resolved",
        tool="open_app",
        target_id="app:calc",
        confidence=1.0,
        latency_ms=0.10,
    )

    assert not event_file.exists()


def test_telemetry_no_raw_request(tmp_path: Path):
    event_file = tmp_path / "noraw_events.jsonl"
    collector = RoutingEventCollector(event_file=event_file, enabled=True, store_raw_request=False)

    collector.record_event(
        request="open private_doc.pdf",
        normalized_request="private_doc.pdf",
        router="deterministic",
        outcome="resolved",
        tool="open_file",
        target_id="file:private",
        confidence=1.0,
        latency_ms=0.15,
    )

    lines = event_file.read_text(encoding="utf-8").strip().splitlines()
    data = json.loads(lines[0])
    assert data["request"] is None
    assert data["normalized_request"] is None
    assert data["outcome"] == "resolved"
