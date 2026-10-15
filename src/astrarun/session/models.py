"""Data models for resident multi-turn conversation sessions and artifacts."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ArtifactKind(str, Enum):
    """Classification of an artifact created or tracked during a session."""
    FILE = "FILE"
    WINDOW = "WINDOW"
    APPLICATION = "APPLICATION"
    GENERATED_TEXT = "GENERATED_TEXT"
    CODE = "CODE"
    TOOL_RESULT = "TOOL_RESULT"
    EXPLANATION = "EXPLANATION"
    EXAMPLE = "EXAMPLE"
    DATA = "DATA"


@dataclass
class PinnedArtifact:
    """
    Strongly typed reference to a conversational or operational artifact.
    
    Invariant: An artifact is NOT verified merely because the model mentioned it.
    It must be independently verified by StepVerifier, filesystem check, or Win32 probe.
    """
    artifact_id: str
    kind: ArtifactKind
    display_name: str
    verified_identity: str = ""
    path: Optional[str] = None
    pid: Optional[int] = None
    hwnd: Optional[int] = None
    content_summary: Optional[str] = None
    content: Optional[str] = None
    topic: Optional[str] = None
    created_turn_id: str = ""
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PinnedArtifact:
        kind = ArtifactKind(data["kind"]) if isinstance(data["kind"], str) else data["kind"]
        return cls(
            artifact_id=data.get("artifact_id", ""),
            kind=kind,
            display_name=data.get("display_name", ""),
            verified_identity=data.get("verified_identity", ""),
            path=data.get("path"),
            pid=data.get("pid"),
            hwnd=data.get("hwnd"),
            content_summary=data.get("content_summary"),
            content=data.get("content"),
            topic=data.get("topic"),
            created_turn_id=data.get("created_turn_id", ""),
            verified=bool(data.get("verified", False)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class TurnRecord:
    """
    Complete immutable record of a single conversational turn.
    """
    turn_id: str
    timestamp: float
    user_text: str
    assistant_text: str
    decision_mode: str
    topic: Optional[str] = None
    conversational_artifacts: List[PinnedArtifact] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_observations: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[PinnedArtifact] = field(default_factory=list)
    verified: bool = False
    error_summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "decision_mode": self.decision_mode,
            "topic": self.topic,
            "conversational_artifacts": [a.to_dict() for a in self.conversational_artifacts],
            "tool_calls": list(self.tool_calls),
            "tool_observations": list(self.tool_observations),
            "artifacts": [a.to_dict() for a in self.artifacts],
            "verified": self.verified,
            "error_summary": self.error_summary,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TurnRecord:
        artifacts = [PinnedArtifact.from_dict(a) for a in data.get("artifacts", [])]
        conv_artifacts = [PinnedArtifact.from_dict(a) for a in data.get("conversational_artifacts", [])]
        return cls(
            turn_id=data["turn_id"],
            timestamp=data["timestamp"],
            user_text=data["user_text"],
            assistant_text=data["assistant_text"],
            decision_mode=data["decision_mode"],
            topic=data.get("topic"),
            conversational_artifacts=conv_artifacts,
            tool_calls=data.get("tool_calls", []),
            tool_observations=data.get("tool_observations", []),
            artifacts=artifacts,
            verified=bool(data.get("verified", False)),
            error_summary=data.get("error_summary"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ConversationSession:
    """
    Resident conversation session state.
    
    Contains history, rolling summary, pinned artifacts, active topic, and state flags.
    Does not store arbitrary global mutable state.
    """
    session_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turns: List[TurnRecord] = field(default_factory=list)
    active_topic: Optional[str] = None
    topic_history: List[str] = field(default_factory=list)
    rolling_summary: str = ""
    pinned_artifacts: Dict[str, PinnedArtifact] = field(default_factory=dict)
    active_task_id: Optional[str] = None
    active_clarification: Optional[str] = None
    active_confirmation: Optional[str] = None

    def set_active_topic(self, topic: str) -> None:
        """Set the active discussion topic and append to history if new."""
        clean = topic.strip()
        if not clean:
            return
        if self.active_topic != clean:
            self.topic_history.append(clean)
            self.active_topic = clean
            self.updated_at = time.time()

    def get_active_topic(self) -> Optional[str]:
        """Return the current active discussion topic."""
        return self.active_topic

    def add_turn(self, turn: TurnRecord) -> None:
        """Append a turn and update timestamp."""
        self.turns.append(turn)
        if turn.topic:
            self.set_active_topic(turn.topic)
        self.updated_at = time.time()

    def pin_artifact(self, key: str, artifact: PinnedArtifact) -> None:
        """Pin a verified artifact reference into the session."""
        self.pinned_artifacts[key] = artifact
        self.updated_at = time.time()

    def get_recent_turns(self, k: int = 4) -> List[TurnRecord]:
        """Return the most recent k turns in chronological order."""
        if k <= 0:
            return []
        return self.turns[-k:]

    def resolve_conversational_artifact(
        self,
        reference_query: str,
        expected_kind: Optional[ArtifactKind] = None,
    ) -> Optional[PinnedArtifact]:
        """
        Resolve a conversational reference ('that example', 'the explanation', 'it', 'the previous answer')
        against actual turn and artifact provenance rather than merely recent text.
        """
        q = reference_query.lower().strip()

        # 1. 'that example', 'the example', 'code example', 'numerical example'
        if "example" in q or "snippet" in q or expected_kind == ArtifactKind.EXAMPLE:
            # First search turns backwards matching active topic
            for turn in reversed(self.turns):
                for art in reversed(turn.conversational_artifacts):
                    if art.kind in (ArtifactKind.EXAMPLE, ArtifactKind.CODE):
                        if not self.active_topic or art.topic == self.active_topic:
                            return art
            # Check pinned artifacts matching active topic
            for art in reversed(list(self.pinned_artifacts.values())):
                if art.kind in (ArtifactKind.EXAMPLE, ArtifactKind.CODE):
                    if not self.active_topic or art.topic == self.active_topic:
                        return art
            # Fallback to any past example across turns
            for turn in reversed(self.turns):
                for art in reversed(turn.conversational_artifacts):
                    if art.kind in (ArtifactKind.EXAMPLE, ArtifactKind.CODE):
                        return art
            # Fallback to any pinned example
            for art in reversed(list(self.pinned_artifacts.values())):
                if art.kind in (ArtifactKind.EXAMPLE, ArtifactKind.CODE):
                    return art

        # 2. 'the explanation', 'that explanation', 'shorter explanation'
        if "explanation" in q or expected_kind == ArtifactKind.EXPLANATION:
            for turn in reversed(self.turns):
                for art in reversed(turn.conversational_artifacts):
                    if art.kind == ArtifactKind.EXPLANATION:
                        if not self.active_topic or art.topic == self.active_topic:
                            return art
            # Check pinned artifacts matching active topic
            for art in reversed(list(self.pinned_artifacts.values())):
                if art.kind == ArtifactKind.EXPLANATION:
                    if not self.active_topic or art.topic == self.active_topic:
                        return art
            for turn in reversed(self.turns):
                for art in reversed(turn.conversational_artifacts):
                    if art.kind == ArtifactKind.EXPLANATION:
                        return art
            for art in reversed(list(self.pinned_artifacts.values())):
                if art.kind == ArtifactKind.EXPLANATION:
                    return art

        # 3. 'the previous answer', 'last response', 'what you just said'
        if any(phrase in q for phrase in ("previous answer", "last response", "what you just said", "your answer")):
            for turn in reversed(self.turns):
                if turn.assistant_text and len(turn.assistant_text.strip()) > 0:
                    return PinnedArtifact(
                        artifact_id=f"art-prev-{turn.turn_id}",
                        kind=ArtifactKind.GENERATED_TEXT,
                        display_name="previous_answer",
                        verified_identity=turn.turn_id,
                        content=turn.assistant_text,
                        topic=turn.topic or self.active_topic,
                        created_turn_id=turn.turn_id,
                        verified=True,
                    )

        # 4. 'it', 'that', 'the file', 'that file' -> Check pinned file/app
        if any(w in q.split() for w in ("it", "that", "file", "the file", "that file")):
            last_file = self.pinned_artifacts.get("last_file")
            if last_file:
                return last_file
            last_app = self.pinned_artifacts.get("last_app")
            if last_app:
                return last_app

        # 5. Fallback: Check if there's any artifact matching active topic
        if self.active_topic:
            for turn in reversed(self.turns):
                if turn.topic == self.active_topic and turn.assistant_text:
                    return PinnedArtifact(
                        artifact_id=f"art-topic-{turn.turn_id}",
                        kind=ArtifactKind.GENERATED_TEXT,
                        display_name=f"{self.active_topic}_content",
                        verified_identity=turn.turn_id,
                        content=turn.assistant_text,
                        topic=self.active_topic,
                        created_turn_id=turn.turn_id,
                        verified=True,
                    )

        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turns": [t.to_dict() for t in self.turns],
            "active_topic": self.active_topic,
            "topic_history": list(self.topic_history),
            "rolling_summary": self.rolling_summary,
            "pinned_artifacts": {k: v.to_dict() for k, v in self.pinned_artifacts.items()},
            "active_task_id": self.active_task_id,
            "active_clarification": self.active_clarification,
            "active_confirmation": self.active_confirmation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConversationSession:
        turns = [TurnRecord.from_dict(t) for t in data.get("turns", [])]
        pinned = {
            k: PinnedArtifact.from_dict(v)
            for k, v in data.get("pinned_artifacts", {}).items()
        }
        return cls(
            session_id=data["session_id"],
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            turns=turns,
            active_topic=data.get("active_topic"),
            topic_history=list(data.get("topic_history", [])),
            rolling_summary=data.get("rolling_summary", ""),
            pinned_artifacts=pinned,
            active_task_id=data.get("active_task_id"),
            active_clarification=data.get("active_clarification"),
            active_confirmation=data.get("active_confirmation"),
        )
