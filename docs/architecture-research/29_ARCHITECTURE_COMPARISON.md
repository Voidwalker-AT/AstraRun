# 29 — Architecture Comparison & Tradeoff Matrix

> **Status**: PROVISIONAL COMPARATIVE AUDIT  
> **Phase**: 14 — Competing Architecture Formulations  
> **Focus**: Systematic Comparison of Architectures A, B, C, and D Across Workstation Engineering Dimensions  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Multi-Dimensional Tradeoff Matrix

> [!IMPORTANT]
> **Empirical Governance Invariant**:  
> In accordance with Phase 17 guidelines, all unmeasured benchmark pass rates and hypothetical performance figures are tagged as `NOT_MEASURED` or `ESTIMATED`. No architecture is ranked using unverified synthetic percentages.

| Evaluation Dimension | Architecture A: Pure Local Single-Model | Architecture B: Asymmetric Hybrid Dual-Model | Architecture C: Hierarchical Agent Swarm | Architecture D: Dynamic Code/Terminal-Centric | Evidence Tag |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Planner** | Local 1.5B/3B (Qwen/Spark) | Frontier Cloud (or Local 3B) | HostAgent Coordinator | Local 1.5B/3B Code Generator | `TARGET` |
| **Primary Executor** | Same Local 1.5B/3B Model | Local 1.5B Reflex Model | Domain Subagents | Dynamic Python/PowerShell Scripts | `TARGET` |
| **Planning Generality (North-Star Pass Rate)** | **NOT_MEASURED** | **NOT_MEASURED** | **NOT_MEASURED** | **NOT_MEASURED** | `NOT_MEASURED` |
| **Execution Latency / Step** | `ESTIMATED` (~250–600ms) | `ESTIMATED` (~80–200ms local steps) | `ESTIMATED` (~800–2,000ms) | `ESTIMATED` (Variable 100–3,000ms) | `ESTIMATED` |
| **Total Peak VRAM** | `ESTIMATED` (~1.4–1.8 GB) | `ESTIMATED` (~1.4–1.7 GB local mode) | `ESTIMATED` (~1.8–4.5 GB) | `ESTIMATED` (~1.4–1.8 GB) | `ESTIMATED` |
| **Host RAM Overhead** | `ESTIMATED` (~120 MB) | `ESTIMATED` (~75 MB) | `ESTIMATED` (~140–300 MB) | `ESTIMATED` (~150 MB temp procs) | `ESTIMATED` |
| **100% Offline Capable?** | **YES** | Optional (Degrades to Arch A) | **YES** | **YES** | `TARGET` |
| **ActionGate Safety Classification** | High (Structured Schemas) | High (Rigid DAG Gates) | High (Domain Scoped) | Complex (Requires AST Audit) | `HYPOTHESIS` |
| **Context Degradation Vulnerability** | High on long multi-turn tasks | Low on execution plane (Macro/Micro split) | Low (Domain partitioned) | High on script debug loops | `HYPOTHESIS` |
| **Implementation Complexity** | Lowest | Moderate | High | Moderate-High | `ESTIMATED` |
| **Secret Broker Safety** | Clean (Local memory) | Clean (Zero secrets to cloud) | Clean (Local memory) | Requires strict script AST check | `HYPOTHESIS` |

---

## 2. In-Depth Tradeoff Analysis

### 2.1 The Generality vs. Offline Paradox `[HYPOTHESIS]`
- **Architecture A** provides complete autonomy from external infrastructure. However, whether a local 1.5B or 3B model can reliably plan 8+ step composite workflows across unfamiliar domains without suffering schema or path degradation remains an unproven hypothesis (`EXPERIMENT_REQUIRED`).
- **Architecture B** posits that outsourcing macro-DAG synthesis to a high-capacity teacher model resolves the planning bottleneck while keeping local execution fast and private. The extent of this advantage must be quantified in Phase 17 (`NOT_MEASURED`).

### 2.2 Schema Strictness vs. Dynamic Expressiveness `[HYPOTHESIS]`
- **Architectures A, B, and C** rely on strongly-typed capability schemas (Pydantic models). This enables deterministic static analysis and predictable ActionGate enforcement.
- **Architecture D** offers expressive flexibility via dynamic script generation, but introduces significant AST security auditing and library hallucination risks that must be benchmarked against controlled test suites.

### 2.3 Single-Engine vs. Swarm Mechanics `[HYPOTHESIS]`
- **Architecture C** provides domain-level context isolation. However, multi-agent lock contention, message serialization overhead, and the danger of concurrent VRAM duplication make it higher risk unless proven otherwise in physical tests.

---

## 3. Evaluation Status

No architecture is declared the permanent winner. **Architecture B+ is designated as the PROVISIONAL LEADING HYPOTHESIS**, subject to rigorous falsification and empirical validation in Phase 17.
