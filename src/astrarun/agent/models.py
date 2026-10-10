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


class PlanningLevel(int, Enum):
    """Explicit planning complexity levels (Levels 0 through 5)."""
    LEVEL_0_DIRECT = 0          # Deterministic direct execution (fast path)
    LEVEL_1_SINGLE_ACTION = 1   # Single capability invocation
    LEVEL_2_STATIC_COMPOSE = 2  # Deterministic composition of 2-4 capabilities
    LEVEL_3_DYNAMIC_DAG = 3     # Dynamically constructed DAG planning with dataflow
    LEVEL_4_ADAPTIVE_LOOP = 4   # Closed-loop execution with runtime replanning
    LEVEL_5_EXTERNAL_REASON = 5 # Complex reasoning requiring external reasoning provider


class ArgumentSourceType(str, Enum):
    """Source provenance for capability argument resolution."""
    USER_TEXT = "USER_TEXT"
    ENTITY_RESOLVER = "ENTITY_RESOLVER"
    CONTEXT = "CONTEXT"
    PREVIOUS_STEP = "PREVIOUS_STEP"
    OBSERVATION = "OBSERVATION"
    CLARIFICATION = "CLARIFICATION"
    DETERMINISTIC_DEFAULT = "DETERMINISTIC_DEFAULT"


@dataclass
class ArgumentBinding:
    """Provenance tracking for resolved capability arguments."""
    parameter: str
    value: Any
    source_type: ArgumentSourceType = ArgumentSourceType.USER_TEXT
    source_reference: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "value": str(self.value) if not isinstance(self.value, (int, float, bool, str, list, dict)) else self.value,
            "source_type": self.source_type.value,
            "source_reference": self.source_reference,
            "confidence": self.confidence,
        }


@dataclass
class OutputReference:
    """Symbolic reference to an output field of an earlier step in the DAG."""
    step_id: str
    field: str

    def to_expression(self) -> str:
        return f"${{{self.step_id}.{self.field}}}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "field": self.field,
            "expression": self.to_expression(),
        }


