# 19 — Workstation Embedding & Reranking Architecture

> **Status**: APPROVED RESEARCH & ARCHITECTURAL SPECIFICATION  
> **Phase**: 9 — Local Embeddings, Vector Indexing & Rerankers  
> **Focus**: Skill & Capability Retrieval, ModernBERT Audit, ONNX CPU Runtimes, and Hybrid Sparse-Dense Search  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Executive Summary & The "Laya" Reality Audit

In AstraRun v0.11, the repository introduced `Laya`, an embedding component utilizing `ModernBERT-Large` (421M parameters).
- **Physical Footprint**: ModernBERT-Large consumes **~950 MB to 1.2 GB of physical RAM** `[ESTIMATED]`.
- **Reality Finding (`01_CURRENT_REALITY.md`)**: Laya runs as a shadow model with **zero execution authority**. Its embeddings were not wired into active tool routing or DAG construction.
- **Architectural Conflict**: Keeping a ~1 GB neural embedder resident in memory when total free physical RAM is only **~3.30 GB** `[MEASURED]` is an unacceptable waste of workstation resources.

To support high-velocity retrieval of tools, documentation, and compiled skills without exhausting RAM, AstraRun must pivot to a **lightweight ONNX CPU or hybrid sparse-dense (FTS5 + Small Dense)** architecture.

---

## 2. Embedding Model Candidate Comparison

| Model | Parameters | Runtime | Memory Footprint `[ESTIMATED]` | CPU Latency (Batch=1) `[ESTIMATED]` | Retrieval MTEB Score | Viability for AstraRun |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **bge-small-en-v1.5 (ONNX)** | 33M | Fast ONNX CPU | **~65 MB RAM** | **~4 – 8 ms** | 62.17 | **TOP RECOMMENDATION** `[TARGET]` |
| **all-MiniLM-L6-v2 (ONNX)** | 22M | Fast ONNX CPU | **~45 MB RAM** | **~3 – 5 ms** | 56.26 | Excellent Alternative `[TARGET]` |
| **bge-base-en-v1.5** | 109M | PyTorch / ONNX | ~220 MB RAM | ~18 – 30 ms | 63.55 | Overkill for <100 tools |
| **ModernBERT-Base** | 149M | PyTorch | ~320 MB RAM | ~25 – 45 ms | Strong long-context | Viable for deep code search |
| **ModernBERT-Large (Laya)** | 421M | PyTorch | ~950 MB RAM | ~80 – 160 ms | Strong | **REJECTED** (Excessive RAM waste) |

---

## 3. Hybrid Sparse-Dense Retrieval Architecture

Semantic vector similarity alone frequently fails on workstation queries:
- Query: *"Find the git commit with hash 4c57098"* $\to$ Dense embeddings fail to capture exact alphanumeric hash strings.
- Query: *"Read test_runner.py"* $\to$ Dense embeddings confuse with `test_suite.py` or `runner.py`.

```mermaid
flowchart TD
    Query[User Task / Goal] --> Parallel{Hybrid Dispatch}

    Parallel -->|Exact keywords, identifiers, paths| Sparse[SQLite FTS5 Full-Text Search\nBM25 Ranking | 0 MB ML RAM\nLatency: < 1ms]
    Parallel -->|Semantic intent, concepts, paraphrasing| Dense[bge-small-en-v1.5 ONNX\nCosine Similarity | ~65 MB RAM\nLatency: 5ms]

    Sparse --> RRF[Reciprocal Rank Fusion\nRRF Score = 1/(60 + r_sparse) + 1/(60 + r_dense)]
    Dense --> RRF

    RRF --> TopK[Top-K Candidate Tools & Skills\nFiltered down to <= 6 tools]
    TopK --> ModelPrompt[Injected into LLM Context]
```

### 3.1 SQLite FTS5 (Sparse BM25)
- Windows native, zero ML dependencies.
- Sub-millisecond exact matching for:
  - Exact file paths (`E:\Workspace\...`)
  - CLI flags (`--remote-debugging-port`)
  - Tool names (`query_process_port_binding`)
  - Error codes (`STATUS_QUOTA_EXCEEDED`)

### 3.2 ONNX Runtime CPU (Dense Semantic)
- `bge-small-en-v1.5` quantized to INT8 runs entirely on CPU via Microsoft's `onnxruntime` wheel.
- Does not touch GPU VRAM, leaving 100% of the RTX 2050 available for LLM inference.
- Handles natural language intent matching:
  - *"Check if battery is dying"* $\to$ maps to `inspect_system_power_state`.
  - *"Kill the runaway node process"* $\to$ maps to `terminate_process_tree`.

---

## 4. Reranker Strategy: On-Demand vs. Unnecessary

For workstation tool and skill catalogs:
- Total capabilities: ~30 native tools + ~20 compiled skills = **~50 candidates total**.
- **Architectural Hypothesis**: Running a neural cross-encoder reranker (e.g., `bge-reranker-large` at 560M params) on a pool of only 50 candidates is likely redundant `[HYPOTHESIS]`.
- **Target**: Evaluate whether Reciprocal Rank Fusion (RRF) between FTS5 and dense embeddings provides sufficient routing accuracy for workstation scopes without loading a separate cross-encoder `[TARGET]` (to be tested in Lab F `[NOT_MEASURED]`).

---

## 5. Synthesis & Architectural Directives

1. **Decommission Laya's 1 GB Footprint**: Decommission `ModernBERT-Large` (~950 MB RAM); replace with Phase-17-selected lightweight retrieval architecture `[TARGET]`.
2. **Evaluate Sparse vs. Hybrid Retrieval**: Benchmark SQLite FTS5 standalone vs. Hybrid RRF in Lab F `[HYPOTHESIS]`. If FTS5 achieves sufficient recall on holdout sets, avoid deploying a dense model entirely.
3. **Preserve GPU Headroom**: Any dense embedding evaluation must run on CPU via ONNX, strictly preserving the 2.8 GB VRAM budget for generative LLM inference `[TARGET]`.
