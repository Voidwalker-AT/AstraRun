"""Data models and typed Intermediate Representation (IR) for AstraRun NLP.

The central IR is StructuredUtterance, representing linguistic structure,
entities, clauses, relations, negations, constraints, and provenance
without holding execution authority.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NLPEntityType(str, Enum):
    """Semantic entity categories recognized by AstraRun NLP."""
    APPLICATION = "APPLICATION"
    PROJECT = "PROJECT"
    FOLDER = "FOLDER"
    FILE = "FILE"
    PORT = "PORT"
    PROCESS = "PROCESS"
    URL = "URL"
    SERVICE = "SERVICE"
    COMMAND_PROFILE = "COMMAND_PROFILE"
    NUMBER = "NUMBER"
    PERCENTAGE = "PERCENTAGE"
    TIME_REFERENCE = "TIME_REFERENCE"
    UNKNOWN = "UNKNOWN"


@dataclass
class NLPEntity:
    """An extracted entity span with typed metadata and provenance."""
    type: NLPEntityType
    text: str
    start: int
    end: int
    normalized: Any
    source: str
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "normalized": self.normalized,
            "source": self.source,
            "confidence": round(self.confidence, 4),
        }


class RelationType(str, Enum):
    """Semantic relations between entities or clauses."""
    LISTENS_ON = "LISTENS_ON"        # PROCESS -> PORT
    OPEN_WITH = "OPEN_WITH"          # PROJECT/FILE -> APPLICATION
    CONTAINS = "CONTAINS"            # FOLDER -> FILE
    OPERATES_ON = "OPERATES_ON"      # ACTION -> ENTITY
    FOLLOWS = "FOLLOWS"              # CLAUSE -> CLAUSE
    REFERENCES = "REFERENCES"        # CONTEXTUAL_REFERENCE -> ENTITY


@dataclass
class Relation:
    """Directed semantic relationship between entities."""
    type: RelationType
    source_entity: str
    target_entity: str
    confidence: float = 1.0
    source: str = "rule"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "source_entity": self.source_entity,
            "target_entity": self.target_entity,
            "confidence": round(self.confidence, 4),
            "source": self.source,
        }


class OrderingRelation(str, Enum):
    """Temporal or causal ordering between clauses."""
    THEN = "THEN"              # Sequential: clause A then clause B
    BEFORE = "BEFORE"          # Precedence: clause A before clause B
    AFTER = "AFTER"            # Precedence: clause A after clause B
    PARALLEL = "PARALLEL"      # Concurrent / Independent: clause A and clause B
    CONJUNCTION = "CONJUNCTION"# Coordinated clause


@dataclass
class TemporalExpression:
    """Workstation-relevant temporal expression with local time bounds."""
    text: str
    relation: str              # "during", "before", "after", "exact"
    value: str                 # "yesterday", "today", "most_recent", etc.
    resolved_range: tuple[float, float] | None = None
    start: int = 0
    end: int = 0
    source: str = "workstation_temporal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "relation": self.relation,
            "value": self.value,
            "resolved_range": list(self.resolved_range) if self.resolved_range else None,
            "start": self.start,
            "end": self.end,
            "source": self.source,
        }


@dataclass
class ContextualReference:
    """An anaphoric or contextual reference token."""
    text: str                  # "it", "that", "that process", "the project"
    target_type: str           # "process", "project", "window", "generic"
    start: int
    end: int
    resolved_id: str | None = None
    resolved_value: Any = None
    ambiguous: bool = False
    candidate_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "target_type": self.target_type,
            "start": self.start,
            "end": self.end,
            "resolved_id": self.resolved_id,
            "resolved_value": self.resolved_value,
            "ambiguous": self.ambiguous,
            "candidate_ids": self.candidate_ids,
        }


@dataclass
class Negation:
    """Scoped negation marker targeting a specific clause or action."""
    text: str                  # "don't", "do not", "never", "without"
    target_clause_idx: int
    target_action: str | None = None
    scope_text: str = ""
    is_contrastive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "target_clause_idx": self.target_clause_idx,
            "target_action": self.target_action,
            "scope_text": self.scope_text,
            "is_contrastive": self.is_contrastive,
        }


@dataclass
class Constraint:
    """Operational modifier or constraint attached to an action."""
    type: str                  # "NO_STARTUP_ACTIONS", "READ_ONLY", "EXTENSION_FILTER"
    value: Any = True
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "value": self.value,
            "raw_text": self.raw_text,
        }


@dataclass
class Clause:
    """A single atomic action or query segment within an utterance."""
    idx: int
    text: str
    action: str                # Canonical action name e.g. "open_project", "inspect_port"
    intent: str                # Synonymous with action or broad intent
    entities: list[NLPEntity] = field(default_factory=list)
    negated: bool = False
    negation_details: Negation | None = None
    modifiers: list[str] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    temporal_expressions: list[TemporalExpression] = field(default_factory=list)
    contextual_references: list[ContextualReference] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    confidence: float = 1.0
    source: str = "nlp_engine"

    def to_dict(self) -> dict[str, Any]:
        return {
            "idx": self.idx,
            "text": self.text,
            "action": self.action,
            "intent": self.intent,
            "entities": [e.to_dict() for e in self.entities],
            "negated": self.negated,
            "negation_details": self.negation_details.to_dict() if self.negation_details else None,
            "modifiers": self.modifiers,
            "constraints": [c.to_dict() for c in self.constraints],
            "temporal_expressions": [t.to_dict() for t in self.temporal_expressions],
            "contextual_references": [r.to_dict() for r in self.contextual_references],
            "relations": [rel.to_dict() for rel in self.relations],
            "confidence": round(self.confidence, 4),
            "source": self.source,
        }


@dataclass
class StructuredUtterance:
    """Canonical Intermediate Representation (IR) of parsed natural language."""
    raw_text: str
    normalized_text: str
    clauses: list[Clause] = field(default_factory=list)
    ordering_relations: list[tuple[int, OrderingRelation, int]] = field(default_factory=list)
    entities: list[NLPEntity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    temporal_expressions: list[TemporalExpression] = field(default_factory=list)
    contextual_references: list[ContextualReference] = field(default_factory=list)
    negations: list[Negation] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    confidence: float = 1.0
    ambiguity: float = 0.0
    parser_sources: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "clauses": [c.to_dict() for c in self.clauses],
            "ordering_relations": [
                {"from": rel[0], "relation": rel[1].value, "to": rel[2]}
                for rel in self.ordering_relations
            ],
            "entities": [e.to_dict() for e in self.entities],
            "relations": [r.to_dict() for r in self.relations],
            "temporal_expressions": [t.to_dict() for t in self.temporal_expressions],
            "contextual_references": [cr.to_dict() for cr in self.contextual_references],
            "negations": [n.to_dict() for n in self.negations],
            "constraints": [co.to_dict() for co in self.constraints],
            "confidence": round(self.confidence, 4),
            "ambiguity": round(self.ambiguity, 4),
            "parser_sources": self.parser_sources,
            "provenance": self.provenance,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }


@dataclass
class ReasoningRequired:
    """Escalation envelope for queries requiring background reasoning in v0.7."""
    reason: str
    structured_partial_parse: StructuredUtterance | None = None
    unresolved_fields: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "structured_partial_parse": self.structured_partial_parse.to_dict() if self.structured_partial_parse else None,
            "unresolved_fields": self.unresolved_fields,
            "explanation": self.explanation,
        }


@dataclass
class UserRequest:
    """User input container carrying input origin and session context."""
    text: str
    source: str = "launcher"
    timestamp: float = field(default_factory=time.time)
    session_id: str | None = None
