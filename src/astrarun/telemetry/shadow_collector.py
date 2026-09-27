"""Local shadow routing event collector for Laya evaluation.

Strictly local append-only JSONL recording without network egress.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision
from astrarun.routing.laya import LayaDecision
from astrarun.telemetry.redactor import redact_sensitive_text

logger = get_logger("astrarun.telemetry.shadow")


class LayaShadowEventCollector:
    """Thread-safe recorder for Laya shadow-mode evaluations."""

    def __init__(
        self,
        event_file: Path | str = "data/laya_shadow_events.jsonl",
        enabled: bool = True,
        store_raw_request: bool = True,
    ) -> None:
        self.event_file = Path(event_file)
        self.enabled = enabled
        self.store_raw_request = store_raw_request
        self._lock = threading.Lock()

    def record_shadow_event(
        self,
        request: str,
        production_decision: Decision,
        laya_decision: LayaDecision,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Record a paired production vs. Laya shadow evaluation event."""
        if not self.enabled:
            return

        clean_req = redact_sensitive_text(request) if self.store_raw_request else None

        event: dict[str, Any] = {
            "schema_version": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": clean_req,
            "production": {
                "router": production_decision.source,
                "tool": production_decision.tool,
                "is_resolved": production_decision.is_resolved,
                "confidence": round(production_decision.confidence, 4),
                "args": production_decision.args,
            },
            "laya": {
                "intent": laya_decision.intent,
                "confidence": round(laya_decision.confidence, 4),
                "probabilities": {k: round(v, 4) for k, v in laya_decision.probabilities.items()},
                "is_executable_now": laya_decision.is_executable_now,
                "requires_resolution": laya_decision.requires_resolution,
                "latency_ms": round(laya_decision.latency_ms, 3),
                "error": laya_decision.error,
            },
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
            logger.warning("Failed appending shadow event to %s: %s", self.event_file, err)
