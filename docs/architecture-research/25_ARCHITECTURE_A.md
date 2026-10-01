# 25 — Architecture A: Pure Local Single-Model Workhorse

> **Status**: APPROVED ARCHITECTURAL SPECIFICATION & EVALUATION  
> **Phase**: 14 — Competing Architecture Formulations  
> **Concept**: A single, unified small local language model (1.5B–3B class) driving both strategic planning and closed-loop tool execution  
> **Target Compute**: Local Workstation (RTX 2050 4GB, ~3.30 GB Free RAM, ~3.43 GB Free VRAM)  

---

## 1. Architectural Blueprint

```mermaid
flowchart TD
    Goal[User Goal] --> Engine[Agent Execution Engine]
    
    subgraph Local Inference Subprocess (VRAM: ~1.8 GB)
        Model[Unified Workhorse Model\nQwen2.5-Coder-1.5B or 3B (Q4/Q5)]
    end

    Engine <-->|Prompt / XML Tool Calls| Model
    Engine --> Runtime[DynamicExecutionRuntime\nJob Objects & ConPTY]
    Runtime --> Tools[Windows APIs, CLI, Filesystem, COM]
    Tools --> Runtime
    Runtime -->|Sanitized Observation| Engine
```

In Architecture A, a single local model handles all cognitive operations:
1. **Goal Decomposition**: Interprets user intent and constructs the execution plan.
2. **Step Dispatch**: Selects capabilities and formats tool arguments.
3. **Observation Verification**: Parses process returns, error codes, and terminal outputs.
4. **Error Recovery**: Replans dynamically when execution encounters friction.

---

## 2. Resource & Memory Footprint

| Component | Technology | Memory Footprint `[ESTIMATED]` | Residency |
| :--- | :--- | :--- | :--- |
| **Model Weights** | Qwen2.5-Coder-1.5B Q5_K_M | **~1.18 GB VRAM** | Out-of-Process Worker (Evictable) |
| **KV Cache** | 8192 context, Q8_0 KV | **~280 MB VRAM** | Dynamic with context |
| **CUDA Driver & Graph** | cu121 / llama.cpp | **~350 MB VRAM** | Worker process |
| **Total VRAM Footprint** | Peak load | **~1.81 GB VRAM** (Leaves > 1.6 GB headroom) | Safe on RTX 2050 4GB |
| **Host System RAM** | Main Astra engine + Worker runtime | **~120 MB RAM** | Negligible impact on host |

---

## 3. Analysis & Evaluation

### Strengths
1. **Zero External Dependencies**: Operates 100% offline with zero cloud API keys, zero network latency, and complete user privacy.
2. **Minimal Operational Complexity**: Single model binary, single prompt format, and straightforward debugging.
3. **Blazing Reactivity**: Generation speeds of 65–85 tokens/sec on RTX 2050 enable sub-second step turnarounds for simple workstation tasks.
4. **Comfortable Memory Budget**: Total VRAM usage (~1.81 GB) is well below the 2.8 GB safe ceiling.

### Weaknesses & Failure Modes
1. **Cognitive Burden on Small Parameter Capacity**: Asking a 1.5B parameter model to simultaneously hold large project contexts, adhere to strict JSON schemas, and reason through subtle edge cases leads to cognitive saturation on tasks $> 6$ steps.
2. **Context Window Contention**: Long compiler errors or large directory listings quickly consume the 8k context window, pushing earlier instructions out of scope.
3. **Complex Planning Limits**: On multi-domain composite goals (e.g., Task 25: full release workflow with git, pytest, docs, and git tag), a 1.5B model exhibits higher plan hallucination rates than larger frontier models.

---

## 4. Verdict & Fit for AstraRun

Architecture A represents the **indispensable offline baseline**. Every workstation agent must have an infallible local fallback when network connectivity is absent. However, as a standalone architecture, it struggles to achieve 100% reliability on long-horizon, highly compositional tasks.