@dataclass
class PlanCondition:
    """Safe, typed predicate condition for plan branching."""
    left: str            # e.g., "result.count", "result.connected", "step1.output_file"
    operator: str        # "==", "!=", ">", "<", ">=", "<=", "exists", "non_empty"
    right: Any = None    # Typed literal: bool, int, float, str

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Safely evaluate condition against resolved step results/context without eval()."""
        # Resolve left value
        left_val = None
        if "." in self.left:
            parts = self.left.split(".", 1)
            root = context.get(parts[0])
            if isinstance(root, dict):
                left_val = root.get(parts[1])
            elif hasattr(root, parts[1]):
                left_val = getattr(root, parts[1])
        else:
            left_val = context.get(self.left)

        op = self.operator.strip().lower()
        if op in ("==", "eq"):
            return left_val == self.right
        elif op in ("!=", "ne"):
            return left_val != self.right
        elif op in (">", "gt"):
            return left_val is not None and self.right is not None and left_val > self.right
        elif op in ("<", "lt"):
            return left_val is not None and self.right is not None and left_val < self.right
        elif op in (">=", "gte"):
            return left_val is not None and self.right is not None and left_val >= self.right
        elif op in ("<=", "lte"):
            return left_val is not None and self.right is not None and left_val <= self.right
        elif op == "exists":
            return left_val is not None
        elif op == "non_empty":
            return bool(left_val)
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "operator": self.operator,
            "right": self.right,
        }


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


class InteractionRequirement(str, Enum):
    """Execution modality requirement enforced by GoalPlanner and StepVerifier."""
    DIRECT_RESULT_ALLOWED = "DIRECT_RESULT_ALLOWED"
    APPLICATION_UI_REQUIRED = "APPLICATION_UI_REQUIRED"
    BROWSER_UI_REQUIRED = "BROWSER_UI_REQUIRED"
    SPECIFIC_TOOL_REQUIRED = "SPECIFIC_TOOL_REQUIRED"
    ANY_VALID_METHOD = "ANY_VALID_METHOD"

    # Compatibility aliases
    DIRECT_RESULT = "DIRECT_RESULT_ALLOWED"
    APPLICATION_UI = "APPLICATION_UI_REQUIRED"
    BROWSER_UI = "BROWSER_UI_REQUIRED"
    EITHER = "ANY_VALID_METHOD"



class ConstraintStatus(str, Enum):
    """Lifecycle status of a semantic constraint."""
    UNSATISFIED = "UNSATISFIED"
    IN_PROGRESS = "IN_PROGRESS"
    SATISFIED = "SATISFIED"
    SUPERSEDED_BY_USER = "SUPERSEDED_BY_USER"
    IMPOSSIBLE = "IMPOSSIBLE"


class ConstraintType(str, Enum):
    """Semantic classification of a goal constraint."""
    REQUIRED_CONTENT = "REQUIRED_CONTENT"
    OUTPUT_LOCATION = "OUTPUT_LOCATION"
    TARGET_ARTIFACT = "TARGET_ARTIFACT"
    TARGET_APPLICATION = "TARGET_APPLICATION"
    SYSTEM_STATE = "SYSTEM_STATE"
    NETWORK_STATE = "NETWORK_STATE"
    COMPUTATION_OUTPUT = "COMPUTATION_OUTPUT"
    CUSTOM = "CUSTOM"


@dataclass
class SemanticConstraint:
    """Explicit tracked constraint extracted from user intent."""
    constraint_id: str = field(default_factory=lambda: f"c_{uuid.uuid4().hex[:6]}")
    constraint_type: ConstraintType = ConstraintType.CUSTOM
    description: str = ""
    target_key: str = ""
    expected_value: Any = None
    status: ConstraintStatus = ConstraintStatus.UNSATISFIED
    is_mandatory: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "constraint_type": self.constraint_type.value,
            "description": self.description,
            "target_key": self.target_key,
            "expected_value": self.expected_value,
            "status": self.status.value,
            "is_mandatory": self.is_mandatory,
            "evidence": self.evidence,
        }


class PredicateType(str, Enum):
    """Domain-level verifiable state predicate."""
    FILE_EXISTS = "FILE_EXISTS"
    FILE_NON_EMPTY = "FILE_NON_EMPTY"
    FILE_CONTENT_CONTAINS = "FILE_CONTENT_CONTAINS"
    FILE_CONTENT_EQUALS = "FILE_CONTENT_EQUALS"
    APPLICATION_RUNNING = "APPLICATION_RUNNING"
    WINDOW_ACTIVE = "WINDOW_ACTIVE"
    NETWORK_CONNECTED = "NETWORK_CONNECTED"
    DATA_COMPUTED = "DATA_COMPUTED"
    CUSTOM = "CUSTOM"


class PredicateStatus(str, Enum):
    """Evaluation status of an acceptance predicate."""
    PENDING = "PENDING"
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"


@dataclass
class GoalPredicate:
    """Verifiable condition that must hold for goal completion."""
    predicate_id: str = field(default_factory=lambda: f"pred_{uuid.uuid4().hex[:6]}")
    predicate_type: PredicateType = PredicateType.CUSTOM
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    is_mandatory: bool = True
    status: PredicateStatus = PredicateStatus.PENDING
    evidence: dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicate_id": self.predicate_id,
            "predicate_type": self.predicate_type.value,
            "description": self.description,
            "parameters": self.parameters,
            "is_mandatory": self.is_mandatory,
            "status": self.status.value,
            "evidence": self.evidence,
            "error_message": self.error_message,
        }


@dataclass
class GoalContract:
    """
    Durable, typed semantic contract representing the user's intent.
    Preserves all entities, constraints, and acceptance predicates across
    planning, execution, replanning, and final verification.
    """
    contract_id: str = field(default_factory=lambda: f"gc_{uuid.uuid4().hex[:8]}")
    original_utterance: str = ""
    objective: str = ""
    target_application: Optional[str] = None
    target_artifact: Optional[str] = None
    target_location: Optional[str] = None
    entities: dict[str, Any] = field(default_factory=dict)
    constraints: list[SemanticConstraint] = field(default_factory=list)
    acceptance_predicates: list[GoalPredicate] = field(default_factory=list)
    interaction_requirement: InteractionRequirement = InteractionRequirement.DIRECT_RESULT_ALLOWED
    forbidden_outcomes: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def get_constraint(self, key: str) -> Optional[SemanticConstraint]:
        for c in self.constraints:
            if c.target_key == key:
                return c
        return None

    def get_mandatory_predicates(self) -> list[GoalPredicate]:
        return [p for p in self.acceptance_predicates if p.is_mandatory]

    def has_unsatisfied_mandatory_predicates(self) -> bool:
        return any(p.is_mandatory and p.status != PredicateStatus.SATISFIED for p in self.acceptance_predicates)

    def detect_information_loss(self, proposed_steps: list[Any]) -> list[str]:
        """
        Information-Loss Invariant: Detect if any mandatory constraint
        is completely missing or dropped in the proposed plan steps.
        """
        violations = []
        req_content = self.get_constraint("content") or self.get_constraint("text") or self.get_constraint("required_content")
        if req_content and req_content.expected_value:
            expected_val = str(req_content.expected_value).strip()
            has_content_in_steps = any(
                str(getattr(s, "arguments", {}).get("text", "")).strip() == expected_val
                or str(getattr(s, "arguments", {}).get("content", "")).strip() == expected_val
                for s in proposed_steps
            )
            if not has_content_in_steps:
                violations.append(
                    f"Information-loss detected: Required content '{expected_val}' is not addressed in any proposed plan step."
                )

        req_artifact = self.get_constraint("artifact") or self.get_constraint("filename") or self.get_constraint("target_artifact")
        if req_artifact and req_artifact.expected_value:
            expected_art = str(req_artifact.expected_value).strip().lower()
            has_artifact = any(
                expected_art in str(getattr(s, "arguments", {}).get("filename", "")).lower()
                or expected_art in str(getattr(s, "arguments", {}).get("path", "")).lower()
                for s in proposed_steps
            )
            if not has_artifact:
                violations.append(
                    f"Information-loss detected: Target artifact '{expected_art}' is not addressed in any proposed plan step."
                )

        return violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "original_utterance": self.original_utterance,
            "objective": self.objective,
            "target_application": self.target_application,
            "target_artifact": self.target_artifact,
            "target_location": self.target_location,
            "entities": self.entities,
            "constraints": [c.to_dict() for c in self.constraints],
            "acceptance_predicates": [p.to_dict() for p in self.acceptance_predicates],
            "interaction_requirement": self.interaction_requirement.value,
            "forbidden_outcomes": self.forbidden_outcomes,
            "provenance": self.provenance,
            "created_at": self.created_at,
        }


@dataclass
class Goal:
    """High-level user goal model."""
    goal_id: str = field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:8]}")
    raw_prompt: str = ""
    intent: str = ""
    target_entities: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    success_criteria: list[str] = field(default_factory=list)
    interaction_requirement: InteractionRequirement = InteractionRequirement.EITHER
    contract: Optional[GoalContract] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "raw_prompt": self.raw_prompt,
            "intent": self.intent,
            "target_entities": self.target_entities,
            "parameters": self.parameters,
            "success_criteria": self.success_criteria,
            "interaction_requirement": self.interaction_requirement.value,
            "contract": self.contract.to_dict() if self.contract else None,
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
    source: str = "general"
    confidence: float = 1.0
    freshness_ttl_s: float = 60.0  # Time-to-live before observation is considered stale

    def is_fresh(self) -> bool:
        """Evaluate if the observation is within its valid time-to-live window."""
        return (time.time() - self.timestamp) <= self.freshness_ttl_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "step_id": self.step_id,
            "timestamp": self.timestamp,
            "machine_state": self.machine_state,
            "raw_output": str(self.raw_output) if self.raw_output is not None else None,
            "extracted_facts": self.extracted_facts,
            "tier": self.tier.value,
            "source": self.source,
            "confidence": self.confidence,
            "freshness_ttl_s": self.freshness_ttl_s,
            "is_fresh": self.is_fresh(),
        }


@dataclass
class ProcessObservation(Observation):
    """Observation of active process state (PID, name, cpu, memory)."""
    pid: Optional[int] = None
    process_name: str = ""
    is_running: bool = True
    cpu_percent: float = 0.0
    source: str = "process"
    freshness_ttl_s: float = 5.0  # Processes change quickly; 5s TTL


@dataclass
class WindowObservation(Observation):
    """Observation of desktop window state (HWND, title, visibility, geometry)."""
    hwnd: int = 0
    title: str = ""
    is_visible: bool = True
    is_foreground: bool = False
    source: str = "window"
    freshness_ttl_s: float = 10.0  # Active windows change frequently; 10s TTL


@dataclass
class FileObservation(Observation):
    """Observation of filesystem state (path, size, exists, modified)."""
    path: str = ""
    exists: bool = False
    size_bytes: int = 0
    modified_at: float = 0.0
    source: str = "file"
    freshness_ttl_s: float = 120.0  # Files remain steady; 2 min TTL


@dataclass
class NetworkObservation(Observation):
    """Observation of network state (connected, SSID, signal, ports)."""
    connected: bool = False
    ssid: str = ""
    signal_quality: int = 0
    listening_ports: list[int] = field(default_factory=list)
    source: str = "network"
    freshness_ttl_s: float = 15.0  # Wi-Fi / ports; 15s TTL


@dataclass
class UIObservation(Observation):
    """Observation of UI element hierarchy and patterns."""
    automation_id: str = ""
    name: str = ""
    control_type: str = ""
    is_enabled: bool = True
    source: str = "ui"
    freshness_ttl_s: float = 15.0


@dataclass
class SystemObservation(Observation):
    """Observation of system health (battery, cpu, memory, disk)."""
    battery_percent: Optional[int] = None
    is_charging: Optional[bool] = None
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    source: str = "system"
    freshness_ttl_s: float = 30.0


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
    argument_bindings: dict[str, ArgumentBinding] = field(default_factory=dict)
    description: str = ""
    human_label: str = ""
    state: StepState = StepState.PENDING
    dependencies: list[StepDependency] = field(default_factory=list)
    condition: Optional[PlanCondition] = None
    interaction_tier: InteractionTier = InteractionTier.TIER_A_NATIVE
    interaction_requirement: InteractionRequirement = InteractionRequirement.EITHER
    verifier_strategy: VerifierStrategy = VerifierStrategy.RETURN_CODE_ONLY
    verifier_params: dict[str, Any] = field(default_factory=dict)
    satisfies_predicates: list[str] = field(default_factory=list)
    requires_predicates: list[str] = field(default_factory=list)
    declared_effects: list[str] = field(default_factory=list)
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
            "argument_bindings": {k: b.to_dict() for k, b in self.argument_bindings.items()},
            "description": self.description,
            "human_label": self.human_label,
            "state": self.state.value,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "condition": self.condition.to_dict() if self.condition else None,
            "interaction_tier": self.interaction_tier.value,
            "interaction_requirement": self.interaction_requirement.value,
            "verifier_strategy": self.verifier_strategy.value,
            "verifier_params": self.verifier_params,
            "satisfies_predicates": self.satisfies_predicates,
            "requires_predicates": self.requires_predicates,
            "declared_effects": self.declared_effects,
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
class PlanRevision:
    """Explicit historical record of task graph modification during replanning."""
    revision_id: str = field(default_factory=lambda: f"rev_{uuid.uuid4().hex[:8]}")
    task_id: str = ""
    previous_plan_version: int = 1
    new_plan_version: int = 2
    reason: str = ""
    observation_ids: list[str] = field(default_factory=list)
    added_steps: list[str] = field(default_factory=list)
    removed_steps: list[str] = field(default_factory=list)
    modified_dependencies: dict[str, list[str]] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "task_id": self.task_id,
            "previous_plan_version": self.previous_plan_version,
            "new_plan_version": self.new_plan_version,
            "reason": self.reason,
            "observation_ids": self.observation_ids,
            "added_steps": self.added_steps,
            "removed_steps": self.removed_steps,
            "modified_dependencies": self.modified_dependencies,
            "timestamp": self.timestamp,
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


class PlanValidationStatus(str, Enum):
    """Validation verdict for a candidate execution plan."""
    VALID = "VALID"
    INVALID = "INVALID"
    CLARIFY = "CLARIFY"
    REASONING_REQUIRED = "REASONING_REQUIRED"


@dataclass
class PlanValidationResult:
    """Result of static and policy validation on a proposed plan."""
    status: PlanValidationStatus
    is_valid: bool
    issues: list[str] = field(default_factory=list)
    clarification_prompt: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "is_valid": self.is_valid,
            "issues": self.issues,
            "clarification_prompt": self.clarification_prompt,
        }


class GoalVerificationStatus(str, Enum):
    """High-level completion status of the overall user goal."""
    GOAL_COMPLETED = "GOAL_COMPLETED"
    GOAL_INCOMPLETE = "GOAL_INCOMPLETE"


@dataclass
class GoalVerificationResult:
    """Result of post-plan empirical goal verification."""
    status: GoalVerificationStatus
    completed: bool
    message: str = ""
    missing_criteria: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "completed": self.completed,
            "message": self.message,
            "missing_criteria": self.missing_criteria,
            "evidence": self.evidence,
        }


@dataclass
class Plan:
    """Execution plan representing a directed acyclic graph of steps."""
    plan_id: str = field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    goal_id: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    version: int = 1
    planning_level: PlanningLevel = PlanningLevel.LEVEL_3_DYNAMIC_DAG
    revisions: list[PlanRevision] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: PlanStatus = PlanStatus.DRAFT
    context: dict[str, Any] = field(default_factory=dict)
    contract: Optional[GoalContract] = None

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
            "planning_level": self.planning_level.value,
            "revisions": [r.to_dict() for r in self.revisions],
            "created_at": self.created_at,
            "status": self.status.value,
            "context": self.context,
            "contract": self.contract.to_dict() if self.contract else None,
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
    revisions: list[PlanRevision] = field(default_factory=list)
    goal_verification: Optional[GoalVerificationResult] = None
    progress_mode: ProgressMode = ProgressMode.DETERMINATE
    progress_pct: float = 0.0
    estimated_remaining_ms: float = 0.0
    cancellation_requested: bool = False
    execution_traces: list[dict[str, Any]] = field(default_factory=list)
    contract: Optional[GoalContract] = None

    def to_dict(self) -> dict[str, Any]:
        contract_data = self.contract.to_dict() if self.contract else (self.goal.contract.to_dict() if self.goal and self.goal.contract else None)
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
            "revisions": [r.to_dict() for r in self.revisions],
            "execution_traces": self.execution_traces,
            "goal_verification": self.goal_verification.to_dict() if self.goal_verification else None,
            "progress_mode": self.progress_mode.value,
            "progress_pct": self.progress_pct,
            "estimated_remaining_ms": self.estimated_remaining_ms,
            "cancellation_requested": self.cancellation_requested,
            "contract": contract_data,
        }


