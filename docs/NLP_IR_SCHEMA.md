# AstraRun NLP Intermediate Representation (NLP-IR) Schema

> **Milestone**: AstraRun v0.10.3  
> **Schema Version**: `1.0.0`  
> **Package**: `astrarun.nlp.ir`  
> **Status**: APPROVED & FROZEN  

---

## 1. Schema Design Principles

1. **Non-Generative & Strictly Typed**: Every field is explicitly typed with Python type hints and dataclass invariants.
2. **Byte-Exact Source Spans**: Every token, clause, and literal payload records `[start:end]` character offsets referencing the unmodified input string.
3. **Preservation of Verbatim Payloads**: `LiteralPayload` is never lowercased, trimmed, or stripped of punctuation.
4. **Execution Authority Boundary**: NLP-IR encapsulates linguistic understanding only. It contains **no** operating system handles (`HWND`), process IDs (`PID`), filesystem paths, or executable commands.

---

## 2. Core Data Structures

### `TextSpan`
Character span referencing the original user query.
```python
@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    raw: str

    def slice_from(self, text: str) -> str:
        return text[self.start:self.end]
```

### `LiteralPayload`
Verbatim user text meant for application input (e.g. typing, searching, prompt text).
```python
@dataclass
class LiteralPayload:
    text: str
    source_span: TextSpan
    is_verbatim: bool = True
```

### `ParsedEntity`
Extracted linguistic argument or target element.
```python
@dataclass
class ParsedEntity:
    entity_type: str            # "app_name", "folder_name", "url", "snap_position", "key_name", "ui_element", "target_ref"
    value: str                  # normalized or raw value
    source_span: TextSpan
    confidence: float = 1.0
    referent_index: Optional[int] = None  # If entity is a pronoun ("it"), index of antecedent clause
```

### `ParsedClause`
A single atomic action unit within a potentially compound utterance.
```python
@dataclass
class ParsedClause:
    clause_id: str
    sequence_index: int
    intent: str                 # "open_app", "type_text", "snap_window", "close_window", etc.
    action_verb: str            # "open", "type", "snap", "close", "minimize"
    is_negated: bool            # True if preceded or governed by negation ("do not", "never", "don't")
    entities: list[ParsedEntity] = field(default_factory=list)
    payload: Optional[LiteralPayload] = None
    dependency_clause_index: Optional[int] = None  # Clause upon which this action depends
    source_span: Optional[TextSpan] = None
    raw_clause: str = ""
```

### `ParsedRequest`
The root container produced by the Neural NLP structure engine.
```python
@dataclass
class ParsedRequest:
    raw_query: str
    clauses: list[ParsedClause] = field(default_factory=list)
    is_compound: bool = False
    has_negation: bool = False
    ambiguity_score: float = 0.0
    confidence: float = 1.0
    source_engine: str = "neural_spacy_laya"
```

---

## 3. Serialization Schema (JSON)

```json
{
  "raw_query": "open notepad and type hello from Astra",
  "is_compound": true,
  "has_negation": false,
  "ambiguity_score": 0.05,
  "confidence": 0.98,
  "source_engine": "neural_spacy_laya",
  "clauses": [
    {
      "clause_id": "c0",
      "sequence_index": 0,
      "intent": "open_app",
      "action_verb": "open",
      "is_negated": false,
      "entities": [
        {
          "entity_type": "app_name",
          "value": "notepad",
          "source_span": { "start": 5, "end": 12, "raw": "notepad" },
          "confidence": 0.99,
          "referent_index": null
        }
      ],
      "payload": null,
      "dependency_clause_index": null,
      "source_span": { "start": 0, "end": 12, "raw": "open notepad" },
      "raw_clause": "open notepad"
    },
    {
      "clause_id": "c1",
      "sequence_index": 1,
      "intent": "type_text",
      "action_verb": "type",
      "is_negated": false,
      "entities": [],
      "payload": {
        "text": "hello from Astra",
        "source_span": { "start": 22, "end": 38, "raw": "hello from Astra" },
        "is_verbatim": true
      },
      "dependency_clause_index": 0,
      "source_span": { "start": 17, "end": 38, "raw": "type hello from Astra" },
      "raw_clause": "type hello from Astra"
    }
  ]
}
```
