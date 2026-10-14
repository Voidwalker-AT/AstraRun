"""Session store providing in-memory retention and reasoner context extraction."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.session.events import SessionEvent
from astrarun.session.models import ConversationSession, PinnedArtifact, TurnRecord

logger = get_logger("astrarun.session.store")


class SessionStore:
    """
    In-memory store for resident AstraRun conversation sessions.
    
    Provides fast lookup, session isolation, and bounded context extraction
    (last 4 turns + rolling summary + pinned artifacts).
    """

    _instance: Optional[SessionStore] = None

    def __init__(self) -> None:
        self._sessions: Dict[str, ConversationSession] = {}
        self._events: Dict[str, List[SessionEvent]] = {}  # session_id -> list of events

    @classmethod
    def get_instance(cls) -> SessionStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_session(self, session_id: Optional[str] = None) -> ConversationSession:
        sid = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        session = ConversationSession(session_id=sid)
        self._sessions[sid] = session
        self._events[sid] = []
        logger.debug("Created session %s", sid)
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: Optional[str] = None) -> ConversationSession:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create_session(session_id)

    def save_session(self, session: ConversationSession) -> None:
        self._sessions[session.session_id] = session

    def record_event(self, event: SessionEvent) -> None:
        sid = event.session_id
        if sid not in self._events:
            self._events[sid] = []
        self._events[sid].append(event)

    def get_events(self, session_id: str) -> List[SessionEvent]:
        return list(self._events.get(session_id, []))

    def get_reasoner_context(
        self,
        session: ConversationSession,
        max_turns: int = 4,
    ) -> Dict[str, Any]:
        """
        Extract bounded context for the turn reasoner:
        - Recent turns (chronological order)
        - Rolling summary
        - Pinned verified artifacts
        """
        recent = session.get_recent_turns(max_turns)
        return {
            "session_id": session.session_id,
            "rolling_summary": session.rolling_summary,
            "pinned_artifacts": {
                k: a.to_dict()
                for k, a in session.pinned_artifacts.items()
            },
            "recent_turns": [
                {
                    "turn_id": t.turn_id,
                    "user_text": t.user_text,
                    "assistant_text": t.assistant_text,
                    "decision_mode": t.decision_mode,
                    "verified": t.verified,
                    "artifacts": [art.to_dict() for art in t.artifacts],
                    "tool_observations": [
                        obs for obs in t.tool_observations
                    ],
                }
                for t in recent
            ],
        }

    def clear(self) -> None:
        """Clear all active sessions (used in test teardown)."""
        self._sessions.clear()
        self._events.clear()
