# 27 — Architecture C: Hierarchical Agent Swarm / Subagent Factory

> **Status**: APPROVED ARCHITECTURAL SPECIFICATION & EVALUATION  
> **Phase**: 14 — Competing Architecture Formulations  
> **Concept**: A multi-agent hierarchy consisting of a Root Host Coordinator and specialized domain subagents (GitAgent, BrowserAgent, SystemAgent, TerminalAgent)  
> **Target Compute**: Multi-Context Agent Runtime on Local Workstation  

---

## 1. Architectural Blueprint

```mermaid
flowchart TD
    Goal[User Composite Goal] --> Host[HostAgent / Root Coordinator\nMacro Task Allocation & Resource Locking]

    Host -->|Delegate Git Task| SubGit[GitAgent\nSpecialized Git & Lockfile Prompt]
    Host -->|Delegate Web Task| SubWeb[BrowserAgent\nCDP, a11y Tree & Quarantine]
    Host -->|Delegate System Task| SubSys[SystemAgent\nWin32, COM, CIM Diagnostics]

    subgraph Shared Local Inference Runtime (Single Engine Process)
        EnginePool[Unified Inference Worker\nMultiplexed Contexts / LoRA Switching]
    end

    SubGit <--> EnginePool
    SubWeb <--> EnginePool
    SubSys <--> EnginePool

    SubGit --> Runtime[DynamicExecutionRuntime]
    SubWeb --> Runtime
    SubSys --> Runtime

    Runtime --> Host
```

Architecture C adopts the specialized multi-agent pattern popularized by Microsoft UFO and enterprise swarm frameworks:
1. **HostAgent**: Maintains global awareness of user goals, active resource locks, and task dependencies.
2. **Domain Subagents**:
   - `GitAgent`: Fine-tuned / prompted specifically for repository safety, branch hygiene, and lockfile invariants.
   - `BrowserAgent`: Handles CDP sessions, a11y tree filtering, and quarantined observation boundaries.
   - `SystemAgent`: Interfaces with Win32, COM, and CIM diagnostics.
3. **Context Isolation**: No subagent is burdened with the irrelevant observations of another subagent (e.g., GitAgent never ingests browser HTML).

---

## 2. Resource & Memory Footprint

| Component | Technology | Memory Footprint `[ESTIMATED]` | Residency |
| :--- | :--- | :--- | :--- |
| **Shared Model Engine** | Qwen2.5-Coder-1.5B (Multiplexed) | **~1.18 GB VRAM** | Single Out-of-Process Worker |
| **Multiple KV Contexts** | 3 concurrent subagents (4k tokens each) | **~420 MB VRAM** (Q8 KV) | Shared GPU buffer |
| **Agent State Runtimes** | Python async subagents | **~140 MB RAM** | Background process |
| **Total Operational VRAM** | Peak concurrent swarm | **~1.95 GB VRAM** | Safe on RTX 2050 4GB |

> [!CAUTION]
> **Swarm Memory Trap**: If subagents are implemented as separate OS processes each loading their own model weights, memory explodes to $3 \times 1.8\,\text{GB} = \mathbf{5.4\,\text{GB VRAM}}$, triggering severe crash and swap thrashing. Architecture C is **only viable** if all subagents share a single multiplexed inference server.

---

## 3. Analysis & Evaluation

### Strengths
1. **Context Purity & Anti-Distraction**: By partitioning tools across domain agents, each subagent only sees 4–6 tool schemas. This completely eliminates tool distraction and schema overload errors (Vector 2 of Torture Benchmark).
2. **True Task Parallelism**: A long-running build or web scrape can execute inside `BrowserAgent` while `SystemAgent` independently monitors thermal and battery states.
3. **Domain Specialization**: System instructions can be tailored specifically to the quirks of each domain without diluting general prompt tokens.

### Weaknesses & Failure Modes
1. **Orchestration & Routing Overhead**: Delegating tasks across subagent boundaries introduces message serialization and turn-taking delays.
2. **Coordination Failures & Deadlocks**: If Subagent A waits for a resource held by Subagent B without robust lock timeouts, the swarm can deadlock.
3. **High Development & Test Complexity**: Testing multi-agent state machines is substantially more complex than testing a single sequential DAG.

---

## 4. Verdict & Fit for AstraRun

Architecture C provides outstanding context isolation and aligns well with long-term platform evolution. However, for immediate implementation on a local 4GB workstation, the orchestration complexity and multi-context VRAM overhead make it higher risk than Architecture B as a primary baseline.
