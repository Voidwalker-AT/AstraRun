# AstraRun — Reasoning Provider Handoff & Escalation Boundary

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5 / v0.7 (Terminology Corrected)  
> **Target Consumer**: Generic `ReasoningProvider` interface (v0.12 Milestone)  
> **Model Definition**: `src/astrarun/nlp/models.py` (`ReasoningRequired`)  
> **Note on Terminology**: Early drafts referenced "AI Bridge" as if it were an internal AstraRun module. The user maintains an independent platform project named `AI-Bridge`. AstraRun maintains a clean, decoupled `ReasoningProvider` interface that may eventually connect to AI-Bridge, a local LLM, or a cloud provider in v0.12, but AstraRun itself does not assume any specific backend.

---

## 1. Architectural Role

The NLP layer does NOT invoke external reasoning models or cloud LLMs directly. Instead, when an utterance exceeds deterministic understanding, the engine emits a typed `ReasoningRequired` escalation object.

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
    [ v0.12 Boundary: Optional Reasoning Provider ]
            │
            ▼
    Structured Reasoning Result
            │
            ▼
    EntityResolver ───> ActionGate ───> CapabilityRegistry
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
  - Structured OS observations (see `docs/OBSERVATIONS.md`).
