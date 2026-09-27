"""Project context tracking and resolution of recent project references."""

from __future__ import annotations

import re
import time
from typing import List, Optional

from astrarun.context.models import RecentProjectRecord
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.context.projects")


class RecentProjectsManager:
    """Manages ordered recency, frequency, and time-decay of project interactions."""

    def __init__(self, ttl_seconds: float = 86400.0) -> None:  # Default 24 hours
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, RecentProjectRecord] = {}

    def load_records(self, records: list[RecentProjectRecord]) -> None:
        """Initialize from persistent records."""
        self._records.clear()
        for r in records:
            self._records[r.project_id] = r

    def get_records(self) -> list[RecentProjectRecord]:
        """Return all project records sorted by last interacted descending."""
        sorted_records = sorted(self._records.values(), key=lambda x: x.last_interacted, reverse=True)
        return sorted_records

    def record_interaction(self, project_id: str, action: str = "open_project") -> RecentProjectRecord:
        """Log an interaction with a project."""
        now = time.time()
        if project_id in self._records:
            rec = self._records[project_id]
            rec.last_interacted = now
            rec.interaction_count += 1
            rec.last_action = action
        else:
            rec = RecentProjectRecord(
                project_id=project_id,
                first_seen=now,
                last_interacted=now,
                interaction_count=1,
                last_action=action,
            )
            self._records[project_id] = rec
        return rec

    def get_most_recent_project(self, max_age_seconds: Optional[float] = None) -> Optional[RecentProjectRecord]:
        """Return the most recently interacted project if within validity TTL."""
        records = self.get_records()
        if not records:
            return None
        
        top = records[0]
        max_age = max_age_seconds if max_age_seconds is not None else self.ttl_seconds
        if (time.time() - top.last_interacted) <= max_age:
            return top
        return None

    def resolve_reference(self, phrase: str) -> Optional[str]:
        """
        Check if phrase is an explicit or pronoun reference to a recent project.
        Examples:
          'my most recent project' -> project_id
          'the last project' -> project_id
          'latest project' -> project_id
          'open that project again' -> project_id
          'continue working on my project' -> project_id (if unambiguous)
        """
        clean = phrase.strip().lower()
        
        # Phrases indicating the most recent project
        recent_patterns = [
            r"\b(?:(?:most\s+)?recent|last|latest|previous)\s+project\b",
            r"\bproject\s+i\s+(?:used|opened|worked\s+on)\s+most\s+recently\b",
            r"\b(?:open\s+)?that\s+project\b",
            r"\bproject\s+from\s+earlier\b",
            r"\bcontinue\s+(?:working\s+on\s+)?my\s+project\b",
            r"\bcontinue\s+what\s+i\s+was\s+doing\b",
        ]
        
        for pat in recent_patterns:
            if re.search(pat, clean):
                most_recent = self.get_most_recent_project()
                if most_recent:
                    return most_recent.project_id
                return None

        return None
