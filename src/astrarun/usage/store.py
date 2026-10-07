"""Local usage signal tracker for fine-tuning candidate rankings."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.usage")


class UsageStore:
    """Persists local candidate usage statistics to slightly weight ranking."""

    def __init__(self, data_file: Path | str | None = None):
        if data_file is None:
            from astrarun.core.paths import AstraPaths
            self.data_file = AstraPaths.data_dir() / "usage.json"
        else:
            self.data_file = Path(data_file)
        self._data: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Load usage statistics from local JSON file."""
        if not self.data_file.exists():
            self._data = {}
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, dict):
                    self._data = content
        except Exception as err:
            logger.warning("Could not read usage statistics from %s: %s", self.data_file, err)
            self._data = {}

    def save(self) -> None:
        """Persist usage statistics safely to disk."""
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as err:
            logger.warning("Failed saving usage data to %s: %s", self.data_file, err)

    def record_launch(self, candidate_id: str) -> None:
        """Record an execution event for the given candidate ID."""
        if not candidate_id:
            return

        entry = self._data.setdefault(candidate_id, {"launch_count": 0, "last_launched": ""})
        entry["launch_count"] = entry.get("launch_count", 0) + 1
        entry["last_launched"] = datetime.now(timezone.utc).isoformat()
        self.save()
        logger.debug("Recorded usage launch for '%s' (total: %d)", candidate_id, entry["launch_count"])

    def get_usage(self, candidate_id: str) -> tuple[int, bool]:
        """
        Get usage count and recency indicator.
        
        Returns:
            tuple of (launch_count: int, is_recent: bool)
        """
        entry = self._data.get(candidate_id)
        if not entry:
            return 0, False

        count = int(entry.get("launch_count", 0))
        last_str = entry.get("last_launched")
        is_recent = False
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str)
                # Recent if launched within the last 7 days
                delta = datetime.now(timezone.utc) - last_dt
                if delta.total_seconds() < 7 * 86400:
                    is_recent = True
            except Exception:
                is_recent = False

        return count, is_recent
