"""Data models for Workstation Context Engine with trusted event tracking."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ContextTrustLevel(str, Enum):
    """Trust classifications for contextual facts."""
    VERIFIED_ACTION = "VERIFIED_ACTION"   # Directly executed/verified through AstraRun ActionGate
    OS_OBSERVATION = "OS_OBSERVATION"     # Directly observed from Win32 / psutil snapshot
    INFERRED = "INFERRED"                 # Deterministically inferred from relations
    MODEL_PROPOSED = "MODEL_PROPOSED"     # Proposed by statistical model (NEVER auto-trusted)


@dataclass
class ContextEvent:
    """Record of a workstation lifecycle event with source provenance and trust level."""
    type: str
    entity_id: str
    timestamp: float = field(default_factory=time.time)
    source: str = "astrarun"
    trust_level: ContextTrustLevel = ContextTrustLevel.VERIFIED_ACTION
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "entity_id": self.entity_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "trust_level": self.trust_level.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextEvent:
        trust_str = data.get("trust_level", ContextTrustLevel.VERIFIED_ACTION.value)
        try:
            trust = ContextTrustLevel(trust_str)
        except ValueError:
            trust = ContextTrustLevel.VERIFIED_ACTION
        return cls(
            type=data.get("type", ""),
            entity_id=data.get("entity_id", ""),
            timestamp=data.get("timestamp", time.time()),
            source=data.get("source", "astrarun"),
            trust_level=trust,
            metadata=data.get("metadata", {}),
        )


@dataclass
class RecentAction:
    """Record of a recently executed or proposed workstation action."""
    action_type: str
    entity_id: str
    target: str | None = None
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "entity_id": self.entity_id,
            "target": self.target,
            "timestamp": self.timestamp,
            "success": self.success,
            "session_id": self.session_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecentAction:
        return cls(
            action_type=data.get("action_type", ""),
            entity_id=data.get("entity_id", ""),
            target=data.get("target"),
            timestamp=data.get("timestamp", time.time()),
            success=data.get("success", True),
            session_id=data.get("session_id", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class RecentProjectRecord:
    """Record of recent project interactions."""
    project_id: str
    first_seen: float = field(default_factory=time.time)
    last_interacted: float = field(default_factory=time.time)
    interaction_count: int = 1
    last_action: str = "open_project"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "first_seen": self.first_seen,
            "last_interacted": self.last_interacted,
            "interaction_count": self.interaction_count,
            "last_action": self.last_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecentProjectRecord:
        return cls(
            project_id=data.get("project_id", ""),
            first_seen=data.get("first_seen", time.time()),
            last_interacted=data.get("last_interacted", time.time()),
            interaction_count=data.get("interaction_count", 1),
            last_action=data.get("last_action", "open_project"),
        )


@dataclass
class DevPortInfo:
    """Information about a listening developer port."""
    port: int
    pid: int
    process_name: str
    create_time: float = 0.0
    status: str = "LISTEN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "pid": self.pid,
            "process_name": self.process_name,
            "create_time": self.create_time,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DevPortInfo:
        return cls(
            port=data.get("port", 0),
            pid=data.get("pid", 0),
            process_name=data.get("process_name", ""),
            create_time=data.get("create_time", 0.0),
            status=data.get("status", "LISTEN"),
        )


@dataclass
class ContextReference:
    """A verified contextual reference resolved from recent activity or context state."""
    entity_id: str
    entity_type: str  # "project", "process", "port", "file", "app"
    source: str       # "recent_action", "foreground_window", "inspected_port"
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    trust_level: ContextTrustLevel = ContextTrustLevel.VERIFIED_ACTION

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.timestamp)

    def is_valid(self, ttl_seconds: float) -> bool:
        return self.age_seconds <= ttl_seconds


@dataclass
class WorkstationContext:
    """Structured, typed snapshot of workstation context facts."""
    foreground_app: str | None = None
    foreground_title: str | None = None
    foreground_pid: int | None = None
    foreground_window: int | None = None
    active_project: str | None = None
    recent_projects: list[RecentProjectRecord] = field(default_factory=list)
    recent_actions: list[RecentAction] = field(default_factory=list)
    recent_apps: list[str] = field(default_factory=list)
    recent_files: list[str] = field(default_factory=list)
    recent_processes: list[int] = field(default_factory=list)
    recent_ports: list[int] = field(default_factory=list)
    recent_events: list[ContextEvent] = field(default_factory=list)
    listening_dev_ports: list[DevPortInfo] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "foreground_app": self.foreground_app,
            "foreground_title": self.foreground_title,
            "foreground_pid": self.foreground_pid,
            "foreground_window": self.foreground_window,
            "active_project": self.active_project,
            "recent_projects": [p.to_dict() for p in self.recent_projects],
            "recent_actions": [a.to_dict() for a in self.recent_actions],
            "recent_apps": self.recent_apps,
            "recent_files": self.recent_files,
            "recent_processes": self.recent_processes,
            "recent_ports": self.recent_ports,
            "recent_events": [e.to_dict() for e in self.recent_events],
            "listening_dev_ports": [p.to_dict() for p in self.listening_dev_ports],
            "timestamp": self.timestamp,
        }
