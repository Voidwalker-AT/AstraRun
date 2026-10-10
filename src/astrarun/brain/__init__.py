"""AstraRun Brain Subsystem.

The Brain domain decides what the user means, reasons, plans, replans,
selects capabilities, interprets observations, and verifies semantic completion.
The Brain contains ZERO direct OS automation primitives or execution authority.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from astrarun.brain.decision import (
    IntentClassifier,
    ResolvedEntity,
    SemanticEntityResolver,
)
from astrarun.brain.memory import BrainMemory
from astrarun.brain.models import (
    AgentTask,
    BrainDecision,
    BrainIntent,
    Goal,
    Plan,
    PlanStep,
)
from astrarun.brain.reasoning import (
    AgentExecutionEngine,
    GoalPlanner,
    GoalVerifier,
)
from astrarun.brain.vision import VisualGrounding
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.brain")


class Brain:
    """
    Unified cognitive facade for AstraRun.
    Orchestrates Decision, Reasoning, Memory, and Vision.
    """

    _instance: Optional[Brain] = None

    def __init__(
        self,
        planner: Optional[GoalPlanner] = None,
        agent_engine: Optional[AgentExecutionEngine] = None,
        entity_resolver: Optional[SemanticEntityResolver] = None,
        intent_classifier: Optional[IntentClassifier] = None,
        memory: Optional[BrainMemory] = None,
        vision: Optional[VisualGrounding] = None,
    ) -> None:
        self.planner = planner
        self.agent_engine = agent_engine
        self.entity_resolver = entity_resolver or SemanticEntityResolver()
        self.intent_classifier = intent_classifier or IntentClassifier()
        self.memory = memory or BrainMemory()
        self.vision = vision or VisualGrounding()

    @classmethod
    def get_instance(cls) -> Brain:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def decide_intent(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> BrainDecision:
        """Classify semantic intent of user prompt."""
        return self.intent_classifier.classify(prompt, context=context)

    def resolve_entity(self, query: str) -> Optional[ResolvedEntity]:
        """Resolve natural language query to canonical desktop entity."""
        return self.entity_resolver.resolve_application(query)

    def plan_goal(self, prompt: str) -> Optional[Plan]:
        """Decompose prompt into validated execution plan DAG."""
        if not self.planner:
            return None
        goal = self.planner.parse_goal(prompt)
        return self.planner.create_plan(goal)

    def execute_goal(self, prompt: str) -> Optional[AgentTask]:
        """Execute goal in closed loop through AgentExecutionEngine."""
        if not self.agent_engine:
            return None
        return self.agent_engine.execute_goal(prompt)


__all__ = [
    "Brain",
    "BrainDecision",
    "BrainIntent",
    "GoalPlanner",
    "AgentExecutionEngine",
    "GoalVerifier",
    "SemanticEntityResolver",
    "ResolvedEntity",
    "IntentClassifier",
    "BrainMemory",
    "VisualGrounding",
]
