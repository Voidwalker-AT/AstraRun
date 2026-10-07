"""Local routing-event collector for offline benchmark evaluation.

NOTE: This collector is strictly local. AstraRun v0.2 performs NO telemetry
upload and NO cloud transmission.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrarun.core.logging import get_logger
from astrarun.telemetry.redactor import redact_sensitive_text

logger = get_logger("astrarun.telemetry")


class RoutingEventCollector:
    """Thread-safe recorder of local routing decisions for offline benchmarking."""

    def __init__(
        self,
        event_file: Path | str | None = None,
        enabled: bool = True,
        store_raw_request: bool = True,
    ):
        if event_file is None:
            from astrarun.core.paths import AstraPaths
            self.event_file = AstraPaths.data_dir() / "routing_events.jsonl"
        else:
            self.event_file = Path(event_file)
        self.enabled = enabled
        self.store_raw_request = store_raw_request
        self._lock = threading.Lock()

    def record_event(
        self,
        request: str,
        normalized_request: str,
        router: str,
        outcome: str,
        tool: str | None,
        target_id: str | None,
        confidence: float,
        latency_ms: float,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Record a single local routing event safely to disk."""
        if not self.enabled:
            return

        # Apply defensive credential redaction
        clean_req = redact_sensitive_text(request) if self.store_raw_request else None
        clean_norm = redact_sensitive_text(normalized_request) if self.store_raw_request else None

        event = {
            "schema_version": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": clean_req,
            "normalized_request": clean_norm,
            "router": router,
            "outcome": outcome,  # "resolved" or "unresolved"
            "tool": tool,
            "target_id": target_id,
            "confidence": round(confidence, 4),
            "latency_ms": round(latency_ms, 3),
        }
        if extra:
            event["extra"] = extra

        try:
            line = json.dumps(event) + "\n"
            with self._lock:
                self.event_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.event_file, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception as err:
            logger.warning("Failed appending routing event to %s: %s", self.event_file, err)
