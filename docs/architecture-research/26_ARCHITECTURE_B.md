# 26 — Architecture B: Asymmetric Hybrid Dual-Model Engine

> **Status**: APPROVED ARCHITECTURAL SPECIFICATION & EVALUATION  
> **Phase**: 14 — Competing Architecture Formulations  
> **Concept**: Asymmetric separation between a High-Reasoning Strategic Planner (Cloud/Remote or Local 3B) and an Ultra-Fast In-Surface Local Executor (Local 1.5B on RTX 2050)  
> **Target Compute**: Hybrid (Local RTX 2050 + Optional Remote Teacher API)  

---

## 1. Architectural Blueprint

```mermaid
flowchart TD
    Goal[User Goal] --> Router{Planner Selector}

    Router -->|Online / Complex Composite Goal| CloudPlanner[Strategic Planner\nRemote Frontier API / Teacher Model\nGenerates High-Fidelity DAG]
    Router -->|Offline / Simple Goal| LocalPlanner[Local Fast Planner\nQwen2.5-Coder-1.5B]

    CloudPlanner --> DAG[Structured Plan DAG\nExplicit Steps, Expected Outputs & Gates]
    LocalPlanner --> DAG

    DAG --> LocalEngine[Local Execution Loop\nAgentExecutionEngine]

    subgraph Local In-Surface Execution (RTX 2050 - Low Latency)
        LocalEngine <--> LocalExecutor[Local Reflex Model\nQwen2.5-Coder-1.5B (Q5_K_M)\nMicro-steps, Argument Binding & Fast Retries]
        LocalEngine --> DynamicRuntime[DynamicExecutionRuntime\nWindows APIs, Job Objects, CLI]
    end

    DynamicRuntime -->|Observation / Error Code| LocalEngine
    LocalEngine --> Eval{Execution Status}
    
    Eval -->|Success / Minor Retry| LocalEngine
    Eval -->|Critical Block / Replan Needed| CloudPlanner
    Eval -->|Final Goal Verified| Done[User Notification]
```

In Architecture B, cognitive responsibilities are decoupled:
1. **Strategic Planner (Macro)**: Ingests the high-level user goal, queries workspace metadata, and outputs a complete, validated **Plan DAG**. It does **not** execute individual terminal commands or handle streaming bytes.
2. **Local Executor (Micro)**: Runs entirely on the RTX 2050. It consumes one step of the DAG at a time, binds runtime variables, invokes local tools, verifies stdout/stderr, and executes fast micro-retries (e.g., correcting an unescaped path).
3. **Escalation Boundary**: If the local executor encounters an unresolvable domain failure (e.g., dependency missing upstream), it escalates back to the Strategic Planner for global graph restructuring.

---

## 2. Resource & Memory Footprint

| Component | Technology | Memory Footprint `[ESTIMATED]` | Residency |
| :--- | :--- | :--- | :--- |
| **Strategic Planner** | Cloud API (via Secret Broker) or Local 3B | **0 MB VRAM** (Cloud) / ~2.6 GB VRAM (Local) | On-Demand HTTP / Evictable Worker |
| **Local Reflex Executor** | Qwen2.5-Coder-1.5B Q5_K_M | **~1.18 GB VRAM** | Out-of-Process Worker |
| **KV Cache & Runtime** | 4096 context, Q8_0 KV | **~220 MB VRAM** | Worker process |
| **Host System RAM** | Main Astra engine | **~75 MB RAM** | Resident in background |
| **Total VRAM Footprint** | Local execution mode | **~1.65 GB VRAM** | Fully safe on RTX 2050 4GB |

---

## 3. Analysis & Evaluation

### Strengths
1. **Optimal Division of Labor**: High-level reasoning requires deep parameter capacity (frontier models); executing a known tool with arguments requires reflex speed and syntax precision (1.5B models).
2. **Extreme Token & Cost Efficiency**: The remote planner is invoked only **once** to generate the DAG (typically 500–1,000 tokens). All subsequent execution, streaming stdout parsing, and verification occur locally at **zero marginal cost**.
3. **Zero-Secret Cloud Boundary**: The remote planner receives only sanitized workspace metadata and capability schemas. No credentials or private file contents cross the network boundary.
4. **Graceful Offline Degradation**: If offline, the router falls back seamlessly to Architecture A (pure local planner).

### Weaknesses & Failure Modes
1. **Network Dependency for Optimal Planning**: Requires internet access to reach maximum planning fidelity on complex tasks.
2. **Dual-Model Coordination Complexity**: Requires strict schema contracts between the strategic planner's DAG outputs and the local executor's step consumption.

---

## 4. Verdict & Fit for AstraRun

Architecture B represents the **most powerful pragmatic architecture** for modern developer workstations. It solves the "Generality Paradox" by allowing frontier-grade reasoning to construct the plan, while keeping the physical workstation control loop instantaneous, secure, and light on local memory.
