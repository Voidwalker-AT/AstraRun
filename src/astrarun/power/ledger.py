"""Power Event Ledger for AstraRun 1.0.

Provides persistent, append-only auditing of Windows power transitions,
task suspensions, and wake recoveries while enforcing zero private data logging.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.power.events import PowerEvent, PowerEventType

logger = get_logger("astrarun.power.ledger")


class PowerEventLedger:
    """Persistent audit ledger for system power and task recovery events."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or (Path("data/power/power_events.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS power_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        monotonic_time REAL NOT NULL,
                        task_id TEXT,
                        details_json TEXT NOT NULL
                    )
                """)
        finally:
            conn.close()

    def record_event(
        self,
        event_type: PowerEventType,
        task_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> PowerEvent:
        """Record a structured power lifecycle event."""
        now = time.time()
        mono = time.monotonic()
        det = details or {}
        # Ensure no accidental token or private data serialization
        safe_details = {k: v for k, v in det.items() if not any(s in k.lower() for s in ("token", "key", "secret", "password"))}

        event = PowerEvent(
            event_type=event_type,
            timestamp=now,
            monotonic_time=mono,
            task_id=task_id,
            details=safe_details,
        )

        conn = sqlite3.connect(str(self.db_path))
        try:
            with conn:
                conn.execute("""
                    INSERT INTO power_events (event_type, timestamp, monotonic_time, task_id, details_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    event.event_type.value,
                    event.timestamp,
                    event.monotonic_time,
                    event.task_id,
                    json.dumps(event.details),
                ))
        except Exception as e:
            logger.error("Failed recording power event %s: %s", event_type, e)
        finally:
            conn.close()

        logger.info("[POWER_LEDGER] %s (task=%s, details=%s)", event_type.value, task_id, safe_details)
        return event

    def list_events(self, limit: int = 50) -> List[PowerEvent]:
        """Retrieve recent power events in chronological order."""
        events: List[PowerEvent] = []
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT event_type, timestamp, monotonic_time, task_id, details_json
                FROM power_events
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            for r in reversed(rows):
                try:
                    events.append(PowerEvent(
                        event_type=PowerEventType(r[0]),
                        timestamp=r[1],
                        monotonic_time=r[2],
                        task_id=r[3],
                        details=json.loads(r[4]),
                    ))
                except Exception:
                    pass
        finally:
            conn.close()
        return events
