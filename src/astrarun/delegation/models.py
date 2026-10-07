"""Data models and session tracking for Delegated Agent Orchestration.

All external AI outputs are classified as UNTRUSTED_ADVISORY content.
Astra retains sole execution, security, machine state, and completion authority.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ReviewStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECTED = "REJECTED"


@dataclass
class DelegateProposal:
    """Structured proposal extracted from advisory delegate output.
    
    Never executed blindly; must pass ActionGate, path safety, and Sandbox policy.
    """
    explanation: str = ""
    proposed_files: Dict[str, str] = field(default_factory=dict)
    proposed_patches: Dict[str, str] = field(default_factory=dict)
    proposed_commands: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    expected_result: str = ""
    review_status: ReviewStatus = ReviewStatus.UNKNOWN
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["review_status"] = self.review_status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DelegateProposal:
        d = dict(data)
        if "review_status" in d and isinstance(d["review_status"], str):
            d["review_status"] = ReviewStatus(d["review_status"])
        return cls(**d)


@dataclass
class DelegateTurn:
    """Single turn in a delegated interaction."""
    turn_number: int
    direction: str  # "OUTBOUND" (Astra -> Delegate) or "INBOUND" (Delegate -> Astra)
    content: str
    timestamp: float = field(default_factory=time.time)
    structured_payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DelegateTurn:
        return cls(**data)


@dataclass
class DelegateResponse:
    """Response returned from a DelegateProvider invocation."""
    raw_content: str
    proposal: DelegateProposal
    turn_number: int
    model_name: str = "unknown"
    latency_ms: float = 0.0
    provider_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_content": self.raw_content,
            "proposal": self.proposal.to_dict(),
            "turn_number": self.turn_number,
            "model_name": self.model_name,
            "latency_ms": self.latency_ms,
            "provider_metadata": self.provider_metadata,
        }


@dataclass
class DelegateSession:
    """Stateful tracking for an ongoing interaction with an external delegate.
    
    Astra maintains conversation continuity across turns, handles, and restarts.
    """
    session_id: str
    provider: str
    conversation_handle: str
    task_id: str
    objective: str
    turns: List[DelegateTurn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    trust_level: str = "UNTRUSTED_ADVISORY"
    context_budget: int = 16000
    max_turns: int = 5
    current_turn: int = 0
    state: str = "ACTIVE"  # "ACTIVE", "PAUSED", "COMPLETED", "FAILED"
    require_delegate_approval: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        provider: str,
        task_id: str,
        objective: str,
        conversation_handle: str = "",
        max_turns: int = 5,
        context_budget: int = 16000,
        require_delegate_approval: bool = False,
    ) -> DelegateSession:
        sid = f"delsess_{uuid.uuid4().hex[:8]}"
        handle = conversation_handle or f"conv_{uuid.uuid4().hex[:8]}"
        return cls(
            session_id=sid,
            provider=provider,
            conversation_handle=handle,
            task_id=task_id,
            objective=objective,
            max_turns=max_turns,
            context_budget=context_budget,
            require_delegate_approval=require_delegate_approval,
        )

    def add_outbound_turn(self, content: str, payload: Optional[Dict[str, Any]] = None) -> DelegateTurn:
        self.current_turn += 1
        turn = DelegateTurn(
            turn_number=self.current_turn,
            direction="OUTBOUND",
            content=content,
            timestamp=time.time(),
            structured_payload=payload,
        )
        self.turns.append(turn)
        self.last_active = turn.timestamp
        return turn

    def add_inbound_turn(self, content: str, proposal: Optional[DelegateProposal] = None) -> DelegateTurn:
        turn = DelegateTurn(
            turn_number=self.current_turn,
            direction="INBOUND",
            content=content,
            timestamp=time.time(),
            structured_payload=proposal.to_dict() if proposal else None,
        )
        self.turns.append(turn)
        self.last_active = turn.timestamp
        return turn

    @property
    def is_turn_budget_exhausted(self) -> bool:
        return self.current_turn >= self.max_turns

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "conversation_handle": self.conversation_handle,
            "task_id": self.task_id,
            "objective": self.objective,
            "turns": [t.to_dict() for t in self.turns],
            "created_at": self.created_at,
            "last_active": self.last_active,
            "trust_level": self.trust_level,
            "context_budget": self.context_budget,
            "max_turns": self.max_turns,
            "current_turn": self.current_turn,
            "state": self.state,
            "require_delegate_approval": self.require_delegate_approval,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DelegateSession:
        turns = [DelegateTurn.from_dict(t) for t in data.get("turns", [])]
        d = dict(data)
        d["turns"] = turns
        return cls(**d)

    def save(self, filepath: Path | str) -> None:
        """Persist session state for pause/resume continuity without secrets."""
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path | str) -> DelegateSession:
        """Load session state from disk for post-restart recovery."""
        p = Path(filepath)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls.from_dict(data)
