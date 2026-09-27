"""Core data models and type definitions for AstraRun."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ToolRisk(str, Enum):
    """Risk classification for tools."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


@dataclass
class Decision:
    """Structured decision output produced by any router implementation."""
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "deterministic"
    explanation: str = ""

    @property
    def is_resolved(self) -> bool:
        """Check if the decision represents an actionable tool invocation."""
        return self.tool != "unknown" and self.confidence > 0.0

    @classmethod
    def unknown(cls, request: str, explanation: str = "") -> Decision:
        """Helper to create an unknown/unresolved decision."""
        return cls(
            tool="unknown",
            args={"request": request},
            confidence=0.0,
            source="deterministic",
            explanation=explanation or f"No matching route found for: {request}",
        )


@dataclass
class ToolMetadata:
    """Metadata describing a registered tool."""
    name: str
    description: str
    risk: ToolRisk
    args_schema: dict[str, Any]
    handler: Callable[..., Any]


@dataclass
class AppInfo:
    """Information about a discovered or configured application."""
    key: str
    name: str
    path: str
    description: str = ""


@dataclass
class FolderInfo:
    """Information about a discovered or configured folder."""
    key: str
    name: str
    path: str
    description: str = ""


@dataclass
class RoutingContext:
    """Contextual registries, search index, and telemetry provided to routers."""
    apps: dict[str, AppInfo] = field(default_factory=dict)
    folders: dict[str, FolderInfo] = field(default_factory=dict)
    urls: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    search_index: Any = None
    telemetry: Any = None
    usage_store: Any = None
    laya_router: Any = None
    shadow_collector: Any = None
