"""Workstation Context Engine for AstraRun v0.7.

Orchestrates machine and workflow state:
- Foreground window and active application
- Recent project tracking and time-decay resolution
- Recent file, application, process, and port tracking
- ContextEvent model with strict source trust levels
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
    ContextEvent,
    ContextReference,
    ContextTrustLevel,
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
        persistence_file: Optional[Path | str] = None,
        project_registry: Optional[ProjectRegistry] = None,
        history_limit: int = 30,
        retention_hours: float = 48.0,
        process_ttl_seconds: float = 300.0,   # 5 minutes for ephemeral processes/ports/files
        project_ttl_seconds: float = 86400.0, # 24 hours for projects
    ) -> None:
        from astrarun.core.paths import AstraPaths
        p_file = persistence_file or (AstraPaths.data_dir() / "context_state.json")
        self.persistence_store = ContextPersistenceStore(
            file_path=p_file,
            history_limit=history_limit,
            retention_hours=retention_hours,
        )
        self.project_registry = project_registry or ProjectRegistry()
        self.project_manager = RecentProjectsManager(ttl_seconds=project_ttl_seconds)
        self.process_ttl_seconds = process_ttl_seconds
        
        self._recent_actions: list[RecentAction] = []
        self._recent_events: list[ContextEvent] = []
        self._recent_files: list[str] = []
        self._recent_apps: list[str] = []
        self._recent_processes: list[int] = []
        self._recent_ports: list[int] = []

        self._last_inspected_process: Optional[ContextReference] = None
        self._last_inspected_port: Optional[ContextReference] = None
        self._last_file_ref: Optional[ContextReference] = None
        
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
            foreground_window=None,
            active_project=active_proj,
            recent_projects=self.project_manager.get_records(),
            recent_actions=self._recent_actions[:10],
            recent_apps=self._recent_apps[:5],
            recent_files=self._recent_files[:5],
            recent_processes=self._recent_processes[:5],
            recent_ports=self._recent_ports[:5],
            recent_events=self._recent_events[:10],
            listening_dev_ports=dev_ports,
            timestamp=time.time(),
        )

    # Aliases
    snapshot = get_snapshot
    capture_snapshot = get_snapshot

    def record_event(
        self,
        event_type: str,
        entity_id: str,
        source: str = "astrarun",
        trust_level: ContextTrustLevel = ContextTrustLevel.VERIFIED_ACTION,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ContextEvent:
        """Record a structured context event with verified trust level."""
        event = ContextEvent(
            type=event_type,
            entity_id=entity_id,
            timestamp=time.time(),
            source=source,
            trust_level=trust_level,
            metadata=metadata or {},
        )
        self._recent_events.insert(0, event)
        self._recent_events = self._recent_events[:self.persistence_store.history_limit]
        return event

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
        now = time.time()
        action = RecentAction(
            action_type=action_type,
            entity_id=entity_id,
            target=target,
            timestamp=now,
            success=success,
            session_id=session_id,
            metadata=meta,
        )
        self._recent_actions.insert(0, action)
        self._recent_actions = self._recent_actions[:self.persistence_store.history_limit]

        # Record corresponding trusted ContextEvent
        self.record_event(
            event_type=action_type,
            entity_id=entity_id,
            source="astrarun",
            trust_level=ContextTrustLevel.VERIFIED_ACTION,
            metadata=meta,
        )

        # Update project recency if action involves a project
        if "project" in action_type or entity_id.startswith("project:"):
            pid = entity_id.replace("project:", "")
            self.project_manager.record_interaction(pid, action=action_type)

        # Update file recency
        if action_type in ("open_file", "reveal_file") or entity_id.startswith("file:"):
            fpath = target or meta.get("path") or entity_id.replace("file:", "")
            if fpath:
                if fpath in self._recent_files:
                    self._recent_files.remove(fpath)
                self._recent_files.insert(0, fpath)
                self._last_file_ref = ContextReference(
                    entity_id=f"file:{fpath}",
                    entity_type="file",
                    source="previous_file_action",
                    confidence=1.0,
                    timestamp=now,
                    metadata={"path": fpath},
                    trust_level=ContextTrustLevel.VERIFIED_ACTION,
                )

        # Update application recency
        if "application" in action_type or "app" in action_type:
            app_name = meta.get("app") or target or entity_id.replace("app:", "")
            if app_name:
                if app_name in self._recent_apps:
                    self._recent_apps.remove(app_name)
                self._recent_apps.insert(0, app_name)

        # Update ephemeral process/port context reference
        if action_type == "inspect_port" and meta.get("pid"):
            port_val = meta.get("port")
            pid_val = meta.get("pid")
            if port_val and port_val not in self._recent_ports:
                self._recent_ports.insert(0, int(port_val))
            if pid_val and pid_val not in self._recent_processes:
                self._recent_processes.insert(0, int(pid_val))

            self._last_inspected_port = ContextReference(
                entity_id=f"port:{port_val}",
                entity_type="port",
                source="previous_inspected_port",
                confidence=1.0,
                timestamp=now,
                metadata=meta,
                trust_level=ContextTrustLevel.VERIFIED_ACTION,
            )
            self._last_inspected_process = ContextReference(
                entity_id=f"process:{pid_val}",
                entity_type="process",
                source="previous_inspected_port",
                confidence=1.0,
                timestamp=now,
                metadata=meta,
                trust_level=ContextTrustLevel.VERIFIED_ACTION,
            )
        elif action_type == "inspect_process" and meta.get("pid"):
            pid_val = meta.get("pid")
            if pid_val and pid_val not in self._recent_processes:
                self._recent_processes.insert(0, int(pid_val))

            self._last_inspected_process = ContextReference(
                entity_id=f"process:{pid_val}",
                entity_type="process",
                source="previous_inspected_process",
                confidence=1.0,
                timestamp=now,
                metadata=meta,
                trust_level=ContextTrustLevel.VERIFIED_ACTION,
            )

        # Persist updated state atomically
        self.persistence_store.save(
            recent_projects=self.project_manager.get_records(),
            recent_actions=self._recent_actions,
        )
        return action

    # -------------------------------------------------------------
    # Clean Context Query APIs
    # -------------------------------------------------------------
    def last_project(self) -> Optional[str]:
        """Return the most recently interacted project ID if within TTL."""
        rec = self.project_manager.get_most_recent_project()
        return rec.project_id if rec else None

    def last_file(self) -> Optional[str]:
        """Return the most recently referenced file path if within TTL."""
        if self._last_file_ref and self._last_file_ref.is_valid(self.process_ttl_seconds):
            return self._last_file_ref.metadata.get("path")
        return self._recent_files[0] if self._recent_files else None

    def last_process(self) -> Optional[int]:
        """Return the most recently inspected process PID if within TTL."""
        if self._last_inspected_process and self._last_inspected_process.is_valid(self.process_ttl_seconds):
            try:
                return int(self._last_inspected_process.entity_id.replace("process:", ""))
            except ValueError:
                pass
        return self._recent_processes[0] if self._recent_processes else None

    def last_port(self) -> Optional[int]:
        """Return the most recently inspected port number if within TTL."""
        if self._last_inspected_port and self._last_inspected_port.is_valid(self.process_ttl_seconds):
            try:
                return int(self._last_inspected_port.entity_id.replace("port:", ""))
            except ValueError:
                pass
        return self._recent_ports[0] if self._recent_ports else None

    def recent_apps(self, limit: int = 5) -> list[str]:
        """Return recent application names."""
        return self._recent_apps[:limit]

    def recent_files(self, limit: int = 5) -> list[str]:
        """Return recent file paths."""
        return self._recent_files[:limit]

    def recent_projects(self, limit: int = 5) -> list[str]:
        """Return recent project IDs."""
        return [p.project_id for p in self.project_manager.get_records()[:limit]]

    def recent_processes(self, limit: int = 5) -> list[int]:
        """Return recent process PIDs."""
        return self._recent_processes[:limit]

    def recent_ports(self, limit: int = 5) -> list[int]:
        """Return recent port numbers."""
        return self._recent_ports[:limit]

    def get_most_recent_project_id(self) -> Optional[str]:
        """Legacy helper alias."""
        return self.last_project()

    def get_last_action(self) -> Optional[RecentAction]:
        """Return the most recent executed action."""
        return self._recent_actions[0] if self._recent_actions else None

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

        # Context Attack Prevention
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
                    trust_level=ContextTrustLevel.VERIFIED_ACTION,
                )

        # 2. File Reference Resolution ('open it', 'reveal that file')
        if expected_type in (None, "file"):
            file_patterns = [
                r"\b(?:open|reveal|show)\s+(?:it|that|that\s+file)\b",
            ]
            if any(re.search(pat, clean) for pat in file_patterns):
                if self._last_file_ref and self._last_file_ref.is_valid(self.process_ttl_seconds):
                    return self._last_file_ref

        # 3. Ephemeral Process/Port Pronoun Resolution ('stop that process', 'kill it', 'terminate it')
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
