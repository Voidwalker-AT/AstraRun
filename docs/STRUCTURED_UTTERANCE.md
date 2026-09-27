# AstraRun v0.6.5 — StructuredUtterance IR Specification

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Schema Definition**: `src/astrarun/nlp/models.py`  

---

## 1. Overview

`StructuredUtterance` is the canonical intermediate representation (IR) produced by AstraRun's NLP engine. It captures linguistic structure, decomposed actions, extracted entities, temporal references, negation boundaries, and provenance while remaining completely inert and incapable of executing system commands.

---

## 2. Core Schema Definition

```python
@dataclass
class StructuredUtterance:
    raw_text: str
    normalized_text: str
    clauses: list[Clause]
    ordering_relations: list[tuple[int, OrderingRelation, int]]
    entities: list[NLPEntity]
    relations: list[Relation]
    temporal_expressions: list[TemporalExpression]
    contextual_references: list[ContextualReference]
    negations: list[Negation]
    constraints: list[Constraint]
    confidence: float
    ambiguity: float
    parser_sources: list[str]
    provenance: dict[str, Any]
    session_id: str | None = None
    timestamp: float = field(default_factory=time.time)
```

---

## 3. Sub-Component Schemas

### A. `Clause`
Represents an atomic action or query segment within a compound utterance:
```python
@dataclass
class Clause:
    idx: int
    text: str
    action: str              # e.g. "open_project", "inspect_port", "terminate_process"
    intent: str              # Broad intent category
    entities: list[NLPEntity]
    negated: bool = False
    negation_details: Negation | None = None
    modifiers: list[str]
    constraints: list[Constraint]
    temporal_expressions: list[TemporalExpression]
    contextual_references: list[ContextualReference]
    relations: list[Relation]
    confidence: float = 1.0
    source: str = "nlp_engine"
```

### B. `NLPEntity`
Represents an entity span with character offsets and normalized typed value:
```python
@dataclass
class NLPEntity:
    type: NLPEntityType      # PORT, PROCESS, PROJECT, APPLICATION, URL, FOLDER, FILE
    text: str                # Raw matched substring
    start: int               # 0-indexed start character offset
    end: int                 # 0-indexed end character offset
    normalized: Any          # Typed value (int for port/pid, canonical string for project)
    source: str              # Extraction provenance (e.g. "deterministic_port")
    confidence: float = 1.0
```

### C. `OrderingRelation`
Enumerates execution sequence and temporal dependency between clauses:
- `THEN`: Sequential execution (Clause A must precede Clause B).
- `BEFORE`: Explicit precedence (Clause A executed before Clause B).
- `AFTER`: Reverse precedence (Clause B executed before Clause A).
- `PARALLEL`: Independent concurrent actions.
- `CONJUNCTION`: General coordinated actions.

### D. `Negation`
Scopes negative polarity to a specific clause index and action target:
```python
@dataclass
class Negation:
    text: str                # e.g. "don't", "never", "without"
    target_clause_idx: int
    target_action: str | None
    scope_text: str
    is_contrastive: bool = False
```

---

## 4. Concrete Serialization Example

For the input: `"open AstraRun in vscode and inspect port 3000"`

```json
{
  "raw_text": "open AstraRun in vscode and inspect port 3000",
  "normalized_text": "open AstraRun in vscode and inspect port 3000",
  "confidence": 0.98,
  "ambiguity": 0.0,
  "clauses": [
    {
      "idx": 0,
      "text": "open AstraRun in vscode",
      "action": "open_project",
      "intent": "project_action",
      "negated": false,
      "entities": [
        {
          "type": "PROJECT",
          "text": "AstraRun",
          "start": 5,
          "end": 13,
          "normalized": "astrarun",
          "source": "project_registry_exact"
        },
        {
          "type": "APPLICATION",
          "text": "vscode",
          "start": 17,
          "end": 23,
          "normalized": "vscode",
          "source": "app_index_alias"
        }
      ]
    },
    {
      "idx": 1,
      "text": "inspect port 3000",
      "action": "inspect_port",
      "intent": "inspect_action",
      "negated": false,
      "entities": [
        {
          "type": "PORT",
          "text": "port 3000",
          "start": 36,
          "end": 45,
          "normalized": 3000,
          "source": "deterministic_port"
        }
      ]
    }
  ],
  "ordering_relations": [
    {
      "from": 0,
      "relation": "CONJUNCTION",
      "to": 1
    }
  ],
  "relations": [
    {
      "type": "OPEN_WITH",
      "source_entity": "project:astrarun",
      "target_entity": "application:vscode",
      "confidence": 0.98
    }
  ],
  "parser_sources": [
    "deterministic_rules",
    "deterministic_entities",
    "clause_decomposer",
    "relation_extractor"
  ]
}
```
