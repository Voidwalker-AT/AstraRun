"""AstraRun Hybrid RAG & Memory Subsystem.

Combines relational SQLite storage, FTS5 lexical BM25 retrieval, in-process
dense VectorIndex (BGE-small ONNX on CPU), Reciprocal Rank Fusion (RRF),
Hermes-style 3-tier progressive skill disclosure, and untrusted XML containment.
"""

from __future__ import annotations

from astrarun.rag.context import ContextBuilder
from astrarun.rag.embeddings import EmbeddingProvider
from astrarun.rag.indexer import WorkspaceIndexer
from astrarun.rag.models import (
    ChunkMetadata,
    DocType,
    DocumentChunk,
    EpisodicTrajectory,
    ProvenanceRecord,
    RetrievalMode,
    RetrievalQuery,
    RetrievedDocument,
    SkillDefinition,
    SkillTier,
    TrustLevel,
)
from astrarun.rag.router import RetrievalRouter
from astrarun.rag.skills import SkillRegistry, SkillRetriever
from astrarun.rag.store import MemoryStore
from astrarun.rag.vector import VectorIndex
from astrarun.rag.worker import EmbeddingWorker

__all__ = [
    "DocType",
    "TrustLevel",
    "RetrievalMode",
    "SkillTier",
    "ChunkMetadata",
    "ProvenanceRecord",
    "DocumentChunk",
    "RetrievedDocument",
    "RetrievalQuery",
    "SkillDefinition",
    "EpisodicTrajectory",
    "VectorIndex",
    "EmbeddingProvider",
    "EmbeddingWorker",
    "MemoryStore",
    "RetrievalRouter",
    "ContextBuilder",
    "WorkspaceIndexer",
    "SkillRegistry",
    "SkillRetriever",
]
