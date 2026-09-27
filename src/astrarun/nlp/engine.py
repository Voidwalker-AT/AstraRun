"""Primary NLP Engine facade for AstraRun.

Orchestrates NLU parsing, caches repeated requests, safely handles exceptions
via deterministic fallback, and identifies queries requiring AI Bridge reasoning.
"""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from typing import Any
from astrarun.nlp.models import (
    Clause,
    ReasoningRequired,
    StructuredUtterance,
    UserRequest,
)
from astrarun.nlp.fusion import NLUFusionEngine
from astrarun.nlp.deterministic import extract_all_deterministic

logger = logging.getLogger(__name__)


class NLPEngine:
    """The central language understanding engine for AstraRun."""

    def __init__(
        self,
        project_registry: Any = None,
        enable_spacy: bool = True,
        cache_size: int = 128
    ):
        self.project_registry = project_registry
        self.fusion_engine = NLUFusionEngine(project_registry=project_registry)
        self.enable_spacy = enable_spacy
        self.cache_size = cache_size
        self._cache: OrderedDict[str, StructuredUtterance] = OrderedDict()

    def parse(
        self,
        request: UserRequest,
        context: Any = None,
        laya_signals: dict[str, Any] | None = None,
    ) -> StructuredUtterance:
        """Parse a natural language UserRequest into a StructuredUtterance IR."""
        cache_key = request.text.strip().lower()
        if context is None and laya_signals is None and cache_key in self._cache:
            # Return cached parse for static identical queries without context
            cached = self._cache[cache_key]
            self._cache.move_to_end(cache_key)
            return cached

        try:
            utterance = self.fusion_engine.fuse(
                request=request,
                context=context,
                laya_signals=laya_signals,
                enable_spacy=self.enable_spacy,
            )
        except Exception as exc:
            logger.warning("NLU fusion failed, falling back to deterministic baseline: %s", exc)
            utterance = self._fallback_parse(request)

        # Cache static parse
        if context is None and laya_signals is None:
            self._cache[cache_key] = utterance
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

        return utterance

    def _fallback_parse(self, request: UserRequest) -> StructuredUtterance:
        """Safe fallback mechanism ensuring AstraRun never crashes on parse failure."""
        text = request.text.strip()
        entities = extract_all_deterministic(text, project_registry=self.project_registry)
        clause = Clause(
            idx=0,
            text=text,
            action="open_project" if any(e.type.value == "PROJECT" for e in entities) else "unknown",
            intent="fallback",
            entities=entities,
            confidence=0.5,
            source="emergency_fallback",
        )
        return StructuredUtterance(
            raw_text=text,
            normalized_text=text,
            clauses=[clause],
            entities=entities,
            confidence=0.5,
            ambiguity=0.5,
            parser_sources=["emergency_fallback"],
            provenance={"error": "NLU pipeline fallback invoked"},
            session_id=request.session_id,
            timestamp=request.timestamp,
        )

    def check_reasoning_escalation(
        self,
        utterance: StructuredUtterance
    ) -> ReasoningRequired | None:
        """Evaluate whether an utterance requires background AI reasoning (v0.7)."""
        raw = utterance.raw_text.lower()

        # 1. Complex temporal or context-switching memory requests
        if re.search(r'\b(?:whatever\s+i\s+was\s+doing|get\s+me\s+back\s+to\s+what|before\s+i\s+switched)\b', raw):
            return ReasoningRequired(
                reason="complex_context_restoration",
                structured_partial_parse=utterance,
                unresolved_fields=["target_project", "target_activity"],
                explanation="Request requires semantic reasoning over past workstation activity logs.",
            )

        # 2. Diagnostic reasoning questions
        if any(c.action == "ai_query" for c in utterance.clauses):
            return ReasoningRequired(
                reason="diagnostic_reasoning",
                structured_partial_parse=utterance,
                unresolved_fields=["explanation"],
                explanation="User asked an open-ended explanatory or diagnostic question.",
            )

        # 3. High ambiguity with no resolvable entities
        if utterance.ambiguity > 0.8 and not utterance.entities:
            return ReasoningRequired(
                reason="high_ambiguity_no_entities",
                structured_partial_parse=utterance,
                unresolved_fields=["intent", "entities"],
                explanation="Utterance lacks clear workstation entities and presents high ambiguity.",
            )

        return None

    def explain(
        self,
        request: UserRequest,
        context: Any = None
    ) -> dict[str, Any]:
        """Produce a comprehensive developer diagnostic representation."""
        utterance = self.parse(request, context)
        escalation = self.check_reasoning_escalation(utterance)
        return {
            "utterance": utterance.to_dict(),
            "reasoning_required": escalation.to_dict() if escalation else None,
            "cache_size": len(self._cache),
        }
