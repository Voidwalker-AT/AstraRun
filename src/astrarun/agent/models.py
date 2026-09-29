"""Core domain models for AstraRun v0.11 Dynamic Workstation Agent Runtime."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.schema import InteractionTier, VerifierStrategy


class AgentTaskStatus(str, Enum):
    """Lifecycle status of an autonomous agent task."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    AWAITING_INPUT = "AWAITING_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepState(str, Enum):
    """State machine states for individual plan steps."""
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class ProgressMode(str, Enum):
    """Honest HUD progress mode."""
    INSTANT = "INSTANT"             # Sub-second single operation (<100ms)
    DETERMINATE = "DETERMINATE"     # Measurable progress (0..100% based on steps or byte/time tracking)
    INDETERMINATE = "INDETERMINATE" # Unmeasurable duration ("Working...")
    EVENT_DRIVEN = "EVENT_DRIVEN"   # Waiting on external signal or user action


class PlanStatus(str, Enum):
    """Lifecycle status of an execution plan."""
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    REPLANNING = "REPLANNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class Goal:
    """High-level user goal model."""
    goal_id: str = field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:8]}")
    raw_prompt: str = ""
    intent: str = ""
    target_entities: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    success_criteria: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "raw_prompt": self.raw_prompt,
            "intent": self.intent,
            "target_entities": self.target_entities,
            "parameters": self.parameters,
            "success_criteria": self.success_criteria,
            "created_at": self.created_at,
        }


@dataclass
class StepDependency:
    """Dependency relationship between plan steps."""
    step_id: str
    required_state: StepState = StepState.COMPLETED
    data_mapping: dict[str, str] = field(default_factory=dict)  # from_output_key -> to_arg_key

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "required_state": self.required_state.value,
            "data_mapping": self.data_mapping,
        }


@dataclass
class Observation:
    """Observed machine or environment state captured after action execution."""
    observation_id: str = field(default_factory=lambda: f"obs_{uuid.uuid4().hex[:8]}")
    step_id: str = ""
    timestamp: float = field(default_factory=time.time)
    machine_state: dict[str, Any] = field(default_factory=dict)
    raw_output: Any = None
    extracted_facts: dict[str, Any] = field(default_factory=dict)
    tier: InteractionTier = InteractionTier.TIER_A_NATIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "step_id": self.step_id,
            "timestamp": self.timestamp,
            "machine_state": self.machine_state,
            "raw_output": str(self.raw_output) if self.raw_output is not None else None,
            "extracted_facts": self.extracted_facts,
            "tier": self.tier.value,
        }


@dataclass
class Verification:
    """Post-execution verification report for a plan step."""
    step_id: str
    verifier_strategy: VerifierStrategy
    verified: bool
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "verifier_strategy": self.verifier_strategy.value,
            "verified": self.verified,
            "message": self.message,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
        }


@dataclass
class PlanStep:
    """Single unit of work within an execution plan."""
    step_id: str
    capability_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    state: StepState = StepState.PENDING
    dependencies: list[StepDependency] = field(default_factory=list)
    interaction_tier: InteractionTier = InteractionTier.TIER_A_NATIVE
    verifier_strategy: VerifierStrategy = VerifierStrategy.RETURN_CODE_ONLY
    verifier_params: dict[str, Any] = field(default_factory=dict)
    result: Optional[CapabilityResult] = None
    observation: Optional[Observation] = None
    verification: Optional[Verification] = None
    retry_count: int = 0
    max_retries: int = 1
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "capability_id": self.capability_id,
            "arguments": self.arguments,
            "description": self.description,
            "state": self.state.value,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "interaction_tier": self.interaction_tier.value,
            "verifier_strategy": self.verifier_strategy.value,
            "verifier_params": self.verifier_params,
            "result": self.result.to_dict() if self.result else None,
            "observation": self.observation.to_dict() if self.observation else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "weight": self.weight,
        }


@dataclass
class ReplanEvent:
    """Record of dynamic runtime plan adjustment or replanning."""
    replan_id: str = field(default_factory=lambda: f"replan_{uuid.uuid4().hex[:8]}")
    trigger_step_id: str = ""
    reason: str = ""
    old_plan_version: int = 1
    new_plan_version: int = 2
    timestamp: float = field(default_factory=time.time)
    modifications: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "replan_id": self.replan_id,
            "trigger_step_id": self.trigger_step_id,
            "reason": self.reason,
            "old_plan_version": self.old_plan_version,
            "new_plan_version": self.new_plan_version,
            "timestamp": self.timestamp,
            "modifications": self.modifications,
        }


@dataclass
class Plan:
    """Execution plan representing a directed acyclic graph of steps."""
    plan_id: str = field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    goal_id: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    version: int = 1
    created_at: float = field(default_factory=time.time)
    status: PlanStatus = PlanStatus.DRAFT

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "steps": [s.to_dict() for s in self.steps],
            "version": self.version,
            "created_at": self.created_at,
            "status": self.status.value,
        }


@dataclass
class AgentTask:
    """Root execution context for an autonomous agent goal run."""
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    goal: Goal = field(default_factory=Goal)
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    plan: Plan = field(default_factory=Plan)
    current_step_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    context: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    observations: list[Observation] = field(default_factory=list)
    replans: list[ReplanEvent] = field(default_factory=list)
    progress_mode: ProgressMode = ProgressMode.DETERMINATE
    progress_pct: float = 0.0
    estimated_remaining_ms: float = 0.0
    cancellation_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal.to_dict(),
            "status": self.status.value,
            "plan": self.plan.to_dict(),
            "current_step_id": self.current_step_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "context": self.context,
            "error": self.error,
            "observations": [o.to_dict() for o in self.observations],
            "replans": [r.to_dict() for r in self.replans],
            "progress_mode": self.progress_mode.value,
            "progress_pct": self.progress_pct,
            "estimated_remaining_ms": self.estimated_remaining_ms,
            "cancellation_requested": self.cancellation_requested,
        }
