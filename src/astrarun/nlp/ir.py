"""Typed Intermediate Representation (NLP-IR) for AstraRun Neural NLP Pipeline.

Strictly typed, non-generative, byte-exact representation of natural language
intents, syntactic clauses, entities, and literal payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class TextSpan:
    """Character offsets referencing the original, unmodified user query."""
    start: int
    end: int
    raw: str

    @property
    def length(self) -> int:
        """Length of this span in characters."""
        return self.end - self.start

    def slice_from(self, text: str) -> str:
        """Extract this span from the provided text."""
        return text[self.start:self.end]

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "raw": self.raw}


@dataclass
class LiteralPayload:
    """Verbatim user text meant for application typing, searching, or form entry.
    
    Guarantees 100% character-level preservation with zero normalization.
    """
    text: str
    source_span: TextSpan
    is_verbatim: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source_span": self.source_span.to_dict(),
            "is_verbatim": self.is_verbatim,
        }


@dataclass
class ParsedEntity:
    """An extracted entity or target element within a clause."""
    entity_type: str             # "app_name", "folder_name", "url", "snap_position", "key_name", "ui_element", "target_ref"
    value: str
    source_span: TextSpan
    confidence: float = 1.0
    referent_index: Optional[int] = None  # Clause antecedent pointer if pronoun

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "source_span": self.source_span.to_dict(),
            "confidence": self.confidence,
            "referent_index": self.referent_index,
        }


@dataclass
class ParsedClause:
    """An individual atomic action unit within an utterance."""
    clause_id: str
    sequence_index: int
    intent: str                  # "open_app", "type_text", "snap_window", "close_window", etc.
    action_verb: str             # "open", "type", "snap", "close", "minimize", etc.
    is_negated: bool = False     # True if governed by negation ("do not", "never", "don't")
    entities: list[ParsedEntity] = field(default_factory=list)
    payload: Optional[LiteralPayload] = None
    dependency_clause_index: Optional[int] = None
    source_span: Optional[TextSpan] = None
    raw_clause: str = ""

    def get_entity(self, entity_type: str) -> Optional[ParsedEntity]:
        for ent in self.entities:
            if ent.entity_type == entity_type:
                return ent
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "sequence_index": self.sequence_index,
            "intent": self.intent,
            "action_verb": self.action_verb,
            "is_negated": self.is_negated,
            "entities": [e.to_dict() for e in self.entities],
            "payload": self.payload.to_dict() if self.payload else None,
            "dependency_clause_index": self.dependency_clause_index,
            "source_span": self.source_span.to_dict() if self.source_span else None,
            "raw_clause": self.raw_clause,
        }


@dataclass
class ParsedRequest:
    """Root container produced by the Neural NLP structure engine."""
    raw_query: str
    clauses: list[ParsedClause] = field(default_factory=list)
    is_compound: bool = False
    has_negation: bool = False
    ambiguity_score: float = 0.0
    confidence: float = 1.0
    source_engine: str = "neural_spacy_laya"

    @property
    def clause_count(self) -> int:
        return len(self.clauses)

    @property
    def executable_clauses(self) -> list[ParsedClause]:
        """Return all affirmative (non-negated) clauses in execution sequence order."""
        return [c for c in sorted(self.clauses, key=lambda x: x.sequence_index) if not c.is_negated]

    @property
    def negated_clauses(self) -> list[ParsedClause]:
        """Return all explicitly negated clauses."""
        return [c for c in self.clauses if c.is_negated]

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "is_compound": self.is_compound,
            "has_negation": self.has_negation,
            "ambiguity_score": self.ambiguity_score,
            "confidence": self.confidence,
            "source_engine": self.source_engine,
            "clauses": [c.to_dict() for c in self.clauses],
        }

    def to_structured_utterance(self) -> Any:
        """Convert ParsedRequest into the canonical StructuredUtterance IR for WorkflowCompiler."""
        from astrarun.nlp.models import (
            Clause,
            ContextualReference,
            Negation,
            NLPEntity,
            NLPEntityType,
            OrderingRelation,
            StructuredUtterance,
        )

        utterance_clauses: list[Clause] = []
        all_entities: list[NLPEntity] = []
        all_negations: list[Negation] = []
        ordering_relations: list[tuple[int, OrderingRelation, int]] = []

        for c in self.clauses:
            clause_entities: list[NLPEntity] = []
            clause_refs: list[ContextualReference] = []

            for ent in c.entities:
                e_type = NLPEntityType.UNKNOWN
                if ent.entity_type == "app_name":
                    e_type = NLPEntityType.APPLICATION
                elif ent.entity_type == "folder_name":
                    e_type = NLPEntityType.FOLDER
                elif ent.entity_type == "url":
                    e_type = NLPEntityType.URL
                elif ent.entity_type == "process":
                    e_type = NLPEntityType.PROCESS
                elif ent.entity_type == "port":
                    e_type = NLPEntityType.PORT
                elif ent.entity_type == "project":
                    e_type = NLPEntityType.PROJECT

                if ent.entity_type in ("process", "port") and isinstance(ent.value, str) and ent.value.isdigit():
                    norm_val: Any = int(ent.value)
                else:
                    norm_val = ent.value

                if ent.entity_type == "target_ref":
                    clause_refs.append(ContextualReference(
                        text=ent.value,
                        target_type="window",
                        start=ent.source_span.start,
                        end=ent.source_span.end,
                    ))
                else:
                    nlp_ent = NLPEntity(
                        type=e_type,
                        text=ent.value,
                        start=ent.source_span.start,
                        end=ent.source_span.end,
                        normalized=norm_val,
                        source=self.source_engine,
                        confidence=ent.confidence,
                    )
                    clause_entities.append(nlp_ent)
                    all_entities.append(nlp_ent)

            neg_detail = None
            if c.is_negated:
                neg_detail = Negation(
                    text="not",
                    target_clause_idx=c.sequence_index,
                    target_action=c.intent,
                    scope_text=c.raw_clause,
                )
                all_negations.append(neg_detail)

            # Determine canonical action name for WorkflowCompiler
            action_name = c.intent
            if action_name in ("press_key", "press_keyboard_shortcut"):
                action_name = "press_keyboard_shortcut"
            elif action_name in ("ui_click", "click_ui_element"):
                action_name = "click_ui_element"
            elif action_name in ("ui_focus", "focus_ui_element"):
                action_name = "focus_ui_element"
            elif action_name in ("ui_select", "select_ui_element"):
                action_name = "select_ui_element"
            elif action_name in ("close_app", "close_application"):
                action_name = "close_application"
            elif action_name in ("focus_app", "focus_application"):
                action_name = "focus_application"
            elif action_name == "focus_window":
                if any(e.entity_type == "app_name" for e in c.entities):
                    action_name = "focus_application"
            elif action_name == "snap_window":
                if any(e.entity_type == "snap_position" and "right" in e.value.lower() for e in c.entities) or "right" in c.raw_clause.lower():
                    action_name = "snap_window_right"
                else:
                    action_name = "snap_window_left"

            if c.payload and c.intent == "type_text":
                c_text = f"type {c.payload.text}"
            else:
                c_text = c.raw_clause

            u_clause = Clause(
                idx=c.sequence_index,
                text=c_text,
                action=action_name,
                intent=c.intent,
                entities=clause_entities,
                negated=c.is_negated,
                negation_details=neg_detail,
                contextual_references=clause_refs,
                confidence=self.confidence,
                source=self.source_engine,
            )
            utterance_clauses.append(u_clause)

        for i in range(len(utterance_clauses) - 1):
            ordering_relations.append((i, OrderingRelation.THEN, i + 1))

        return StructuredUtterance(
            raw_text=self.raw_query,
            normalized_text=self.raw_query.lower(),
            clauses=utterance_clauses,
            ordering_relations=ordering_relations,
            entities=all_entities,
            negations=all_negations,
            ambiguity=self.ambiguity_score,
            confidence=self.confidence,
            parser_sources=[self.source_engine],
            provenance={"source_engine": self.source_engine},
        )
