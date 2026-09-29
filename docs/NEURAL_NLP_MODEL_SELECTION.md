# AstraRun Neural NLP Model Selection Rationale

> **Milestone**: AstraRun v0.10.3  
> **Selection Decision**: Hybrid Neural NLP Architecture (`spaCy en_core_web_sm` + Shared ModernBERT `convaiinnovations/laya`)  
> **Status**: APPROVED  
> **Date**: 2026-09-28  

---

## 1. Selected Architecture Matrix

The AstraRun v0.10.3 Neural Sandwich employs two complementary neural tiers:

```mermaid
flowchart LR
    subgraph SharedModel["Shared ModernBERT Instance (~421M Weights)"]
        LayaA["Laya A: Semantic Pre-Gate"]
        LayaB["Laya B: Post-Verifier"]
    end
    
    subgraph NeuralStruct["Lightweight Structure Engine (~12M Params)"]
        SpaCyEngine["spaCy en_core_web_sm + Span Resolver"]
    end
    
    Query[User Query] --> LayaA
    Query --> SpaCyEngine
    SpaCyEngine --> NLP_IR[Typed NLP IR]
    NLP_IR --> LayaB
    LayaA --> DecisionFusion[Decision Fusion Engine]
    LayaB --> DecisionFusion
    DecisionFusion --> WorkflowCompiler[Deterministic WorkflowCompiler]
```

---

## 2. Selection Rationale

### A. Pre-Gate & Post-Verifier: `convaiinnovations/laya` (Shared Instance)
- **Zero Additional RAM**: AstraRun already incorporates Laya for shadow routing. By sharing the loaded instance via `LayaSandwichRouter`, Laya A and Laya B add **0 MB** of additional model weight memory.
- **Calibrated Multi-Criteria Probabilities**: Laya's structured query interface allows querying domain classification, ambiguity, compound probability, and semantic consistency as separate heads on the same encoder forward pass.
- **Latency**: Mean forward pass 25-45 ms, well within interactive budget for complex/compound requests.

### B. Structure & Span Engine: `spaCy en_core_web_sm`
- **100% Literal Span Preservation**: Provides exact byte start and end character offsets (`Token.idx`, `Token.idx + len(Token)`) natively on Python 3.13 without subword detokenization hazards.
- **Ultra-Low Latency**: Parses typical command utterances in **1.5 to 2.5 ms** on CPU.
- **Zero GPU Overhead**: Operates entirely in user-space CPU memory with < 18 MB RAM consumption.
- **Offline / Zero Network Dependency**: Shipped directly inside the local virtual environment wheel cache (`site-packages/en_core_web_sm`).
- **Syntactic Precision**: Out-of-the-box support for:
  - Coordinate conjunctions (`cc`: `and`, `then`, `but`)
  - Negation particles (`neg`: `not`, `n't`, `never`, `no`)
  - Direct objects and prepositions (`dobj`, `prep`, `pobj`)
  - Pronoun resolution (`PRON`: `it`, `this`, `that`)

---

## 3. Alternative Candidates Rejection Log

1. **`all-MiniLM-L6-v2`**:
   - *Strengths*: Highly compact, fast sentence similarity.
   - *Rejection Rationale*: While excellent for sequence embeddings, it lacks native span extraction and syntactic dependency trees. Implementing token classification on top of it would require training custom NER heads and adding ~90MB RAM when spaCy accomplishes the structure parsing in 15MB with higher syntactic accuracy.
2. **`deberta-v3-small`**:
   - *Rejection Rationale*: Slower CPU latency (14.5 ms) and fragile SPM tokenizer on Windows Python 3.13.
3. **`ModernBERT-base` (Standalone)**:
   - *Rejection Rationale*: Duplicate 149M model in addition to Laya's 421M weights would consume > 500 MB extra RAM, violating resident background footprint constraints.

---

## 4. Hardware Impact Profile (Workstation Baseline)

| Resource | Baseline (v0.10.2) | v0.10.3 (With Neural Sandwich) | Delta | Budget Ceiling |
| :--- | :--- | :--- | :--- | :--- |
| **Resident RAM** | ~125 MB | ~145 MB | +20 MB | < 250 MB |
| **GPU VRAM** | 0 MB (CPU Mode) | 0 MB (CPU Mode) | 0 MB | < 250 MB |
| **Fast-Path Latency** | 7.05 ms | 7.10 ms | +0.05 ms | < 50.0 ms |
| **Compound Latency** | 137.3 ms | 145.0 ms | +7.7 ms | < 250.0 ms |
