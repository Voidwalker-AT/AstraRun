# AstraRun v0.6.5 — AI Bridge NLP Escalation & Handoff Boundary

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Target Consumer**: AI Bridge (v0.7 Milestone)  
> **Model Definition**: `src/astrarun/nlp/models.py` (`ReasoningRequired`)  

---

## 1. Architectural Role

The NLP layer does NOT invoke AI Bridge or cloud LLMs directly. Instead, when an utterance exceeds deterministic understanding, the engine emits a typed `ReasoningRequired` escalation object.

```text
Natural Language Utterance
            │
            ▼
        NLPEngine
            │
     Exceeds Deterministic
         Capabilities?
            │
            ├─────── NO ───────> WorkflowCompiler ───> ActionGate
            │
           YES
            ▼
    ReasoningRequired (Envelope)
            │
            ▼
    [ v0.7 Boundary: AI Bridge ]
            │
            ▼
    Structured Reasoning Result
            │
            ▼
    EntityResolver ───> ActionGate ───> ToolRegistry
```

---

## 2. Escalation Trigger Conditions

AstraRun's NLP engine escalates queries under three conditions:

| Escalation Reason | Trigger Syntax | Unresolved Fields | Concrete Example |
| :--- | :--- | :--- | :--- |
| **`complex_context_restoration`** | Semantic references to past activities | `target_project`, `target_activity` | `"get me back to whatever I was doing before AstraRun"` |
| **`diagnostic_reasoning`** | Open-ended explanatory questions | `explanation`, `diagnostic_steps` | `"why is port 3000 occupied?"`, `"explain this failure"` |
| **`high_ambiguity_no_entities`** | High ambiguity with no resolvable entities | `intent`, `target_entities` | `"fix the thing that broke earlier"` |

---

## 3. Privacy-Preserving Structured Context Contract

When escalating to future background reasoning providers, AstraRun adheres to a strict privacy contract:

- **Prohibited**: Raw shell command history, keystroke logs, memory dumps, and unsanitized screen buffers.
- **Permitted**: Minimal structured context envelopes containing:
  - Canonical project IDs and last-interacted timestamps.
  - Active dev ports and listening process names.
  - Foreground application window title (sanitized).
