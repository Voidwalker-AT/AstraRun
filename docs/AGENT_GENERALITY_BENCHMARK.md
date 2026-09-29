# AstraRun v0.11.1 Agent Generality Benchmark Report

> **Milestone**: AstraRun v0.11.1 (Generality & Reality Gate)  
> **Execution Date**: 2026-09-29  
> **Benchmark Suite**: `benchmarks/agent_generality/run_generality_benchmark.py`  
> **Results Store**: `benchmarks/agent_generality/generality_benchmark_results.json`  
> **Overall Verdict**: **PASSED (ALL 10 TARGETS MET)**  

---

## 1. Executive Summary & Purpose

The Generality Benchmark verifies that AstraRun is a genuine, general-purpose workstation agent rather than a hardcoded intent-switching system. The evaluation assesses the agent's ability to interpret arbitrary goals, retrieve relevant capabilities from open registries, assemble valid execution DAGs, wire dataflow across novel plugins, respect negations, and reject impossible or unsafe goals.

The test suite evaluates **320 total scenarios**:
- **220 Development Scenarios**: Across System, File, Window, Network, Process, Window Layout, Multi-Step Compound, and Adversarial Trap domains.
- **100 Novel Held-Out Scenarios**: Composed entirely of synthetic capabilities (`compress_archive`, `transcode_video`, `compute_sha256`, `encrypt_payload`, `http_fetch`, `diff_files`, `parse_csv`, etc.) registered dynamically at test runtime with zero planner foreknowledge.

---

## 2. 10 Critical Agent Generality Metrics

| # | Metric | Achieved Value | Target | Status |
| :---: | :--- | :---: | :---: | :---: |
| 1 | **Goal Interpretation Accuracy** | **100.00%** | $\ge 95.0\%$ | **PASSED** |
| 2 | **Capability Retrieval Recall@5** | **99.03%** | $\ge 95.0\%$ | **PASSED** |
| 3 | **Plan Validity Rate** | **100.00%** | $100.0\%$ | **PASSED** |
| 4 | **Capability Hallucination Rate** | **0.00%** | $0.00\%$ | **PASSED** |
| 5 | **Invalid Plan Execution Rate** | **0.00%** | $0.00\%$ | **PASSED** |
| 6 | **False Execution Rate** | **0.00%** | $0.00\%$ | **PASSED** |
| 7 | **Negated Action Leakage** | **0.00%** | $0.00\%$ | **PASSED** |
| 8 | **Dangling Output Reference Execution** | **0.00%** | $0.00\%$ | **PASSED** |
| 9 | **Unsafe Replan Execution** | **0.00%** | $0.00\%$ | **PASSED** |
| 10 | **Held-Out Composition Success Rate** | **100.00%** | $\ge 95.0\%$ | **PASSED** |

---

## 3. Analysis of Critical Invariants

### Zero Hallucination & Zero False Execution (0.00%)
When presented with impossible, trap, or out-of-domain goals (e.g. `"summon a dragon on the desktop"`, `"brew hot coffee"`), the agent retrieved no hallucinated capability IDs and executed zero arbitrary actions. The engine cleanly recognized the goal as unresolvable.

### Negated Action Leakage (0.00%)
For prompts containing negative constraints (e.g. `"find the latest PDF but don't open it"`, `"clean cache without deleting temp"`), the planner extracted the negated tokens into `goal.parameters["negated_actions"]` and blocked the excluded capability from the DAG.

### Held-Out Dynamic Composition (100.00%)
Synthetic tools registered only at runtime were correctly discovered by the semantic indexer and chained via `OutputReference` with 100% dataflow fidelity, establishing empirical proof of general compositional planning.
