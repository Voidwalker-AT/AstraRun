"""Data models for AstraRun Brain subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Re-export core cognitive and agent models
from astrarun.cognition.models import IntentClass, IntentReasonerResult
from astrarun.agent.models import (
    Goal,
    GoalContract,
    SemanticConstraint,
    ConstraintType,
    ConstraintStatus,
    GoalPredicate,
    PredicateType,
    PredicateStatus,
    Plan,
    PlanStep,
    StepState,
    PlanStatus,
    PlanningLevel,
    AgentTask,
    AgentTaskStatus,
    StepDependency,
    OutputReference,
    GoalVerificationResult,
    GoalVerificationStatus,
)


class BrainIntent(str, Enum):
    DIRECT_ACTION = "DIRECT_ACTION"
    COMPOSITE_GOAL = "COMPOSITE_GOAL"
    CONVERSATIONAL = "CONVERSATIONAL"
    QUESTION = "QUESTION"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    SECURITY_REJECTION = "SECURITY_REJECTION"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class BrainDecision:
    """Canonical decision output produced by Brain."""
    intent: BrainIntent
    primary_capability: Optional[str] = None
    confidence: float = 1.0
    reason: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    sub_intents: List[Dict[str, Any]] = field(default_factory=list)
    requires_disambiguation: bool = False
    ambiguous_choices: List[Dict[str, Any]] = field(default_factory=list)
    routing_tier: str = "BRAIN"
