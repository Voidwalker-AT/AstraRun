"""Strongly typed turn decision schemas for AstraRun 1.0 intelligence spine."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TurnMode(str, Enum):
    """Execution mode chosen for a single user turn."""
    DIRECT_ANSWER = "DIRECT_ANSWER"                    # Pure conversational response, no OS tool required
    TOOL_PLAN = "TOOL_PLAN"                            # One or more governed workstation capabilities
    HYBRID_ACT_AND_ANSWER = "HYBRID_ACT_AND_ANSWER"    # Perform governed action AND provide conversational synthesis
    CLARIFY = "CLARIFY"                                # Request clarification from user before acting
    REFUSE = "REFUSE"                                  # Refuse out-of-scope or unsafe request gracefully


@dataclass
class PlanStep:
    """
    A single governed capability execution step proposed by TurnReasoner or FastTrack.
    
    Invariant: Does NOT permit arbitrary executable python code or raw shell commands.
    Dynamic code generation must target the registered governed capability ('run_python_code').
    """
    step_id: str
    capability_id: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    expected_postconditions: Optional[Dict[str, Any]] = None
    depends_on: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "capability_id": self.capability_id,
            "arguments": dict(self.arguments),
            "expected_postconditions": dict(self.expected_postconditions) if self.expected_postconditions else None,
            "depends_on": list(self.depends_on),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlanStep:
        return cls(
            step_id=data.get("step_id", "step-1"),
            capability_id=data["capability_id"],
            arguments=dict(data.get("arguments", {})),
            expected_postconditions=data.get("expected_postconditions"),
            depends_on=list(data.get("depends_on", [])),
        )


@dataclass
class TurnDecision:
    """
    Authoritative decision structure produced by TurnReasoner or SingleStepFastTrack.
    
    Determines whether to answer directly, execute a governed tool plan, or perform hybrid action.
    """
    mode: TurnMode
    assistant_reply: Optional[str] = None
    goal_summary: Optional[str] = None
    plan_steps: List[PlanStep] = field(default_factory=list)
    referenced_artifacts: List[str] = field(default_factory=list)
    clarification_question: Optional[str] = None
    confidence: float = 1.0
    model_role: str = "TURN_REASONER"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "assistant_reply": self.assistant_reply,
            "goal_summary": self.goal_summary,
            "plan_steps": [s.to_dict() for s in self.plan_steps],
            "referenced_artifacts": list(self.referenced_artifacts),
            "clarification_question": self.clarification_question,
            "confidence": self.confidence,
            "model_role": self.model_role,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TurnDecision:
        mode_val = data.get("mode", TurnMode.DIRECT_ANSWER.value)
        if isinstance(mode_val, str):
            mode = TurnMode(mode_val)
        else:
            mode = mode_val

        steps = [PlanStep.from_dict(s) for s in data.get("plan_steps", [])]
        return cls(
            mode=mode,
            assistant_reply=data.get("assistant_reply"),
            goal_summary=data.get("goal_summary"),
            plan_steps=steps,
            referenced_artifacts=list(data.get("referenced_artifacts", [])),
            clarification_question=data.get("clarification_question"),
            confidence=float(data.get("confidence", 1.0)),
            model_role=data.get("model_role", "TURN_REASONER"),
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def json_schema(cls) -> Dict[str, Any]:
        """Return canonical JSON schema for LLM structured output enforcement."""
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [m.value for m in TurnMode],
                    "description": "Decision mode for the turn.",
                },
                "assistant_reply": {
                    "type": "string",
                    "description": "Direct conversational answer or explanation to the user.",
                },
                "goal_summary": {
                    "type": "string",
                    "description": "Short summary of the operational intent.",
                },
                "plan_steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_id": {"type": "string"},
                            "capability_id": {"type": "string"},
                            "arguments": {"type": "object"},
                            "expected_postconditions": {"type": "object"},
                            "depends_on": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["step_id", "capability_id", "arguments"],
                    },
                },
                "referenced_artifacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Artifact keys referenced from session pinned artifacts.",
                },
                "clarification_question": {
                    "type": "string",
                    "description": "Question asked when mode is CLARIFY.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score between 0.0 and 1.0.",
                },
            },
            "required": ["mode"],
        }
