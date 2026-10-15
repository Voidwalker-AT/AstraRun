"""Typed event stream for AstraRun 1.0 conversation sessions and intelligence spine.

Inspired by OpenHands structured event logging without chain-of-thought leakage.
Invariant: Never persist hidden model reasoning or private chain-of-thought tokens.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(str, Enum):
    """Enumeration of typed event classes in the session event stream."""
    USER_TURN = "USER_TURN"
    WORLD_OBSERVATION = "WORLD_OBSERVATION"
    REASONING_DECISION = "REASONING_DECISION"
    TOOL_CALL = "TOOL_CALL"
    TOOL_OBSERVATION = "TOOL_OBSERVATION"
    VERIFICATION = "VERIFICATION"
    RECOVERY = "RECOVERY"
    ASSISTANT_RESPONSE = "ASSISTANT_RESPONSE"
    TURN_COMPLETED = "TURN_COMPLETED"
    KNOWLEDGE_SUFFICIENCY_EVALUATED = "KNOWLEDGE_SUFFICIENCY_EVALUATED"
    INFORMATION_NEED_CREATED = "INFORMATION_NEED_CREATED"
    ACQUISITION_PLAN_CREATED = "ACQUISITION_PLAN_CREATED"


@dataclass
class SessionEvent:
    """Base class for all session stream events."""
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    session_id: str = ""
    turn_id: str = ""
    timestamp: float = field(default_factory=time.time)
    event_type: EventType = EventType.USER_TURN

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


@dataclass
class UserTurnEvent(SessionEvent):
    """User input received for this turn."""
    user_text: str = ""
    origin: str = "LAUNCHER"
    event_type: EventType = field(default=EventType.USER_TURN, init=False)


@dataclass
class WorldObservationEvent(SessionEvent):
    """Compact observation of the desktop environment."""
    foreground_app: str = ""
    foreground_pid: Optional[int] = None
    visible_window_count: int = 0
    modal_dialog_active: bool = False
    task_id: Optional[str] = None
    event_type: EventType = field(default=EventType.WORLD_OBSERVATION, init=False)


@dataclass
class ReasoningDecisionEvent(SessionEvent):
    """
    Structured outcome of TurnReasoner or FastTrack.
    
    Invariant: Stores only structured facts (mode, capability IDs, args, goal summary).
    Never stores private model chain-of-thought tokens.
    """
    decision_mode: str = "DIRECT_ANSWER"
    selected_capability_ids: List[str] = field(default_factory=list)
    structured_arguments: Dict[str, Any] = field(default_factory=dict)
    goal_summary: str = ""
    reason_code: str = ""
    model_role: str = ""
    confidence: float = 1.0
    task_id: Optional[str] = None
    event_type: EventType = field(default=EventType.REASONING_DECISION, init=False)


@dataclass
class ToolCallEvent(SessionEvent):
    """Governed tool invocation intent passed to ExecutionBroker."""
    capability_id: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    step_id: Optional[str] = None
    risk_level: str = "LOW"
    event_type: EventType = field(default=EventType.TOOL_CALL, init=False)


@dataclass
class ToolObservationEvent(SessionEvent):
    """Compact structured result of governed capability execution."""
    capability_id: str = ""
    success: bool = True
    output_summary: str = ""
    verified_path: Optional[str] = None
    bytes_written: Optional[int] = None
    postcondition_result: Optional[str] = None
    task_id: Optional[str] = None
    step_id: Optional[str] = None
    error: Optional[str] = None
    event_type: EventType = field(default=EventType.TOOL_OBSERVATION, init=False)


@dataclass
class VerificationEvent(SessionEvent):
    """StepVerifier or CompletionGate postcondition assessment."""
    target: str = ""
    strategy: str = ""
    verified: bool = False
    details: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    step_id: Optional[str] = None
    event_type: EventType = field(default=EventType.VERIFICATION, init=False)


@dataclass
class RecoveryEvent(SessionEvent):
    """Bounded recovery action triggered on tool or verification failure."""
    failure_class: str = ""
    replan_decision: str = ""
    pre_state: Dict[str, Any] = field(default_factory=dict)
    post_state: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    step_id: Optional[str] = None
    event_type: EventType = field(default=EventType.RECOVERY, init=False)


@dataclass
class AssistantResponseEvent(SessionEvent):
    """Final assistant textual response presented to the user."""
    response_text: str = ""
    has_artifacts: bool = False
    event_type: EventType = field(default=EventType.ASSISTANT_RESPONSE, init=False)


@dataclass
class TurnCompletedEvent(SessionEvent):
    """Lifecycle event marking turn termination and commitment."""
    turn_status: str = "SUCCESS"  # SUCCESS, BLOCKED, PAUSED_CONFIRMATION, FAILED, CANCELLED
    duration_s: float = 0.0
    task_id: Optional[str] = None
    event_type: EventType = field(default=EventType.TURN_COMPLETED, init=False)


@dataclass
class KnowledgeSufficiencyEvaluatedEvent(SessionEvent):
    """Outcome of pre-reasoning knowledge sufficiency evaluation."""
    is_sufficient: bool = True
    reason: str = "SUFFICIENT_INTERNAL_KNOWLEDGE"
    confidence: float = 1.0
    missing_aspects: List[str] = field(default_factory=list)
    explanation: str = ""
    task_id: Optional[str] = None
    event_type: EventType = field(default=EventType.KNOWLEDGE_SUFFICIENCY_EVALUATED, init=False)


@dataclass
class InformationNeedCreatedEvent(SessionEvent):
    """Structured information need identified by InformationAcquisitionPlanner."""
    need_id: str = ""
    description: str = ""
    need_type: str = "FACTUAL"
    freshness: str = "STATIC"
    authority: str = "ANY_REASONABLE"
    priority: int = 1
    privacy_sensitive: bool = False
    task_id: Optional[str] = None
    event_type: EventType = field(default=EventType.INFORMATION_NEED_CREATED, init=False)


@dataclass
class AcquisitionPlanCreatedEvent(SessionEvent):
    """Structured information acquisition plan formulated before execution."""
    plan_id: str = ""
    need_count: int = 0
    evidence_request_count: int = 0
    target_sources: List[str] = field(default_factory=list)
    user_summary: str = ""
    task_id: Optional[str] = None
    event_type: EventType = field(default=EventType.ACQUISITION_PLAN_CREATED, init=False)
