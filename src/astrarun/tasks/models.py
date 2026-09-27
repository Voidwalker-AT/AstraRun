"""Strongly typed domain models and finite state machine for AstraRun Task Runtime."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class InvalidStateTransitionError(Exception):
    """Raised when an illegal TaskStatus state transition is attempted."""
    pass


class TaskCancelledError(Exception):
    """Raised when an operation is aborted via a cancellation token."""
    pass


class TaskStatus(str, Enum):
    """Finite states of a Task lifecycle."""
    CREATED = "CREATED"
    PARSING = "PARSING"
    RESOLVING = "RESOLVING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"
    WAITING_USER = "WAITING_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    INTERRUPTED = "INTERRUPTED"

    @property
    def is_terminal(self) -> bool:
        """Return True if the status represents a final, immutable state."""
        return self in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.BLOCKED,
            TaskStatus.PARTIALLY_COMPLETED,
            TaskStatus.INTERRUPTED,
        }

    @property
    def is_waiting(self) -> bool:
        """Return True if the task is suspended waiting for external user input."""
        return self in {
            TaskStatus.WAITING_CONFIRMATION,
            TaskStatus.WAITING_CLARIFICATION,
            TaskStatus.WAITING_USER,
        }

    @property
    def is_active(self) -> bool:
        """Return True if the task is currently active or transitioning."""
        return not self.is_terminal and not self.is_waiting


# Strict State Transition Validation Table
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {
        TaskStatus.PARSING,
        TaskStatus.RESOLVING,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.PARSING: {
        TaskStatus.RESOLVING,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.RESOLVING: {
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.READY: {
        TaskStatus.RUNNING,
        TaskStatus.WAITING_CONFIRMATION,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.BLOCKED,
        TaskStatus.PARTIALLY_COMPLETED,
        TaskStatus.WAITING_CONFIRMATION,
        TaskStatus.WAITING_CLARIFICATION,
        TaskStatus.WAITING_USER,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.WAITING_CONFIRMATION: {
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.WAITING_CLARIFICATION: {
        TaskStatus.RESOLVING,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.WAITING_USER: {
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.INTERRUPTED,
    },
    # Terminal States: No transitions allowed
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.BLOCKED: set(),
    TaskStatus.PARTIALLY_COMPLETED: set(),
    TaskStatus.INTERRUPTED: set(),
}


def validate_transition(current: TaskStatus, target: TaskStatus) -> None:
    """
    Validate that transition from current to target status is strictly allowed.
    Raises InvalidStateTransitionError if illegal.
    """
    if current == target:
        return
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"Illegal task state transition: {current.value} -> {target.value}. "
            f"Allowed next states: {[s.value for s in allowed]}"
        )


class TaskEventType(str, Enum):
    """Categorical types of Task Events reflecting observable runtime occurrences."""
    TASK_CREATED = "TASK_CREATED"

    # Natural Language Understanding & Planning
    NLP_PARSE_STARTED = "NLP_PARSE_STARTED"
    NLP_PARSE_COMPLETED = "NLP_PARSE_COMPLETED"
    INTENT_RESOLVED = "INTENT_RESOLVED"

    # Entity Resolution
    ENTITY_RESOLUTION_STARTED = "ENTITY_RESOLUTION_STARTED"
    ENTITY_RESOLVED = "ENTITY_RESOLVED"
    ENTITY_AMBIGUOUS = "ENTITY_AMBIGUOUS"

    # Workflow Planning
    WORKFLOW_COMPILED = "WORKFLOW_COMPILED"

    # Safety Gating
    ACTION_GATE_ALLOW = "ACTION_GATE_ALLOW"
    ACTION_GATE_CONFIRM = "ACTION_GATE_CONFIRM"
    ACTION_GATE_CLARIFY = "ACTION_GATE_CLARIFY"
    ACTION_GATE_BLOCK = "ACTION_GATE_BLOCK"

    # Capability Execution
    CAPABILITY_STARTED = "CAPABILITY_STARTED"
    CAPABILITY_COMPLETED = "CAPABILITY_COMPLETED"
    CAPABILITY_FAILED = "CAPABILITY_FAILED"

    # Fact Observations
    OBSERVATION_RECORDED = "OBSERVATION_RECORDED"

    # User Interactive Gating
    CONFIRMATION_REQUESTED = "CONFIRMATION_REQUESTED"
    CONFIRMATION_ACCEPTED = "CONFIRMATION_ACCEPTED"
    CONFIRMATION_REJECTED = "CONFIRMATION_REJECTED"

    CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED"
    CLARIFICATION_RESOLVED = "CLARIFICATION_RESOLVED"

    # Workflow Orchestration
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    WORKFLOW_STEP_STARTED = "WORKFLOW_STEP_STARTED"
    WORKFLOW_STEP_COMPLETED = "WORKFLOW_STEP_COMPLETED"
    WORKFLOW_STEP_FAILED = "WORKFLOW_STEP_FAILED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"

    # Cancellation
    TASK_CANCEL_REQUESTED = "TASK_CANCEL_REQUESTED"
    TASK_CANCELLED = "TASK_CANCELLED"

    # Terminal Task Events
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_BLOCKED = "TASK_BLOCKED"
    TASK_INTERRUPTED = "TASK_INTERRUPTED"

    # Forward-looking placeholders (for v0.9+ Window/Computer-Use)
    WINDOW_FOCUSED = "WINDOW_FOCUSED"
    WINDOW_MOVED = "WINDOW_MOVED"
    REASONING_REQUESTED = "REASONING_REQUESTED"


@dataclass(frozen=True)
class TaskEvent:
    """
    Immutable record of an observable system occurrence during task processing.
    Represents ground-truth machine activity; never contains fabricated thinking.
    """
    id: str
    task_id: str
    type: TaskEventType
    title: str
    status: str = "SUCCESS"
    timestamp: float = field(default_factory=time.time)

    summary: Optional[str] = None

    capability_id: Optional[str] = None
    entity_ids: list[str] = field(default_factory=list)

    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "type": self.type.value,
            "status": self.status,
            "title": self.title,
            "summary": self.summary,
            "capability_id": self.capability_id,
            "entity_ids": list(self.entity_ids),
            "data": dict(self.data),
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskEvent:
        """Construct a TaskEvent from dictionary data."""
        return cls(
            id=d["id"],
            task_id=d["task_id"],
            timestamp=d["timestamp"],
            type=TaskEventType(d["type"]),
            status=d["status"],
            title=d["title"],
            summary=d.get("summary"),
            capability_id=d.get("capability_id"),
            entity_ids=d.get("entity_ids", []),
            data=d.get("data", {}),
            duration_ms=d.get("duration_ms"),
        )


@dataclass
class TaskError:
    """Structured error payload attached to failed or partially completed tasks."""
    code: str
    message: str
    capability: Optional[str] = None
    recoverable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "capability": self.capability,
            "recoverable": self.recoverable,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskError:
        return cls(
            code=d["code"],
            message=d["message"],
            capability=d.get("capability"),
            recoverable=d.get("recoverable", False),
        )


@dataclass
class TaskResult:
    """Final output bundle summarizing task execution outcomes."""
    task_id: str
    success: bool
    status: TaskStatus
    message: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    capabilities_used: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[TaskError] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "status": self.status.value,
            "message": self.message,
            "summary": self.summary,
            "data": dict(self.data),
            "capabilities_used": list(self.capabilities_used),
            "duration_ms": self.duration_ms,
            "error": self.error.to_dict() if self.error else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskResult:
        err = TaskError.from_dict(d["error"]) if d.get("error") else None
        return cls(
            task_id=d["task_id"],
            success=d["success"],
            status=TaskStatus(d["status"]),
            message=d["message"],
            summary=d["summary"],
            data=d.get("data", {}),
            capabilities_used=d.get("capabilities_used", []),
            duration_ms=d.get("duration_ms", 0.0),
            error=err,
        )


@dataclass
class Task:
    """
    First-class Task entity representing a discrete, trackable workstation operation.
    """
    id: str
    conversation_id: str

    request_text: Optional[str] = None
    request_hash: str = ""
    source: str = "launcher"

    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    status: TaskStatus = TaskStatus.CREATED
    events: list[TaskEvent] = field(default_factory=list)
    final_result: Optional[TaskResult] = None
    parent_task_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_hash and self.request_text:
            import hashlib
            self.request_hash = hashlib.sha256(self.request_text.strip().encode("utf-8")).hexdigest()

    def transition_to(self, new_status: TaskStatus) -> None:
        """Validate and apply a finite state transition."""
        validate_transition(self.status, new_status)
        self.status = new_status
        if new_status == TaskStatus.RUNNING and self.started_at is None:
            self.started_at = time.time()
        if new_status.is_terminal and self.completed_at is None:
            self.completed_at = time.time()

    def duration_ms(self) -> float:
        """Calculate active duration in milliseconds."""
        start = self.started_at or self.created_at
        end = self.completed_at or time.time()
        return max(0.0, (end - start) * 1000.0)

    def to_dict(self) -> dict[str, Any]:
        """Serialize Task to a dictionary."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "request_text": self.request_text,
            "request_hash": self.request_hash,
            "source": self.source,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "events": [e.to_dict() for e in self.events],
            "final_result": self.final_result.to_dict() if self.final_result else None,
            "parent_task_id": self.parent_task_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Task:
        """Construct a Task from dictionary representation."""
        events = [TaskEvent.from_dict(e) for e in d.get("events", [])]
        res = TaskResult.from_dict(d["final_result"]) if d.get("final_result") else None
        return cls(
            id=d["id"],
            conversation_id=d["conversation_id"],
            request_text=d.get("request_text"),
            request_hash=d["request_hash"],
            source=d.get("source", "launcher"),
            created_at=d["created_at"],
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            status=TaskStatus(d["status"]),
            events=events,
            final_result=res,
            parent_task_id=d.get("parent_task_id"),
            metadata=d.get("metadata", {}),
        )


