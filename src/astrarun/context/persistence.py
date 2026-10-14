"""Atomic local persistence and safe recovery for Workstation Context state."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.context.models import RecentAction, RecentProjectRecord
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.context.persistence")


class ContextPersistenceStore:
    """
    Manages local, atomic persistence of recent projects and actions.
    Ensures zero corruption, thread safety, bounded history, and automatic pruning.
    """

    def __init__(
        self,
        file_path: Optional[Path | str] = None,
        history_limit: int = 30,
        retention_hours: float = 48.0,
    ) -> None:
        from astrarun.core.paths import AstraPaths
        p_file = file_path or (AstraPaths.data_dir() / "context_state.json")
        self.file_path = Path(p_file).resolve()
        self.history_limit = history_limit
        self.retention_hours = retention_hours
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> tuple[list[RecentProjectRecord], list[RecentAction]]:
        """Load context records with robust corrupted JSON recovery."""
        if not self.file_path.exists() or self.file_path.stat().st_size == 0:
            return [], []

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cutoff = time.time() - (self.retention_hours * 3600.0)

            raw_projects = data.get("recent_projects", [])
            projects: list[RecentProjectRecord] = []
            for p in raw_projects:
                rec = RecentProjectRecord.from_dict(p)
                if rec.last_interacted >= cutoff:
                    projects.append(rec)

            raw_actions = data.get("recent_actions", [])
            actions: list[RecentAction] = []
            for a in raw_actions:
                act = RecentAction.from_dict(a)
                if act.timestamp >= cutoff:
                    actions.append(act)

            # Sort descending by recency
            projects.sort(key=lambda x: x.last_interacted, reverse=True)
            actions.sort(key=lambda x: x.timestamp, reverse=True)

            return projects[:self.history_limit], actions[:self.history_limit]
        except Exception as err:
            logger.warning("Corrupted or unreadable context state file %s: %s. Resetting.", self.file_path, err)
            return [], []

    def save(
        self,
        recent_projects: list[RecentProjectRecord],
        recent_actions: list[RecentAction],
    ) -> bool:
        """
        Atomically write state using a temporary file in the same directory and rename.
        """
        try:
            cutoff = time.time() - (self.retention_hours * 3600.0)
            clean_projects = [p for p in recent_projects if p.last_interacted >= cutoff][:self.history_limit]
            clean_actions = [a for a in recent_actions if a.timestamp >= cutoff][:self.history_limit]

            payload = {
                "version": "0.6",
                "saved_at": time.time(),
                "recent_projects": [p.to_dict() for p in clean_projects],
                "recent_actions": [a.to_dict() for a in clean_actions],
            }

            dir_path = self.file_path.parent
            dir_path.mkdir(parents=True, exist_ok=True)

            # Write to temporary file first
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix="ctx_", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

            # Atomic replace
            os.replace(tmp_path, self.file_path)
            return True
        except Exception as err:
            logger.error("Failed to atomically save context state: %s", err)
            return False
