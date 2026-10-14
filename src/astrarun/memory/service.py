"""Authoritative Unified Memory Service for AstraRun.

Provides one canonical facade across all memory faculties:
MemoryService
├── working      (transient active context scratchpad)
├── episodic     (task histories, execution traces, failure modes)
├── semantic     (persistent verified user/system facts, entities)
├── procedural   (Hermes progressive skills and workflows)
└── workspace    (FTS5 lexical index & semantic workspace retrieval)

Callers access memory through clean abstractions; underlying SQLite, FTS5,
and Vector storage engines remain completely encapsulated.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from astrarun.core.paths import AstraPaths
from astrarun.memory.skills import SkillService, SkillDefinition

logger = logging.getLogger("astrarun.memory.service")


class WorkingMemory:
    """Transient in-memory scratchpad for the active interaction turn."""

    def __init__(self) -> None:
        self._context: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._context[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._context.get(key, default)

    def clear(self) -> None:
        self._context.clear()

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._context)


class EpisodicFaculty:
    """Episodic memory: records past task executions, plans, errors, and outcomes."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or (AstraPaths.data_dir() / "memory" / "episodic.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._store: Optional[Any] = None

    def _get_store(self) -> Any:
        if self._store is None:
            from astrarun.rag.store import MemoryStore
            self._store = MemoryStore(db_path=self.db_path)
        return self._store

    def record_episode(
        self,
        task_id: str,
        goal: str,
        plan_summary: str,
        status: str,
        step_count: int,
        final_outcome: str = "",
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store a completed episodic task trajectory."""
        from astrarun.rag.models import EpisodicTrajectory
        traj = EpisodicTrajectory(
            task_id=task_id,
            goal=goal,
            plan_summary=plan_summary,
            status=status,
            step_count=step_count,
            final_outcome=final_outcome,
            error_message=error_message,
            metadata=metadata or {},
        )
        self._get_store().record_trajectory(traj)

    def get_recent_episodes(self, limit: int = 10, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recent episodic trajectories."""
        trajs = self._get_store().get_trajectories(limit=limit, status=status)
        return [
            {
                "task_id": t.task_id,
                "goal": t.goal,
                "status": t.status,
                "step_count": t.step_count,
                "plan_summary": t.plan_summary,
                "final_outcome": t.final_outcome,
                "error": t.error_message,
            }
            for t in trajs
        ]


class SemanticFaculty:
    """Semantic memory: persistent verified user/system facts, entities, and preferences."""

    def __init__(self) -> None:
        self._store: Optional[Any] = None

    def _get_store(self) -> Any:
        if self._store is None:
            from astrarun.learning.memory import MemoryStore
            from astrarun.learning.persistence import LearningPersistence
            self._store = MemoryStore(persistence=LearningPersistence())
        return self._store

    def set_fact(
        self,
        namespace: str,
        key: str,
        value: str,
        target_type: str = "preference",
        pinned: bool = False,
    ) -> None:
        """Record or update a semantic fact with confidence calculation."""
        from astrarun.learning.models import MemoryNamespace
        ns = getattr(MemoryNamespace, namespace.upper(), MemoryNamespace.PREFERENCE)
        self._get_store().add_or_update_memory(
            namespace=ns,
            key=key,
            value=value,
            target_type=target_type,
            pinned=pinned,
        )

    def get_facts(self, key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve facts matching key."""
        mems = self._get_store().persistence.find_memories(key=key)
        return [
            {
                "key": m.key,
                "value": m.value,
                "confidence": m.confidence,
                "status": m.status.value,
            }
            for m in mems
        ]


class WorkspaceFaculty:
    """Workspace retrieval: indexes documents and provides lexical (FTS5) and vector retrieval."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or (AstraPaths.data_dir() / "memory" / "workspace.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._store: Optional[Any] = None

    def _get_store(self) -> Any:
        if self._store is None:
            from astrarun.rag.store import MemoryStore
            self._store = MemoryStore(db_path=self.db_path)
        return self._store

    def index_document(
        self,
        doc_id: str,
        source_path: str,
        content: str,
        doc_type: str = "file",
    ) -> None:
        """Index a document chunk into FTS5 lexical storage."""
        from astrarun.rag.models import ChunkMetadata, DocumentChunk, DocType, TrustLevel
        chunk = DocumentChunk(
            id=doc_id,
            source_path=source_path,
            doc_type=DocType.CODE,
            content=content,
            token_count=len(content.split()),
            trust_level=TrustLevel.TRUSTED_LOCAL,
            metadata=ChunkMetadata(source_path=source_path),
        )
        self._get_store().insert_chunk(chunk)

    def search_workspace(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Perform lexical FTS5 search across indexed workspace files."""
        results = self._get_store().search_lexical(query, top_k=top_k)
        return [
            {
                "chunk_id": r.chunk_id,
                "source": r.source,
                "content": r.content,
                "score": r.score,
            }
            for r in results
        ]


class MemoryService:
    """The authoritative single facade across all Astra memory faculties."""

    _instance: Optional[MemoryService] = None

    def __init__(self) -> None:
        self.working = WorkingMemory()
        self.episodic = EpisodicFaculty()
        self.semantic = SemanticFaculty()
        self.workspace = WorkspaceFaculty()
        self.procedural = SkillService()
        from astrarun.hermes.store import HermesKnowledgeStore
        self.hermes = HermesKnowledgeStore()

    @classmethod
    def get_instance(cls) -> MemoryService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
