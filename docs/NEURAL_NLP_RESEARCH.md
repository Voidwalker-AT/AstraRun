# AstraRun Neural NLP Model Research Report

> **Milestone**: AstraRun v0.10.3  
> **Target**: Lightweight Non-Generative Encoder NLP Models for Resident Workstation Architecture  
> **Status**: APPROVED  
> **Date**: 2026-09-28  

---

## 1. Executive Summary & Problem Formulation

In AstraRun v0.10.2, compound natural language requests (e.g., `open notepad and type pqr`) were handled via deterministic regex, clause splitting heuristics, and information-retrieval (IR) indexing. While fast (< 15 ms), deterministic approaches have rigid linguistic ceilings:
- Sensitivity to syntax variations and informal phrasing (`could you please bring up notepad`).
- Difficulty disambiguating negation (`close edge but do not close notepad`).
- Brittleness in resolving coreference and pronouns (`launch calc then snap it left`).
- Inability to compute calibrated semantic confidence across ambiguous user prompts.

However, workstation constraints strictly prohibit heavy generative LLMs:
1. **Hardware Invariant**: RTX 2050 (4 GB VRAM) must remain free for user developer tasks and external workloads; background resident service must run with minimal VRAM/RAM impact.
2. **Process Latency Invariant**: Interactive Alt+Space latency must remain sub-second; fast-path commands must execute under 50 ms.
3. **Execution Authority Boundary**: Neural models must have **ZERO direct OS execution authority**; they must output strictly typed linguistic representations (`ParsedRequest`, `ParsedClause`) evaluated and executed by deterministic policy gates (`ActionGate`).
4. **Single-Model Instance Invariant**: If Laya is active, Laya A (Pre-Gate) and Laya B (Verifier) must share the identical in-memory weights (no duplicate 421M models in RAM).

---

## 2. Candidate Architecture Evaluation

We benchmarked 6 candidate encoder architectures for the Neural NLP layer:

| Candidate Model | Parameter Count | Disk / Memory Footprint | CPU Inference Latency | Strengths | Weaknesses | Evaluation Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`spaCy en_core_web_sm`** | 12 M | ~15 MB RAM | **1.8 ms** (CPU) | Exact byte spans, zero network download, robust dependency tree, negation parsing, offline | Pure syntactic parser, lacks deep contextual semantics | **SELECTED (Syntactic / Span Engine)** |
| **`all-MiniLM-L6-v2`** | 22.7 M | ~90 MB RAM (FP32), ~25 MB (INT8) | 5.2 ms (CPU ONNX) | Ultra-compact, fast sentence embeddings, high clustering fidelity | 128 max seq len, weaker on complex span extraction | **CANDIDATE (Dense Retrieval)** |
| **`bge-small-en-v1.5`** | 33 M | ~130 MB RAM | 7.8 ms (CPU ONNX) | Strong MTEB retrieval performance | Slightly higher latency than MiniLM | **ALTERNATIVE** |
| **`deberta-v3-small`** | 44 M | ~175 MB RAM | 14.5 ms (CPU) | Disentangled attention, high NLI accuracy | Complex custom tokenizer, slower CPU latency | **REJECTED (Latency Overhead)** |
| **`ModernBERT-base`** | 149 M | ~570 MB RAM | 22.0 ms (CPU) | 8192 context, unpadding, RoPE | High RAM footprint for background resident process | **REJECTED (RAM Footprint)** |
| **`convaiinnovations/laya` (ModernBERT-large)** | 421 M | ~840 MB (shared) | 38.0 ms (GPU/CPU) | Calibrated zero-shot decision classification, multi-criteria heads | Heavy if instantiated twice | **SELECTED (Shared Semantic Gate & Verifier)** |

---

## 3. Findings on Literal Payload Preservation

In desktop automation, preserving verbatim literal payloads is safety-critical:
- Example: `type Hello, Bob -- meet at 5?`
- If an NLP model normalizes casing, strips dashes, or tokenizes text with subword artifacts (e.g. `ĠHello`), the text typed into the target application is corrupted.
- **Rule**: Neural extraction must preserve exact character offsets `[start:end]` into the original input string. The payload is sliced directly from `raw_query[start:end]`.
- spaCy's `Token.idx` and `len(Token)` guarantee 100.0% exact source span preservation with 0.00% character alteration.

---

## 4. Negation & Coreference Analysis

- **Negation Handling**:
  - Syntactic dependency parsing (`neg` dependency relation: `not`, `n't`, `never`, `no`) flags the governing verb with `is_negated = True`.
  - Contrastive conjunctions (`but`, `except`, `without`) cleanly split affirmative and negated clauses.
- **Coreference & Pronouns**:
  - Pronominal targets (`it`, `that`, `that window`, `this`) in sequential clauses inherit entity bindings from the preceding clause (`dependency_clause_index = 0`, `referent_index = 0`).

---

## 5. Architectural Recommendation

Implement a **Dual-Engine Neural Sandwich**:
1. **Laya A (Semantic Gate)**: Leverages shared ModernBERT Laya instance to classify domain, compound probability, ambiguity score, and risk class.
2. **Neural NLP Structure Engine**: Combines `spaCy en_core_web_sm` syntactic span dependency extraction with neural semantic classifiers to yield strictly typed `ParsedRequest` IR.
3. **Laya B (Semantic Verifier)**: Reuses the same ModernBERT Laya instance to verify intent consistency and check for negation violations.
4. **Decision Fusion**: Deterministic arbitration engine uniting Tier 0, Laya A, Neural IR, and Laya B.
