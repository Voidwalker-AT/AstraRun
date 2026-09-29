# AstraRun v0.11 Execution Graph & Dependency Resolution

> **Module**: `astrarun.agent.graph`  
> **Status**: APPROVED  
> **Target**: AstraRun v0.11+  

---

## 1. Directed Acyclic Graph (DAG) Model

Complex user goals often decompose into interdependent steps. For instance:
$$\text{Launch App} \longrightarrow \text{Wait Window Ready} \longrightarrow \text{Inject Text} \longrightarrow \text{Save Document}$$

`ExecutionGraph` models plan steps as nodes in a DAG where edges represent state prerequisites and data bindings.

---

## 2. Key Capabilities

### 2.1 Cycle Detection & Validation
The graph enforces acyclicity at construction time using Kahn's topological sorting algorithm. If a cycle is introduced, `DependencyCycleError` is raised immediately before execution starts.

### 2.2 Topological Step Readiness
At every tick of the execution loop, `get_ready_steps()` queries pending steps whose incoming dependencies have all attained their `required_state` (default `StepState.COMPLETED`).

### 2.3 Data Propagation
When a predecessor step completes, `ExecutionGraph` automatically maps declared output keys from `result.data` to successor step arguments based on `StepDependency.data_mapping`.

### 2.4 Dynamic Runtime Re-Routing
The graph supports runtime insertion (`insert_after`), allowing replanning routines to splice in recovery steps (such as focus restoration or confirmation prompts) without recompiling the entire plan.
