# General Capability Planning in AstraRun v0.11.1

> **Milestone**: AstraRun v0.11.1 (Generality & Reality Gate)  
> **Status**: APPROVED  
> **Last Verified**: 2026-09-29  

---

## 1. Architectural Motivation: Agent vs Intent Switch

Prior to AstraRun v0.11, natural language commands were routed through intent-matching routers (Deterministic, Laya, Kev, Decision Fusion). While effective for direct single-shot actions (e.g. launching an application or snapping a window), this approach suffered from fundamental architectural limitations:

1. **Static Coupling**: Every new capability required updating router intent tables or rule sets.
2. **Zero Dynamic Composition**: Compound workflows could only execute if pre-compiled or hardcoded as known multi-action templates.
3. **Rigid Execution**: Unexpected machine observations could not trigger dynamic plan adaptations without aborting the entire command.

AstraRun v0.11.1 establishes the **Dynamic Workstation Agent Runtime**, transforming Astra from an *intent switch* into a genuine *compositional workstation agent*. The planner operates against an open, dynamically extensible capability registry $\mathcal{C}$, constructing validated Directed Acyclic Graphs (DAGs) on the fly without requiring code changes to [`planner.py`](file:///E:/Workspace/Active/AstraRun/src/astrarun/agent/planner.py).

---

## 2. Formal Planning Framework

Given a user goal $G = (T, P, \mathcal{N})$ where:
- $T$ is the natural language goal text or utterance,
- $P$ is the extracted or resolved parameters dictionary,
- $\mathcal{N}$ is the set of explicitly negated actions (e.g., `"don't open it"`),

the planner maps $G$ onto a plan DAG:

$$P = (V, E)$$

where:
- Each vertex $v_i \in V$ represents a [`PlanStep`](file:///E:/Workspace/Active/AstraRun/src/astrarun/agent/models.py) bound to a capability $c \in \mathcal{C} \setminus \mathcal{N}$.
- Each directed edge $e = (v_i, v_j) \in E$ represents a causal execution dependency where $v_j$ requires the completion of $v_i$.
- Dataflow edges convey outputs from $v_i$ into the argument bindings of $v_j$ via [`OutputReference`](file:///E:/Workspace/Active/AstraRun/src/astrarun/agent/models.py) tokens: $\text{arg}_k(v_j) \leftarrow \text{result}(v_i)[\text{field}]$.

```mermaid
flowchart LR
    Goal["User Goal G"] --> Parser["Goal Parser & Negation Extractor"]
    Parser --> Indexer["Capability Semantic Index"]
    Indexer --> CandidateRetrieval["Top-K Capability Retrieval (Recall@5 >= 95%)"]
    CandidateRetrieval --> DAGBuilder["DAG Construction & Argument Binding"]
    DAGBuilder --> QualityGate["Plan Quality Validator (Zero Dangling, Zero Cycles)"]
    QualityGate --> ExecutionGraph["ExecutionGraph Topological Runtime"]
```

---

## 3. Dynamic Capability Discovery Protocol

Any plug-in or workstation tool can register itself into [`CapabilityRegistry`](file:///E:/Workspace/Active/AstraRun/src/astrarun/capabilities/registry.py) at runtime:

```python
registry.register(
    Capability(
        id="reverse_text",
        category=CapabilityCategory.SYSTEM,
        description="Reverse an input string payload character by character",
        args_schema={"text": str},
        risk=ToolRisk.LOW,
        read_only=True,
        handler=lambda text="": CapabilityResult.ok("reverse_text", f"Reversed: {text[::-1]}", data={"reversed": text[::-1]}),
        permission=CapabilityPermission.AUTO,
    )
)
```

### Discovery & Composition Invariants:
1. **Zero Planner Modification**: [`GoalPlanner`](file:///E:/Workspace/Active/AstraRun/src/astrarun/agent/planner.py) contains zero hardcoded checks for `"reverse_text"` or future plugin identifiers.
2. **Semantic Grounding**: The semantic indexer indexes tokens, action verbs, categories, and argument types. When the user asks to `"reverse hello world"`, the indexer ranks `reverse_text` as the top candidate.
3. **Automatic Dataflow Wiring**: When composing multi-step goals (e.g., `"reverse hello world and save the result to C:\out.txt"`), the planner identifies that `save_text_file` requires `content`, while `reverse_text` produces string data, creating an `OutputReference` link automatically.

---

## 4. Plan Quality Gating (`PlanQualityValidator`)

Before any plan is handed to [`AgentExecutionEngine`](file:///E:/Workspace/Active/AstraRun/src/astrarun/agent/loop.py), it must pass the pre-execution quality gate:

1. **Cycle Detection**: Depth-first search verifies that the plan contains zero directed cycles ($\text{DFS}(V, E) \implies \text{DAG}$).
2. **Dangling Output Reference Check**: For every argument $\text{arg} = \text{OutputReference}(s_{\text{dep}}, \text{field})$, the validator guarantees that $s_{\text{dep}} \in V$ and that $s_{\text{dep}}$ precedes the current step topologically.
3. **Schema Validation**: Ensures all mandatory arguments without default values are satisfied by explicit literals or valid output references.
4. **Negation Enforcement**: Guarantees that no capability matching an excluded/negated action appears anywhere in $V$.

If any violation occurs, the validator marks the plan as `INVALID`, returning actionable diagnostic issues and preventing invalid plan execution.