@dataclass
class Conversation:
    """
    User-facing interaction thread grouping related tasks and follow-up commands.
    """
    id: str
    title: Optional[str]
    created_at: float
    updated_at: float
    status: str = "ACTIVE"
    task_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "task_ids": list(self.task_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Conversation:
        return cls(
            id=d["id"],
            title=d.get("title"),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            status=d.get("status", "ACTIVE"),
            task_ids=d.get("task_ids", []),
            metadata=d.get("metadata", {}),
        )


@dataclass
class ConversationMessage:
    """
    Individual message entry in a conversation thread.
    Can be from the USER, ASTRA_RESULT, CONFIRMATION, CLARIFICATION, or SYSTEM_STATUS.
    """
    id: str
    conversation_id: str
    sender: str  # "USER", "ASTRA_RESULT", "SYSTEM_STATUS", "CONFIRMATION", "CLARIFICATION"
    text: str
    timestamp: float
    task_id: Optional[str] = None
    data: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "task_id": self.task_id,
            "sender": self.sender,
            "text": self.text,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConversationMessage:
        return cls(
            id=d["id"],
            conversation_id=d["conversation_id"],
            task_id=d.get("task_id"),
            sender=d["sender"],
            text=d["text"],
            timestamp=d["timestamp"],
            data=d.get("data"),
        )
