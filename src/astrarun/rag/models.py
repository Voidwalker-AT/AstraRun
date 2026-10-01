"""Data models and schemas for the AstraRun Hybrid RAG & Memory Subsystem.

Defines document chunks, provenance records, retrieval queries and results,
progressive disclosure skill representations, and episodic memory structures.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocType(str, Enum):
    """Document and chunk classification types."""
    CODE = "CODE"
    MARKDOWN = "MARKDOWN"
    JSON = "JSON"
    CONFIG = "CONFIG"
    LOG = "LOG"
    SKILL = "SKILL"
    EPISODIC = "EPISODIC"
    TEXT = "TEXT"


class TrustLevel(str, Enum):
    """Security trust classifications for indexed content."""
    TRUSTED_LOCAL = "TRUSTED_LOCAL"          # Local code, verified configs
    VERIFIED_SKILL = "VERIFIED_SKILL"        # Operator approved SKILL.md
    UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"  # Scraped text, logs, third-party content


class RetrievalMode(str, Enum):
    """Query execution modes."""
    LEXICAL = "LEXICAL"      # Exact token / BM25 FTS5 match
    SEMANTIC = "SEMANTIC"    # Dense vector cosine similarity
    HYBRID = "HYBRID"        # Reciprocal Rank Fusion (RRF)


class SkillTier(str, Enum):
    """Hermes-style 3-tier progressive skill disclosure."""
    TIER_1_CATALOG = "TIER_1_CATALOG"      # Name + 1-sentence description (in system prompt)
    TIER_2_SCHEMA = "TIER_2_SCHEMA"        # Parameter JSON schema (injected on skill selection)
    TIER_3_EXECUTION = "TIER_3_EXECUTION"  # Executable workflow / script (loaded only on run)


class ChunkMetadata(BaseModel):
    """Structural metadata associated with a document chunk."""
    file_path: str = ""
    file_name: str = ""
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    symbol_name: Optional[str] = None
    symbol_type: Optional[str] = None  # e.g., "function", "class", "section"
    language: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ProvenanceRecord(BaseModel):
    """Cryptographic provenance and indexing audit information."""
    entity_id: str
    entity_type: str = "chunk"
    source_path: str
    content_hash: str
    indexed_at: float = Field(default_factory=time.time)
    trust_level: TrustLevel = TrustLevel.TRUSTED_LOCAL


class DocumentChunk(BaseModel):
    """Atomic indexable unit of knowledge across code, docs, and skills."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    doc_type: DocType = DocType.TEXT
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)
    trust_level: TrustLevel = TrustLevel.TRUSTED_LOCAL
    token_count: int = 0
    embedding: Optional[List[float]] = None
    provenance: Optional[ProvenanceRecord] = None


class RetrievedDocument(BaseModel):
    """A ranked search result returned from the retrieval subsystem."""
    chunk_id: str
    source: str
    content: str
    score: float
    doc_type: DocType
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)
    trust_level: TrustLevel = TrustLevel.TRUSTED_LOCAL
    lexical_rank: Optional[int] = None
    semantic_rank: Optional[int] = None


class RetrievalQuery(BaseModel):
    """Structured query specification passed to RetrievalRouter."""
    text: str
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = 5
    filter_doc_types: Optional[List[DocType]] = None
    scope_path: Optional[str] = None


class SkillDefinition(BaseModel):
    """Unified definition for a reusable skill supporting progressive disclosure."""
    id: str
    name: str
    one_sentence_description: str
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    execution_type: str = "WORKFLOW"  # "WORKFLOW", "PYTHON_SNIPPET", "SHELL_COMMAND"
    executable_content: str = ""
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    tags: List[str] = Field(default_factory=list)
    trust_level: TrustLevel = TrustLevel.VERIFIED_SKILL
    source_file: Optional[str] = None

    def to_tier_1_catalog(self) -> Dict[str, str]:
        """Compact catalog entry for prompt budget optimization (~15-20 tokens)."""
        return {
            "name": self.name,
            "description": self.one_sentence_description,
            "risk": self.risk_level,
        }

    def to_tier_2_schema(self) -> Dict[str, Any]:
        """Detailed schema injected when the skill is selected by the planner."""
        return {
            "name": self.name,
            "description": self.one_sentence_description,
            "parameters": self.parameters_schema,
            "risk_level": self.risk_level,
            "execution_type": self.execution_type,
        }


class EpisodicTrajectory(BaseModel):
    """Structured record of a completed task trajectory stored for episodic recall."""
    task_id: str
    goal: str
    plan_summary: str
    status: str  # "SUCCESS", "FAILED", "ABORTED"
    step_count: int
    final_outcome: str
    error_message: Optional[str] = None
    recorded_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)
