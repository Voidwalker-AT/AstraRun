"""Workstation Context Engine for AstraRun v0.6.

Orchestrates machine and workflow state:
- Foreground window and active application
- Recent project tracking and time-decay resolution
- Listening developer ports and inspected processes
- Pronoun and contextual entity resolution with strict TTLs
- Privacy-first local atomic persistence
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.context.activity import get_foreground_window_info
from astrarun.context.models import (
    ContextReference,
    DevPortInfo,
    RecentAction,
    RecentProjectRecord,
    WorkstationContext,
)
from astrarun.context.persistence import ContextPersistenceStore
from astrarun.context.processes import get_listening_dev_ports
from astrarun.context.projects import RecentProjectsManager
from astrarun.core.logging import get_logger
from astrarun.projects.registry import ProjectRegistry

logger = get_logger("astrarun.context.engine")


class WorkstationContextEngine:
    """
    Main context coordination engine for workstation awareness.
    Provides structured, verified machine state without intrusive background tracking.
    """

    def __init__(
        self,
        persistence_file: Path | str = r"E:\Workspace\Active\AstraRun\data\context_state.json",
        project_registry: Optional[ProjectRegistry] = None,
        history_limit: int = 30,
        retention_hours: float = 48.0,
        process_ttl_seconds: float = 300.0,   # 5 minutes for ephemeral processes/ports
        project_ttl_seconds: float = 86400.0, # 24 hours for projects
    ) -> None:
        self.persistence_store = ContextPersistenceStore(
            file_path=persistence_file,
            history_limit=history_limit,
            retention_hours=retention_hours,
        )
        self.project_registry = project_registry or ProjectRegistry()
        self.project_manager = RecentProjectsManager(ttl_seconds=project_ttl_seconds)
        self.process_ttl_seconds = process_ttl_seconds
        
        self._recent_actions: list[RecentAction] = []
        self._last_inspected_process: Optional[ContextReference] = None
        self._last_inspected_port: Optional[ContextReference] = None
        
        # Load persistent state
        projects, actions = self.persistence_store.load()
        self.project_manager.load_records(projects)
        self._recent_actions = actions

    def get_snapshot(self) -> WorkstationContext:
        """Capture a live, typed snapshot of the current workstation state."""
        app_name, title, pid = get_foreground_window_info()

        # Identify active project from window title if possible
        active_proj = None
        if title:
            title_lower = title.lower()
            for p in self.project_registry.list_projects():
                if p.id in title_lower or p.name.lower() in title_lower:
                    active_proj = p.id
                    break

        dev_ports = get_listening_dev_ports()

        return WorkstationContext(
            foreground_app=app_name,
            foreground_title=title,
            foreground_pid=pid,
            active_project=active_proj,
            recent_projects=self.project_manager.get_records(),
            recent_actions=self._recent_actions[:10],
            listening_dev_ports=dev_ports,
            timestamp=time.time(),
        )

    # Aliases
    snapshot = get_snapshot
    capture_snapshot = get_snapshot

    def record_action(
        self,
        action_type: str,
        entity_id: str,
        target: str | None = None,
        success: bool = True,
        session_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> RecentAction:
        """
        Record a completed workstation action and update recency indices.
        """
        meta = metadata or {}
        action = RecentAction(
            action_type=action_type,
            entity_id=entity_id,
            target=target,
            timestamp=time.time(),
            success=success,
            session_id=session_id,
            metadata=meta,
        )
        self._recent_actions.insert(0, action)
        self._recent_actions = self._recent_actions[:self.persistence_store.history_limit]

        # Update project recency if action involves a project
        if "project" in action_type or entity_id.startswith("project:"):
            pid = entity_id.replace("project:", "")
            self.project_manager.record_interaction(pid, action=action_type)

        # Update ephemeral process/port context reference
        if action_type == "inspect_port" and meta.get("pid"):
            port_val = meta.get("port")
            pid_val = meta.get("pid")
            self._last_inspected_port = ContextReference(
                entity_id=f"port:{port_val}",
                entity_type="port",
                source="previous_inspected_port",
                confidence=1.0,
                timestamp=time.time(),
                metadata=meta,
            )
            self._last_inspected_process = ContextReference(
                entity_id=f"process:{pid_val}",
                entity_type="process",
                source="previous_inspected_port",
                confidence=1.0,
                timestamp=time.time(),
                metadata=meta,
            )
        elif action_type == "inspect_process" and meta.get("pid"):
            pid_val = meta.get("pid")
            self._last_inspected_process = ContextReference(
                entity_id=f"process:{pid_val}",
                entity_type="process",
                source="previous_inspected_process",
                confidence=1.0,
                timestamp=time.time(),
                metadata=meta,
            )

        # Persist updated state atomically
        self.persistence_store.save(
            recent_projects=self.project_manager.get_records(),
            recent_actions=self._recent_actions,
        )
        return action

    def resolve_contextual_entity(
        self,
        phrase: str,
        expected_type: Optional[str] = None,
    ) -> Optional[ContextReference]:
        """
        Attempt to resolve pronouns and relative references using structured context state.
        
        Enforces strict safety rules:
        - If query matches an attack pattern ('ignore previous context'), rejects context.
        - If reference has expired past its TTL, rejects reference.
        - If multiple matches exist and ambiguity cannot be resolved, returns None.
        """
        clean = phrase.strip().lower()

        # Context Attack Prevention (Section 45)
        attack_patterns = [
            r"\bignore\s+(?:previous\s+)?context\b",
            r"\bthe\s+previous\s+model\s+said\b",
            r"\bpretend\s+(?:port|system|policy)\b",
        ]
        for pat in attack_patterns:
            if re.search(pat, clean):
                logger.warning("Rejected context query matching attack pattern: %s", phrase)
                return None

        # 1. Project Reference Resolution
        if expected_type in (None, "project"):
            project_id = self.project_manager.resolve_reference(clean)
            if project_id:
                meta = self.project_registry.project_metadata(project_id) or {}
                return ContextReference(
                    entity_id=f"project:{project_id}",
                    entity_type="project",
                    source="recent_projects",
                    confidence=1.0,
                    timestamp=time.time(),
                    metadata=meta,
                )

        # 2. Ephemeral Process/Port Pronoun Resolution ('stop that process', 'kill it', 'terminate it')
        if expected_type in (None, "process", "port"):
            pronoun_patterns = [
                r"\b(?:stop|kill|terminate|end|shut\s+down)\s+(?:that\s+process|that|it|that\s+server)(?:\s+now)?\b",
                r"\b(?:stop|kill|terminate)\s+whatever\s+(?:is\s+on\s+that\s+port|was\s+running(?:\s+on\s+that\s+port)?)\b",
            ]
            is_pronoun_process = any(re.search(pat, clean) for pat in pronoun_patterns)
            
            if is_pronoun_process:
                # Must have a valid, recent inspection within TTL
                if self._last_inspected_process and self._last_inspected_process.is_valid(self.process_ttl_seconds):
                    return self._last_inspected_process
                else:
                    logger.info("Contextual process reference expired or not found for '%s'", phrase)
                    return None

        return None

    def get_most_recent_project_id(self) -> Optional[str]:
        """Return the most recently used project ID if within TTL."""
        rec = self.project_manager.get_most_recent_project()
        return rec.project_id if rec else None

    def get_last_action(self) -> Optional[RecentAction]:
        """Return the most recent executed action."""
        return self._recent_actions[0] if self._recent_actions else None
