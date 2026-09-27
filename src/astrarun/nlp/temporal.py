"""Local workstation temporal engine.

Extracts and resolves temporal expressions into canonical local-time
timestamp ranges (start_timestamp, end_timestamp) in the host machine's timezone.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any
from astrarun.nlp.models import TemporalExpression

# Precompiled patterns for workstation temporal expressions
_PATTERNS: list[tuple[str, str, str]] = [
    # (regex_pattern, canonical_value, default_relation)
    (r'(?i)\byesterday(?:\s+(?:morning|afternoon|evening))?\b', "yesterday", "during"),
    (r'(?i)\blast\s+night\b', "last_night", "during"),
    (r'(?i)\btoday(?:\s+(?:morning|afternoon|evening))?\b', "today", "during"),
    (r'(?i)\bearlier\s+today\b', "today", "during"),
    (r'(?i)\bjust\s+now\b|\ba\s+moment\s+ago\b|\bright\s+now\b', "just_now", "during"),
    (r'(?i)\bmost\s+recent(?:ly)?\b', "most_recent", "exact"),
    (r'(?i)\blatest\b', "most_recent", "exact"),
    (r'(?i)\bnewest\b', "most_recent", "exact"),
    (r'(?i)\blast\s+(?:project|session|action|window|process)\b', "most_recent", "exact"),
    (r'(?i)\bprevious\s+(?:project|session|action|window|process)\b', "previous", "exact"),
    (r'(?i)\brecent(?:ly)?\b', "recent", "during"),
    (r'(?i)\bbefore\b', "before", "before"),
    (r'(?i)\bafter\b', "after", "after"),
]


def resolve_local_time_range(
    value: str,
    now: datetime | None = None
) -> tuple[float, float] | None:
    """Calculate the [start_ts, end_ts] timestamp bounds in local workstation time."""
    current = now or datetime.now().astimezone()
    tz = current.tzinfo
    today_date = current.date()

    if value == "today":
        start_dt = datetime.combine(today_date, time.min, tzinfo=tz)
        end_dt = datetime.combine(today_date, time.max, tzinfo=tz)
        return (start_dt.timestamp(), end_dt.timestamp())

    elif value == "yesterday":
        yesterday_date = today_date - timedelta(days=1)
        start_dt = datetime.combine(yesterday_date, time.min, tzinfo=tz)
        end_dt = datetime.combine(yesterday_date, time.max, tzinfo=tz)
        return (start_dt.timestamp(), end_dt.timestamp())

    elif value == "last_night":
        yesterday_date = today_date - timedelta(days=1)
        start_dt = datetime.combine(yesterday_date, time(18, 0), tzinfo=tz)
        end_dt = datetime.combine(today_date, time(6, 0), tzinfo=tz)
        return (start_dt.timestamp(), end_dt.timestamp())

    elif value == "just_now":
        start_dt = current - timedelta(minutes=15)
        return (start_dt.timestamp(), current.timestamp())

    elif value == "recent":
        start_dt = current - timedelta(hours=4)
        return (start_dt.timestamp(), current.timestamp())

    elif value in ("most_recent", "previous"):
        # Relative superlative: point in time representing the immediate predecessor
        return (0.0, current.timestamp())

    return None


def extract_temporal_expressions(
    text: str,
    now: datetime | None = None
) -> list[TemporalExpression]:
    """Extract all temporal expressions from text with local timestamp bounds."""
    expressions: list[TemporalExpression] = []
    occupied_spans: list[tuple[int, int]] = []

    for pattern_str, canonical_val, default_rel in _PATTERNS:
        for m in re.finditer(pattern_str, text):
            s, e = m.start(), m.end()
            if any(occ_s <= s and e <= occ_e for occ_s, occ_e in occupied_spans):
                continue
            
            time_range = resolve_local_time_range(canonical_val, now=now)
            expressions.append(TemporalExpression(
                text=m.group(0),
                relation=default_rel,
                value=canonical_val,
                resolved_range=time_range,
                start=s,
                end=e,
                source="workstation_temporal",
            ))
            occupied_spans.append((s, e))

    expressions.sort(key=lambda t: t.start)
    return expressions
