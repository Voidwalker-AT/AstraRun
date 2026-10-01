"""Unified embedded MemoryStore for AstraRun Hybrid RAG.

Houses relational state, FTS5 lexical index, compact VectorIndex,
episodic trajectories, and provenance records in a local SQLite database.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.rag.models import (
    ChunkMetadata,
    DocType,
    DocumentChunk,
    EpisodicTrajectory,
    ProvenanceRecord,
    RetrievedDocument,
    TrustLevel,
)
from astrarun.rag.vector import VectorIndex

logger = get_logger("astrarun.rag.store")


class MemoryStore:
    """
    Embedded storage engine combining relational SQLite tables, FTS5 lexical search,
    and an in-memory dense VectorIndex.
    """

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        vector_index: Optional[VectorIndex] = None,
    ):
        self.db_path = Path(db_path) if db_path else Path(":memory:")
        self.vector_index = vector_index or VectorIndex(dimension=384)
        self._lock = threading.RLock()
        self._is_memory = str(self.db_path) == ":memory:"

        if not self._is_memory and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        if not self._is_memory:
            self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_database()

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def _init_database(self) -> None:
        """Initialize relational and FTS5 schema."""
        with self._lock:
            with self._conn:
                # 1. Relational chunks table
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chunks (
                        id TEXT PRIMARY KEY,
                        source_path TEXT NOT NULL,
                        doc_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        token_count INTEGER NOT NULL DEFAULT 0,
                        trust_level TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    """
                )
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_path);")
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_type ON chunks(doc_type);")

                # 2. FTS5 Virtual Table for Lexical Search
                self._conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        source_path,
                        symbol_name,
                        doc_type,
                        content,
                        tokenize = 'unicode61 remove_diacritics 2'
                    );
                    """
                )

                # 3. Episodic Trajectories table
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS episodic_trajectories (
                        task_id TEXT PRIMARY KEY,
                        goal TEXT NOT NULL,
                        plan_summary TEXT NOT NULL,
                        status TEXT NOT NULL,
                        step_count INTEGER NOT NULL,
                        final_outcome TEXT NOT NULL,
                        error_message TEXT,
                        recorded_at REAL NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    );
                    """
                )
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_status ON episodic_trajectories(status);")

                # 4. Provenance and File Hashes table
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS provenance (
                        entity_id TEXT PRIMARY KEY,
                        entity_type TEXT NOT NULL,
                        source_path TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        indexed_at REAL NOT NULL,
                        trust_level TEXT NOT NULL
                    );
                    """
                )
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_provenance_path ON provenance(source_path);")

    def insert_chunk(self, chunk: DocumentChunk) -> None:
        """Insert or replace a document chunk and register its embedding."""
        with self._lock:
            now = time.time()
            meta_json = json.dumps(chunk.metadata.model_dump())
            with self._conn:
                # Upsert chunk record
                self._conn.execute(
                    """
                    INSERT INTO chunks (id, source_path, doc_type, content, token_count, trust_level, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_path = excluded.source_path,
                        doc_type = excluded.doc_type,
                        content = excluded.content,
                        token_count = excluded.token_count,
                        trust_level = excluded.trust_level,
                        metadata_json = excluded.metadata_json,
                        updated_at = excluded.updated_at;
                    """,
                    (
                        chunk.id,
                        chunk.metadata.file_path or "",
                        chunk.doc_type.value,
                        chunk.content,
                        chunk.token_count,
                        chunk.trust_level.value,
                        meta_json,
                        now,
                        now,
                    ),
                )

                # Delete existing FTS record if any, then insert
                self._conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?;", (chunk.id,))
                self._conn.execute(
                    """
                    INSERT INTO chunks_fts (chunk_id, source_path, symbol_name, doc_type, content)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (
                        chunk.id,
                        chunk.metadata.file_path or "",
                        chunk.metadata.symbol_name or "",
                        chunk.doc_type.value,
                        chunk.content,
                    ),
                )

                # Provenance tracking
                if chunk.provenance:
                    self._conn.execute(
                        """
                        INSERT OR REPLACE INTO provenance (entity_id, entity_type, source_path, content_hash, indexed_at, trust_level)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (
                            chunk.provenance.entity_id or chunk.id,
                            chunk.provenance.entity_type,
                            chunk.provenance.source_path,
                            chunk.provenance.content_hash,
                            chunk.provenance.indexed_at,
                            chunk.provenance.trust_level.value,
                        ),
                    )

            # Register in vector index if embedding is provided
            if chunk.embedding is not None:
                self.vector_index.add(chunk.id, chunk.embedding)

    def get_chunk(self, chunk_id: str) -> Optional[DocumentChunk]:
        """Retrieve a chunk by ID."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM chunks WHERE id = ?;", (chunk_id,)).fetchone()
            if not row:
                return None
            meta_dict = json.loads(row["metadata_json"])
            metadata = ChunkMetadata(**meta_dict)
            emb = self.vector_index.get(chunk_id)
            return DocumentChunk(
                id=row["id"],
                content=row["content"],
                doc_type=DocType(row["doc_type"]),
                metadata=metadata,
                trust_level=TrustLevel(row["trust_level"]),
                token_count=row["token_count"],
                embedding=emb.tolist() if emb is not None else None,
            )

    def delete_chunks_by_source(self, source_path: str) -> int:
        """Delete all chunks originating from a source file."""
        with self._lock:
            rows = self._conn.execute("SELECT id FROM chunks WHERE source_path = ?;", (source_path,)).fetchall()
            chunk_ids = [r["id"] for r in rows]
            if not chunk_ids:
                return 0

            with self._conn:
                for cid in chunk_ids:
                    self._conn.execute("DELETE FROM chunks WHERE id = ?;", (cid,))
                    self._conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?;", (cid,))
                    self.vector_index.remove(cid)
                self._conn.execute("DELETE FROM provenance WHERE source_path = ?;", (source_path,))
            return len(chunk_ids)

    def search_lexical(
        self,
        query: str,
        top_k: int = 5,
        filter_doc_types: Optional[List[DocType]] = None,
    ) -> List[RetrievedDocument]:
        """
        Execute BM25 lexical search over FTS5 virtual table.
        Cleanly escapes query tokens to avoid FTS5 syntax errors.
        """
        clean_tokens = [t.strip().replace('"', '""') for t in query.split() if t.strip()]
        if not clean_tokens:
            return []

        # Formulate safe quoted token match expression
        fts_query = " ".join(f'"{t}"' for t in clean_tokens)

        with self._lock:
            try:
                sql = """
                    SELECT f.chunk_id, f.source_path, f.doc_type, f.content, bm25(chunks_fts) as rank_score,
                           c.metadata_json, c.trust_level
                    FROM chunks_fts f
                    JOIN chunks c ON f.chunk_id = c.id
                    WHERE chunks_fts MATCH ?
                """
                params: List[Any] = [fts_query]

                if filter_doc_types:
                    placeholders = ",".join("?" for _ in filter_doc_types)
                    sql += f" AND f.doc_type IN ({placeholders})"
                    params.extend([dt.value for dt in filter_doc_types])

                # Note: In SQLite FTS5 bm25(), lower score is better (more negative/closer to 0)
                sql += " ORDER BY rank_score ASC LIMIT ?;"
                params.append(top_k)

                rows = self._conn.execute(sql, params).fetchall()
                results: List[RetrievedDocument] = []
                for rank_idx, row in enumerate(rows, start=1):
                    meta = ChunkMetadata(**json.loads(row["metadata_json"]))
                    # Invert BM25 score so higher is better for ranking consistency
                    normalized_score = 1.0 / (1.0 + abs(float(row["rank_score"])))
                    results.append(
                        RetrievedDocument(
                            chunk_id=row["chunk_id"],
                            source=row["source_path"],
                            content=row["content"],
                            score=normalized_score,
                            doc_type=DocType(row["doc_type"]),
                            metadata=meta,
                            trust_level=TrustLevel(row["trust_level"]),
                            lexical_rank=rank_idx,
                        )
                    )
                return results
            except sqlite3.OperationalError as e:
                logger.warning("FTS5 lexical search query '%s' failed: %s", query, e)
                return []

    def search_semantic(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_doc_types: Optional[List[DocType]] = None,
    ) -> List[RetrievedDocument]:
        """
        Execute dense vector search against VectorIndex and enrich results with SQLite metadata.
        """
        vector_results = self.vector_index.search(query_vector, top_k=top_k * 2)
        if not vector_results:
            return []

        with self._lock:
            results: List[RetrievedDocument] = []
            rank = 1
            for chunk_id, sim_score in vector_results:
                row = self._conn.execute("SELECT * FROM chunks WHERE id = ?;", (chunk_id,)).fetchone()
                if not row:
                    continue

                doc_type = DocType(row["doc_type"])
                if filter_doc_types and doc_type not in filter_doc_types:
                    continue

                meta = ChunkMetadata(**json.loads(row["metadata_json"]))
                results.append(
                    RetrievedDocument(
                        chunk_id=chunk_id,
                        source=row["source_path"],
                        content=row["content"],
                        score=sim_score,
                        doc_type=doc_type,
                        metadata=meta,
                        trust_level=TrustLevel(row["trust_level"]),
                        semantic_rank=rank,
                    )
                )
                rank += 1
                if len(results) >= top_k:
                    break
            return results

    def record_trajectory(self, trajectory: EpisodicTrajectory) -> None:
        """Record a completed episodic task trajectory."""
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO episodic_trajectories 
                    (task_id, goal, plan_summary, status, step_count, final_outcome, error_message, recorded_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        trajectory.task_id,
                        trajectory.goal,
                        trajectory.plan_summary,
                        trajectory.status,
                        trajectory.step_count,
                        trajectory.final_outcome,
                        trajectory.error_message,
                        trajectory.recorded_at,
                        json.dumps(trajectory.metadata),
                    ),
                )

    def get_trajectories(self, limit: int = 10, status: Optional[str] = None) -> List[EpisodicTrajectory]:
        """Retrieve recent episodic trajectories."""
        with self._lock:
            sql = "SELECT * FROM episodic_trajectories"
            params = []
            if status:
                sql += " WHERE status = ?"
                params.append(status)
            sql += " ORDER BY recorded_at DESC LIMIT ?;"
            params.append(limit)

            rows = self._conn.execute(sql, params).fetchall()
            results = []
            for r in rows:
                results.append(
                    EpisodicTrajectory(
                        task_id=r["task_id"],
                        goal=r["goal"],
                        plan_summary=r["plan_summary"],
                        status=r["status"],
                        step_count=r["step_count"],
                        final_outcome=r["final_outcome"],
                        error_message=r["error_message"],
                        recorded_at=r["recorded_at"],
                        metadata=json.loads(r["metadata_json"]),
                    )
                )
            return results

    def get_provenance(self, source_path: str) -> Optional[ProvenanceRecord]:
        """Retrieve provenance record for a given source path."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM provenance WHERE source_path = ?;", (source_path,)).fetchone()
            if not row:
                return None
            return ProvenanceRecord(
                entity_id=row["entity_id"],
                entity_type=row["entity_type"],
                source_path=row["source_path"],
                content_hash=row["content_hash"],
                indexed_at=row["indexed_at"],
                trust_level=TrustLevel(row["trust_level"]),
            )
