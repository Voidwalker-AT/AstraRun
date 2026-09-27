# AstraRun v0.6.5 — Hybrid NLP Architecture Specification

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Audience**: Platform Engineers, Security Engineers, AI Agents  

---

## 1. Architectural Philosophy

AstraRun v0.6.5 introduces a dedicated **Natural Language Understanding (NLU/NLP) layer** between raw human language and AstraRun's deterministic execution architecture.

### The Prime Operating Rule
$$\text{Natural Language} \longrightarrow \text{NLP Engine} \longrightarrow \text{StructuredUtterance (Data)} \longrightarrow \text{Context Engine} \longrightarrow \text{Entity Resolution} \longrightarrow \text{Proposed Action} \longrightarrow \text{ActionGate} \longrightarrow \text{Registered Tool} \longrightarrow \text{OS}$$

- **NLP understands language; NLP DOES NOT control the computer.**
- **Zero Raw Shell Invariant**: Output from NLP models, tokenizers, dependency parsers, or LLMs is strictly treated as data and never passed to a system shell (`cmd.exe`, `powershell.exe`, or `subprocess.run(shell=True)`).
- **No Unrestricted Autonomous Planning**: NLP output must map only to predefined registered tools or structured workflow templates.

---

## 2. Multi-Layer Hybrid Architecture

Rather than relying on a single monolithic statistical model, AstraRun employs a multi-layer hybrid approach:

```text
                                Human Text
                                    │
                                    ▼
                          Politeness Normalization
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
   Deterministic             Linguistic Parser          Laya Semantic
    Extractors                   (spaCy)                   Signals
  - Ports / PIDs             - Part of Speech           - Broad Intent
  - URLs / Paths             - Dependency Heads         - Ambiguity Score
  - Catalog Entities         - Lemmatization            - Risk Class
         │                          │                          │
         └──────────────────────────┼──────────────────────────┘
                                    ▼
                            NLU Fusion Engine
                                    │
                      ┌─────────────┴─────────────┐
                      ▼                           ▼
              Clause Decomposer            Negation Scoper
              (AND, THEN, BEFORE)         (0.00% Leakage)
                      │                           │
                      └─────────────┬─────────────┘
                                    ▼
                         Local Temporal Engine
                         (Local Machine Range)
                                    │
                                    ▼
                        Coreference Recognizer
                        (Syntactic Pronoun Spans)
                                    │
                                    ▼
                           StructuredUtterance
                                    │
                                    ▼
                            Workflow Compiler
                                    │
                                    ▼
                            WorkflowProposal
```

---

## 3. Component Responsibilities

| Component | Module Path | Primary Responsibility | Latency |
| :--- | :--- | :--- | :--- |
| **Deterministic Extractors** | `src/astrarun/nlp/deterministic.py` | Exact extraction of ports, PIDs, URLs, paths, percentages, projects, and app aliases | **0.05 ms** |
| **Lexicon Loader** | `src/astrarun/nlp/lexicon.py` | Centralized domain vocabulary from `config/nlp_lexicon.json` | **< 0.01 ms** |
| **Clause Decomposer** | `src/astrarun/nlp/clause_decomposer.py` | Multi-action splitting (`and`, `then`, `before`, `after`) and ordering inference | **0.08 ms** |
| **Negation Scoper** | `src/astrarun/nlp/negation.py` | Clause-level negation attribution with strict safety verification | **0.03 ms** |
| **Temporal Engine** | `src/astrarun/nlp/temporal.py` | Workstation local relative time bounds (`yesterday`, `today`, `most_recent`) | **0.04 ms** |
| **Coreference Engine** | `src/astrarun/nlp/coreference.py` | Syntactic identification of anaphora (`it`, `that`, `that process`) | **0.03 ms** |
| **Relations Extractor** | `src/astrarun/nlp/relations.py` | Typed directed relations (`LISTENS_ON`, `OPEN_WITH`, `CONTAINS`) | **0.02 ms** |
| **spaCy Parser** | `src/astrarun/nlp/spacy_parser.py` | Optional non-blocking POS tagging and dependency parsing | **7.15 ms** |
| **NLU Fusion Engine** | `src/astrarun/nlp/fusion.py` | Hierarchical conflict resolution and provenance ledger assembly | **0.10 ms** |
| **Workflow Compiler** | `src/astrarun/workflows/compiler.py` | Capability mapping, mixed-risk propagation, and conservative policy blocking | **0.08 ms** |

---

## 4. Conflict Precedence Contract

When multiple extractors or models provide conflicting information, the system enforces the following hierarchy:

1. **Exact Deterministic Evidence**: Regex matches for ports, PIDs, URLs, Windows filesystem paths, percentages, and file extensions.
2. **Verified Registry Matches**: Project IDs from `ProjectRegistry` and known application aliases from `SearchIndex`.
3. **Structured Linguistic Parser**: Dependency trees, POS tags, and lemmatized stems from spaCy.
4. **Probabilistic Semantic Signals**: Intent distributions, ambiguity scores, and consequence risks from Laya.

**No Silent Conflict Resolution**: If two high-confidence components disagree on an entity that cannot be resolved deterministically, the engine sets `ambiguity = 1.0` and triggers `DecisionDisposition.CLARIFY`.
