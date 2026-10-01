# 39 — Workstation Tool & Skill Retrieval Experiment Protocol (Lab F)

> **Scope**: Phase 17 Lab F Specification  
> **Status**: APPROVED EXPERIMENT PROTOCOL  
> **Focus**: Evaluation of SQLite FTS5, Dense ONNX Embeddings, Hybrid RRF, and Current AstraRun Baseline  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Experimental Objectives & Falsification Targets

This lab physically benchmarks retrieval architectures for workstation tools and skills, measuring recall and latency under strict lexical holdout and catalog scaling:

1. **Hybrid Superiority**: Does Hybrid RRF (SQLite FTS5 + `bge-small-en-v1.5` ONNX) achieve $\ge 98\%$ Recall@6 on zero-lexical-overlap user queries?
2. **Dense-Only Vulnerability**: Does dense vector search fail on exact workstation alphanumeric tokens (file paths, git hashes, flags, error codes)?
3. **Sparse-Only Vulnerability**: Does FTS5 BM25 fail when user queries use colloquial paraphrasing without keyword overlap?
4. **Scale Invariance**: How does retrieval accuracy degrade when the candidate tool catalog expands from 28 native tools to 100, 250, and 500 candidate tools?
5. **Memory & Latency Footprint**: Does ONNX `bge-small` CPU inference execute in $\le 10\,\text{ms}$ while occupying $\le 80\,\text{MB}$ RAM?

---

## 2. Benchmark Query Dataset & Holdout Design

To prevent artificial inflation of accuracy, queries are divided into two distinct test splits:

```
Split A: Lexical Exact-Match Split (25 Queries)
  - Tests paths, CLI flags, git hashes, error constants.
  - Example: "Resolve lock on E:\Workspace\Active\AstraRun\lock.pid" -> query_file_locks

Split B: Zero-Lexical-Overlap Paraphrase Split (50 Queries)
  - Zero word overlap with capability names, parameter names, or tool docstrings.
  - Example: "How much juice is left before I need to plug in?" -> inspect_system_power_state
  - Example: "Wipe out the frozen background terminal" -> terminate_process_tree
  - Example: "Check if my feature branch is behind the team's main branch" -> audit_git_tracking_state
```

---

## 3. Evaluated Retrieval Systems

| System ID | Retrieval Architecture | Technology | Hardware Layer | Target Memory Footprint |
| :--- | :--- | :--- | :--- | :--- |
| **System 1** | Pure Sparse (BM25) | SQLite FTS5 | OS Native / Disk | **< 5 MB RAM** |
| **System 2** | Pure Dense (Vector) | `bge-small-en-v1.5` (INT8 ONNX) | CPU (onnxruntime) | **~65 MB RAM** |
| **System 3** | Hybrid (Sparse + Dense) | FTS5 + `bge-small` (RRF Ranker) | CPU | **~70 MB RAM** |
| **System 4** | Current Astra Baseline | Laya (`ModernBERT-Large` PyTorch) | CPU / PyTorch | **~950 MB RAM** |

---

## 4. Distractor Tool Catalog Scaling

To measure performance as the platform grows, candidate pools are expanded synthetically:
- **Pool 1 (Baseline)**: 28 native AstraRun capability schemas.
- **Pool 2 (Expanded)**: 100 capabilities (28 native + 72 realistic Windows/Linux tools).
- **Pool 3 (Stress)**: 250 capabilities.
- **Pool 4 (Extreme)**: 500 capabilities.

---

## 5. Evaluation Metrics & Scoring Criteria

1. **Recall@K** ($K \in \{1, 3, 6\}$):
   $$\text{Recall@K} = \frac{\mathbb{I}(\text{Target Tool} \in \text{Top-K})}{N_{\text{queries}}}$$
2. **Mean Reciprocal Rank (MRR)**:
   $$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$
3. **Query Latency (P50 & P95 ms)**.
4. **Resident RAM Working Set (MB)** measured before and after 1,000 queries.

---

## 6. Falsification Conditions for Retrieval Architecture

1. **Hybrid Redundancy**: If pure SQLite FTS5 matches or exceeds Hybrid RRF on Split B (paraphrase queries), the neural dense embedder is redundant and can be omitted.
2. **Dense Failure on Identifiers**: If dense vector search achieves $< 50\%$ Recall@1 on Split A (exact paths and codes), dense-only retrieval is falsified.
3. **Scale Collapse**: If Recall@6 drops below $85\%$ at 100 tools, flat retrieval is insufficient and requires two-stage hierarchical domain routing.
