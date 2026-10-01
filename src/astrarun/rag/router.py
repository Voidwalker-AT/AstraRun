"""Model-independent RetrievalRouter for AstraRun Hybrid RAG.

Provides intelligent dispatch across LEXICAL (FTS5 BM25), SEMANTIC (dense vector),
and HYBRID (Reciprocal Rank Fusion - RRF) retrieval pipelines.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from astrarun.core.logging import get_logger
from astrarun.rag.embeddings import EmbeddingProvider
from astrarun.rag.models import (
    DocType,
    RetrievalMode,
    RetrievalQuery,
    RetrievedDocument,
)
from astrarun.rag.store import MemoryStore

logger = get_logger("astrarun.rag.router")

# Heuristics for detecting exact identifier queries
FILE_EXT_PATTERN = re.compile(r"\b[\w\-]+\.(py|json|md|txt|toml|yaml|yml|ps1|bat|cmd|log|ini|cfg)\b", re.IGNORECASE)
CAMEL_CASE_PATTERN = re.compile(r"\b[a-z]+[A-Z][a-zA-Z0-9]*\b")
SNAKE_CASE_PATTERN = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b", re.IGNORECASE)
QUOTED_PATTERN = re.compile(r'"([^"]*)"|\'([^\']*)\'')


class RetrievalRouter:
    """
    Directs queries to the optimal retrieval modality and fuses multi-modal rankings.
    """

    def __init__(
        self,
        store: MemoryStore,
        embeddings: EmbeddingProvider,
        rrf_k: int = 60,
    ):
        self.store = store
        self.embeddings = embeddings
        self.rrf_k = rrf_k

    def classify_query_intent(self, query: str) -> RetrievalMode:
        """
        Classifies user query to determine whether LEXICAL, SEMANTIC, or HYBRID is optimal.
        """
        text = query.strip()
        # 1. Exact quoted phrases strongly suggest lexical
        if QUOTED_PATTERN.search(text):
            return RetrievalMode.LEXICAL

        # 2. File extensions or exact paths
        if FILE_EXT_PATTERN.search(text) or "/" in text or "\\" in text:
            return RetrievalMode.LEXICAL

        # 3. CamelCase or snake_case symbols (code identifiers)
        if CAMEL_CASE_PATTERN.search(text) or SNAKE_CASE_PATTERN.search(text):
            return RetrievalMode.LEXICAL

        # 4. Short queries (< 3 words) without conversational framing
        words = text.split()
        if len(words) <= 2 and not any(w.lower() in ("how", "what", "where", "why", "when") for w in words):
            return RetrievalMode.HYBRID

        # Default for natural language descriptions and conceptual queries is HYBRID
        return RetrievalMode.HYBRID

    def retrieve(self, query: RetrievalQuery | str) -> List[RetrievedDocument]:
        """
        Execute retrieval based on query specifications or automatic routing.
        """
        if isinstance(query, str):
            query = RetrievalQuery(text=query, mode=RetrievalMode.HYBRID)

        target_mode = query.mode
        if target_mode == RetrievalMode.HYBRID:
            # Check if query strongly calls for pure lexical
            intent = self.classify_query_intent(query.text)
            if intent == RetrievalMode.LEXICAL:
                # If exact identifier detected, prioritize lexical but allow hybrid fusion
                target_mode = RetrievalMode.HYBRID

        if target_mode == RetrievalMode.LEXICAL:
            return self._retrieve_lexical(query)
        elif target_mode == RetrievalMode.SEMANTIC:
            return self._retrieve_semantic(query)
        else:
            return self._retrieve_hybrid(query)

    def _retrieve_lexical(self, query: RetrievalQuery) -> List[RetrievedDocument]:
        """Execute pure lexical search via FTS5."""
        return self.store.search_lexical(
            query=query.text,
            top_k=query.top_k,
            filter_doc_types=query.filter_doc_types,
        )

    def _retrieve_semantic(self, query: RetrievalQuery) -> List[RetrievedDocument]:
        """Execute pure dense semantic search."""
        query_vec = self.embeddings.embed_text(query.text)
        return self.store.search_semantic(
            query_vector=query_vec,
            top_k=query.top_k,
            filter_doc_types=query.filter_doc_types,
        )

    def _retrieve_hybrid(self, query: RetrievalQuery) -> List[RetrievedDocument]:
        """
        Execute both lexical and semantic retrieval, fusing scores with Reciprocal Rank Fusion (RRF).
        RRF(d) = sum(1 / (k + rank_i))
        """
        k = self.rrf_k
        top_k = query.top_k

        # 1. Fetch Lexical Candidates (top 2*k for broad recall)
        lexical_docs = self.store.search_lexical(
            query=query.text,
            top_k=top_k * 2,
            filter_doc_types=query.filter_doc_types,
        )

        # 2. Fetch Semantic Candidates
        query_vec = self.embeddings.embed_text(query.text)
        semantic_docs = self.store.search_semantic(
            query_vector=query_vec,
            top_k=top_k * 2,
            filter_doc_types=query.filter_doc_types,
        )

        # 3. Fuse via RRF
        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, RetrievedDocument] = {}

        for rank, doc in enumerate(lexical_docs, start=1):
            doc.lexical_rank = rank
            rrf_scores[doc.chunk_id] = rrf_scores.get(doc.chunk_id, 0.0) + (1.0 / (k + rank))
            doc_map[doc.chunk_id] = doc

        for rank, doc in enumerate(semantic_docs, start=1):
            doc.semantic_rank = rank
            rrf_scores[doc.chunk_id] = rrf_scores.get(doc.chunk_id, 0.0) + (1.0 / (k + rank))
            if doc.chunk_id not in doc_map:
                doc_map[doc.chunk_id] = doc
            else:
                # Merge semantic rank into existing doc object
                doc_map[doc.chunk_id].semantic_rank = rank

        # Sort documents by fused RRF score descending
        sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        results: List[RetrievedDocument] = []
        for cid in sorted_chunk_ids[:top_k]:
            doc = doc_map[cid]
            doc.score = rrf_scores[cid]
            results.append(doc)

        return results
