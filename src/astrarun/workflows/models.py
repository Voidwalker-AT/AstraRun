"""Data models for Workflow Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from astrarun.core.models import ToolRisk


@dataclass
class WorkflowStep:
    """Predefined step calling a registered tool."""
    step_id: str
    name: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    critical: bool = True  # If true, failure halts remaining steps
    source_clause_idx: int | None = None



@dataclass
class WorkflowStepResult:
    """Result of executing a single workflow step."""
    step_id: str
    name: str
    tool: str
    success: bool
    message: str
    data: Any = None
    latency_ms: float = 0.0


@dataclass
class Workflow:
    """Predefined typed workflow definition."""
    id: str
    name: str
    description: str
    steps: list[WorkflowStep]
    risk: ToolRisk = ToolRisk.LOW
    rollback_supported: bool = False


@dataclass
class WorkflowExecutionResult:
    """Summary of a workflow execution run."""
    workflow_id: str
    entity_id: str
    success: bool
    message: str
    steps_attempted: int
    steps_succeeded: int
    steps_failed: int
    step_results: list[WorkflowStepResult] = field(default_factory=list)
    rollback_supported: bool = False
    timestamp: float = field(default_factory=time.time)
    total_latency_ms: float = 0.0

    @property
    def status(self) -> str:
        return "completed" if self.success else "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "entity_id": self.entity_id,
            "success": self.success,
            "message": self.message,
            "steps_attempted": self.steps_attempted,
            "steps_succeeded": self.steps_succeeded,
            "steps_failed": self.steps_failed,
            "rollback_supported": self.rollback_supported,
            "timestamp": self.timestamp,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "step_results": [
                {
                    "step_id": s.step_id,
                    "tool": s.tool,
                    "success": s.success,
                    "message": s.message,
                    "latency_ms": round(s.latency_ms, 2),
                }
                for s in self.step_results
            ],
        }


@dataclass
class WorkflowProposal:
    """Compiled proposal representing planned actions before gating and execution."""
    status: str  # "READY", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CLARIFY", "BLOCKED", "EMPTY"
    steps: list[WorkflowStep] = field(default_factory=list)
    overall_risk: ToolRisk = ToolRisk.LOW
    requires_confirmation: bool = False
    blocked_reasons: list[str] = field(default_factory=list)
    unsupported_clauses: list[str] = field(default_factory=list)
    preview: str = ""
    utterance: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "steps": [
                {
                    "step_id": s.step_id,
                    "name": s.name,
                    "tool": s.tool,
                    "arguments": s.arguments,
                }
                for s in self.steps
            ],
            "overall_risk": self.overall_risk.value,
            "requires_confirmation": self.requires_confirmation,
            "blocked_reasons": self.blocked_reasons,
            "unsupported_clauses": self.unsupported_clauses,
            "preview": self.preview,
        }

