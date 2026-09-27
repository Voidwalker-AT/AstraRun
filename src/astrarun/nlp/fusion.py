"""NLU Fusion Engine.

Fuses deterministic extraction, clause decomposition, negation scoping,
local temporal expressions, contextual references, and Laya semantic signals
into a single, typed StructuredUtterance with full provenance and zero execution authority.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from astrarun.nlp.models import (
    Clause,
    ContextualReference,
    NLPEntity,
    NLPEntityType,
    OrderingRelation,
    Relation,
    StructuredUtterance,
    TemporalExpression,
    UserRequest,
)
from astrarun.nlp.deterministic import extract_all_deterministic
from astrarun.nlp.temporal import extract_temporal_expressions
from astrarun.nlp.clause_decomposer import decompose_clauses, strip_politeness
from astrarun.nlp.negation import apply_negation_scope
from astrarun.nlp.coreference import extract_contextual_references, resolve_coreference_with_context
from astrarun.nlp.relations import extract_relations
from astrarun.nlp.spacy_parser import is_spacy_available, parse_spacy_tokens

logger = logging.getLogger(__name__)


class NLUFusionEngine:
    """Combines rule extractors, grammar parsers, and statistical models."""

    def __init__(self, project_registry: Any = None):
        self.project_registry = project_registry

    def fuse(
        self,
        request: UserRequest,
        context: Any = None,
        laya_signals: dict[str, Any] | None = None,
        enable_spacy: bool = True,
    ) -> StructuredUtterance:
        """Execute the multi-tier NLU fusion pipeline."""
        t_start = time.perf_counter()
        raw_text = request.text
        provenance: dict[str, Any] = {}
        parser_sources: list[str] = ["deterministic_rules"]

        # 1. Normalize politeness while retaining raw text
        normalized = strip_politeness(raw_text)

        # 2. Extract deterministic entities
        entities = extract_all_deterministic(
            normalized,
            project_registry=self.project_registry
        )
        if entities:
            parser_sources.append("deterministic_entities")
            provenance["entities"] = [
                {"text": e.text, "type": e.type.value, "normalized": e.normalized, "source": e.source}
                for e in entities
            ]

        # 3. Extract temporal expressions
        temporal_exprs = extract_temporal_expressions(normalized)
        if temporal_exprs:
            parser_sources.append("workstation_temporal")
            provenance["temporal"] = [
                {"text": t.text, "value": t.value, "relation": t.relation, "range": t.resolved_range}
                for t in temporal_exprs
            ]

        # 4. Extract and resolve contextual references
        raw_corefs = extract_contextual_references(normalized)
        resolved_corefs: list[ContextualReference] = []
        is_ambiguous = False

        for ref in raw_corefs:
            res_ref = resolve_coreference_with_context(ref, context=context)
            resolved_corefs.append(res_ref)
            if res_ref.ambiguous:
                is_ambiguous = True

        if resolved_corefs:
            parser_sources.append("context_coreference")
            provenance["coreferences"] = [
                {"text": r.text, "type": r.target_type, "resolved_id": r.resolved_id, "ambiguous": r.ambiguous}
                for r in resolved_corefs
            ]

        # 5. Clause decomposition and ordering
        clauses, ordering_rels = decompose_clauses(normalized, entities)
        parser_sources.append("clause_decomposer")

        # 6. Negation detection & scope attribution
        negations = apply_negation_scope(clauses)
        if negations:
            parser_sources.append("negation_scoper")
            provenance["negations"] = [
                {"text": n.text, "clause_idx": n.target_clause_idx, "action": n.target_action}
                for n in negations
            ]

        # 7. Directed relation extraction
        relations = extract_relations(normalized, entities, clauses)
        if relations:
            parser_sources.append("relation_extractor")
            provenance["relations"] = [
                {"type": r.type.value, "source": r.source_entity, "target": r.target_entity}
                for r in relations
            ]

        # 8. Optional spaCy linguistic parsing
        if enable_spacy and is_spacy_available():
            spacy_tokens = parse_spacy_tokens(normalized)
            if spacy_tokens:
                parser_sources.append("spacy_en_core_web_sm")
                provenance["linguistic_tokens_count"] = len(spacy_tokens)

        # 9. Laya Semantic Signals Integration
        overall_confidence = 0.95
        ambiguity_score = 1.0 if is_ambiguous else 0.0

        if laya_signals:
            parser_sources.append("laya_semantic_signals")
            laya_intent = laya_signals.get("intent")
            laya_conf = laya_signals.get("confidence", 0.8)
            laya_ambiguity = laya_signals.get("ambiguity", 0.0)

            provenance["laya"] = {
                "intent": laya_intent,
                "confidence": laya_conf,
                "ambiguity": laya_ambiguity,
            }

            # Conflict handling: Deterministic Evidence > Laya Signals
            for c in clauses:
                if c.action in ("unsupported", "unknown") and laya_intent:
                    # Laya informs unclassified clause
                    c.action = laya_intent
                    c.intent = laya_intent
                    c.source = "laya_intent_signal"
                    c.confidence = laya_conf

            if laya_ambiguity > 0.4:
                ambiguity_score = max(ambiguity_score, laya_ambiguity)

        # Attribute temporal expressions and corefs to clauses
        for c in clauses:
            c.temporal_expressions = [
                t for t in temporal_exprs
                if t.text.lower() in c.text.lower()
            ]
            c.contextual_references = [
                r for r in resolved_corefs
                if r.text.lower() in c.text.lower()
            ]
            c.relations = [
                rel for rel in relations
                if any(e.text.lower() in c.text.lower() for e in entities)
            ]

        # Overall confidence calculation
        if clauses:
            clause_confs = [c.confidence for c in clauses]
            overall_confidence = sum(clause_confs) / len(clause_confs)

        if is_ambiguous:
            overall_confidence = min(overall_confidence, 0.5)

        provenance["parse_duration_ms"] = round((time.perf_counter() - t_start) * 1000, 3)

        return StructuredUtterance(
            raw_text=raw_text,
            normalized_text=normalized,
            clauses=clauses,
            ordering_relations=ordering_rels,
            entities=entities,
            relations=relations,
            temporal_expressions=temporal_exprs,
            contextual_references=resolved_corefs,
            negations=negations,
            constraints=[co for c in clauses for co in c.constraints],
            confidence=overall_confidence,
            ambiguity=ambiguity_score,
            parser_sources=parser_sources,
            provenance=provenance,
            session_id=request.session_id,
            timestamp=request.timestamp,
        )
