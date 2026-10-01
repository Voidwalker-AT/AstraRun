"""Compact in-process dense vector index for AstraRun Hybrid RAG.

Provides thread-safe vectorized cosine similarity search using numpy,
with zero external database servers, low RAM footprint, and binary serialization.
"""

from __future__ import annotations

import io
import threading
from typing import Dict, List, Optional, Set, Tuple
import numpy as np


class VectorIndex:
    """
    In-memory dense vector index utilizing vectorized dot product over L2-normalized embeddings.
    Thread-safe and designed for sub-millisecond local retrieval.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self._lock = threading.RLock()
        self._id_to_idx: Dict[str, int] = {}
        self._idx_to_id: List[str] = []
        # Matrix of shape (N, dimension)
        self._matrix: np.ndarray = np.empty((0, self.dimension), dtype=np.float32)

    def size(self) -> int:
        """Return the number of vectors stored in the index."""
        with self._lock:
            return len(self._idx_to_id)

    def add(self, entity_id: str, vector: List[float] | np.ndarray) -> None:
        """Add or replace a single vector in the index."""
        vec = np.asarray(vector, dtype=np.float32)
        if vec.shape != (self.dimension,):
            raise ValueError(f"Vector dimension mismatch: expected {self.dimension}, got {vec.shape}")

        # Normalize to unit length
        norm = np.linalg.norm(vec)
        if norm > 1e-12:
            vec = vec / norm
        else:
            vec = np.zeros_like(vec)

        with self._lock:
            if entity_id in self._id_to_idx:
                idx = self._id_to_idx[entity_id]
                self._matrix[idx] = vec
            else:
                idx = len(self._idx_to_id)
                self._id_to_idx[entity_id] = idx
                self._idx_to_id.append(entity_id)
                if self._matrix.shape[0] == 0:
                    self._matrix = np.array([vec], dtype=np.float32)
                else:
                    self._matrix = np.vstack([self._matrix, vec])

    def add_batch(self, items: List[Tuple[str, List[float] | np.ndarray]]) -> None:
        """Efficiently batch-insert vectors into the index."""
        if not items:
            return

        with self._lock:
            for entity_id, vector in items:
                self.add(entity_id, vector)

    def remove(self, entity_id: str) -> bool:
        """Remove an entity vector by ID."""
        with self._lock:
            if entity_id not in self._id_to_idx:
                return False

            idx = self._id_to_idx.pop(entity_id)
            self._idx_to_id.pop(idx)
            self._matrix = np.delete(self._matrix, idx, axis=0)

            # Re-index remaining entities
            for i, remaining_id in enumerate(self._idx_to_id):
                self._id_to_idx[remaining_id] = i
            return True

    def get(self, entity_id: str) -> Optional[np.ndarray]:
        """Retrieve stored vector for an entity ID."""
        with self._lock:
            idx = self._id_to_idx.get(entity_id)
            if idx is not None and idx < self._matrix.shape[0]:
                return self._matrix[idx].copy()
            return None

    def search(
        self,
        query_vector: List[float] | np.ndarray,
        top_k: int = 5,
        filter_ids: Optional[Set[str]] = None,
    ) -> List[Tuple[str, float]]:
        """
        Perform cosine similarity search against indexed vectors.
        Returns sorted list of (entity_id, similarity_score).
        """
        with self._lock:
            if self._matrix.shape[0] == 0:
                return []

            q = np.asarray(query_vector, dtype=np.float32)
            norm = np.linalg.norm(q)
            if norm > 1e-12:
                q = q / norm
            else:
                return []

            # Cosine similarity for normalized vectors is direct dot product
            scores = np.dot(self._matrix, q)

            # Filter candidates if requested
            if filter_ids is not None:
                valid_mask = np.array(
                    [eid in filter_ids for eid in self._idx_to_id],
                    dtype=bool,
                )
                if not np.any(valid_mask):
                    return []
                # Invalidate non-filtered scores
                scores = np.where(valid_mask, scores, -1e9)

            # Retrieve top_k indices
            k = min(top_k, len(self._idx_to_id))
            top_indices = np.argsort(scores)[::-1][:k]

            results = []
            for idx in top_indices:
                score = float(scores[idx])
                if score <= -1e8:
                    continue
                results.append((self._idx_to_id[idx], score))
            return results

    def clear(self) -> None:
        """Clear all entries from the index."""
        with self._lock:
            self._id_to_idx.clear()
            self._idx_to_id.clear()
            self._matrix = np.empty((0, self.dimension), dtype=np.float32)

    def serialize(self) -> bytes:
        """Serialize index matrix and ID lookup to compact binary bytes."""
        with self._lock:
            buffer = io.BytesIO()
            np.savez_compressed(
                buffer,
                ids=np.array(self._idx_to_id),
                matrix=self._matrix,
                dimension=np.array([self.dimension]),
            )
            return buffer.getvalue()

    def deserialize(self, data: bytes) -> None:
        """Restore index state from serialized binary bytes."""
        if not data:
            return
        with self._lock:
            buffer = io.BytesIO(data)
            loaded = np.load(buffer, allow_pickle=False)
            self.dimension = int(loaded["dimension"][0])
            self._idx_to_id = loaded["ids"].tolist()
            self._matrix = loaded["matrix"].astype(np.float32)
            self._id_to_idx = {eid: idx for idx, eid in enumerate(self._idx_to_id)}
