"""Cognitive data models and strict structured output schemas for AstraRun 1.0.

Provides:
  - Strongly typed InferenceRequest and InferenceObservation
  - Pydantic-validated cognitive decision schemas:
      - IntentDecision
      - SkillSelection
      - PlanDAG & PlanStep (with cycle detection and dependency validation)
      - RecoveryDecision (Mode-D recovery)
      - ClarificationRequest
  - Lifecycle enums (ModelRole, ResidencyPreference, ModelState)
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# 1. Lifecycle Enums & Metadata
# =============================================================================

class ModelRole(str, Enum):
    """Functional role of a model within AstraRun's cognitive architecture."""
    FAST = "FAST"          # Low-latency interactive model (Spark-X2.5)
    DEEP = "DEEP"          # Reasoning and code DAG planner (Qwen2.5-Coder)
    SPECIALIST = "SPECIALIST"  # Future vision/audio/domain specialist


class ResidencyPreference(str, Enum):
    """Memory residency priority for local model instances."""
    PINNED = "PINNED"        # Never evicted during normal operation (Spark)
    WARM = "WARM"            # Kept resident if memory permits; evictable under emergency (Qwen)
    ON_DEMAND = "ON_DEMAND"  # Loaded on request, eligible for immediate unloading
    EVICTABLE = "EVICTABLE"  # First in line to be evicted on memory pressure


class ModelState(str, Enum):
    """Supervised operational state of a model server instance."""
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    WARMING = "WARMING"
    READY = "READY"
    BUSY = "BUSY"
    EVICTING = "EVICTING"
    FAILED = "FAILED"


# =============================================================================
# 2. Model Client Contracts
# =============================================================================

class InferenceRequest(BaseModel):
    """Model-independent structured inference request submitted to ModelClient."""
    model_config = ConfigDict(extra="ignore")

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    role: ModelRole = ModelRole.FAST
    messages: List[Dict[str, str]] = Field(default_factory=list)
    schema_dict: Optional[Dict[str, Any]] = None
    max_tokens: int = 512
    temperature: float = 0.2
    timeout: float = 30.0
    stop: List[str] = Field(default_factory=lambda: ["<|im_end|>", "<|endoftext|>"])
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InferenceObservation(BaseModel):
    """Standardized, model-independent response returned from ModelClient."""
    model_config = ConfigDict(extra="ignore")

    model_id: str
    status: str  # "SUCCESS", "FAILED", "TIMEOUT", "SCHEMA_INVALID"
    raw_output: str = ""
    parsed_output: Optional[Dict[str, Any]] = None
    schema_valid: bool = False
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    failure_reason: Optional[str] = None
    created_at: float = Field(default_factory=time.time)

    @property
    def is_success(self) -> bool:
        return self.status == "SUCCESS" and self.schema_valid


# =============================================================================
# 3. Strict Structured Cognitive Schemas
# =============================================================================

class IntentDecision(BaseModel):
    """Structured classification emitted by Fast cognitive model."""
    model_config = ConfigDict(extra="forbid")

    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    is_compound: bool = False
    entities: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    requires_deep_planning: bool = False


class SkillSelection(BaseModel):
    """Selection of a known, verified skill for rapid execution."""
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    fallback_skill: Optional[str] = None


class PlanStep(BaseModel):
    """An individual discrete action step in a multi-step PlanDAG."""
    model_config = ConfigDict(extra="forbid")

    step_id: str
    capability: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    risk_hint: str = "LOW"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    expected_observation: str = ""
    completion_condition: str = ""


class PlanDAG(BaseModel):
    """
    Typed, structured Directed Acyclic Graph plan emitted by deep cognitive planner.
    Enforces strict structural validity: no duplicate IDs, no undefined dependencies, and no cycles.
    """
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    goal: str
    steps: List[PlanStep]
    dataflow: Dict[str, str] = Field(default_factory=dict)
    estimated_risk: str = "LOW"

    def validate_graph(self) -> None:
        """
        Validate graph invariants:
        1. No duplicate step_ids.
        2. All dependencies reference declared step_ids.
        3. No cyclic dependencies (DAG property).
        """
        if not self.steps:
            raise ValueError("PlanDAG must contain at least one step.")

        step_ids = set()
        for step in self.steps:
            if step.step_id in step_ids:
                raise ValueError(f"Duplicate step_id detected in PlanDAG: {step.step_id}")
            step_ids.add(step.step_id)

        # Check references
        for step in self.steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    raise ValueError(f"Step '{step.step_id}' references unknown dependency: '{dep}'")
                if dep == step.step_id:
                    raise ValueError(f"Step '{step.step_id}' cannot depend on itself.")

        # Cycle detection via topological DFS
        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        for sid in step_ids:
            visited[sid] = 0

        dep_map = {step.step_id: step.dependencies for step in self.steps}

        def dfs(node: str) -> None:
            visited[node] = 1
            for parent in dep_map.get(node, []):
                if visited[parent] == 1:
                    raise ValueError(f"Cyclic dependency detected involving step '{node}' and '{parent}'")
                if visited[parent] == 0:
                    dfs(parent)
            visited[node] = 2

        for sid in step_ids:
            if visited[sid] == 0:
                dfs(sid)

    def topological_sort(self) -> List[PlanStep]:
        """Return steps sorted in valid topological execution order."""
        self.validate_graph()
        step_dict = {s.step_id: s.model_copy() for s in self.steps}
        in_degree = {s.step_id: 0 for s in self.steps}
        children: Dict[str, List[str]] = {s.step_id: [] for s in self.steps}

        for s in self.steps:
            for dep in s.dependencies:
                children[dep].append(s.step_id)
                in_degree[s.step_id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        sorted_steps: List[PlanStep] = []

        while queue:
            curr = queue.pop(0)
            sorted_steps.append(step_dict[curr])
            for child in children[curr]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(sorted_steps) != len(self.steps):
            raise ValueError("Dependency cycle detected during topological sort.")

        return sorted_steps


class RecoveryDecision(BaseModel):
    """Structured recovery proposition emitted by cognitive engine on execution failure."""
    model_config = ConfigDict(extra="forbid")

    failed_step_id: str
    error_code: str
    diagnosis: str
    recovery_action: str  # "RETRY", "ALTERNATIVE_CAPABILITY", "DEGRADE_TIER", "ESCALATE", "ABORT"
    new_step: Optional[PlanStep] = None
    remaining_goal: str = ""
    can_retry: bool = True
    retry_count: int = 0


class ClarificationRequest(BaseModel):
    """Structured question returned when a request is ambiguous or missing required parameters."""
    model_config = ConfigDict(extra="forbid")

    missing_parameter: str
    prompt_question: str
    candidate_options: List[str] = Field(default_factory=list)
