# AstraRun Sequential Pattern Mining Engine

> **Document**: `docs/PATTERN_MINING.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Status**: APPROVED ALGORITHM SPECIFICATION  

---

## 1. Intent & Algorithmic Design

Users repeatedly execute common workflow choreographies:
- Opening a project folder ➔ Launching an integrated terminal ➔ Checking git status.
- Inspecting network ports ➔ Identifying listening PID ➔ Terminating process.

The `PatternMiner` periodically scans completed tasks in `data/astra_history.db` to discover frequent sequential capability patterns without requiring neural models or cloud processing.

---

## 2. Mining Algorithm

The mining process operates across three stages:

### 2.1 Trajectory Extraction
Extract ordered sequences of capability events:
$$T = \big[\langle c_1, \text{args}_1 \rangle, \langle c_2, \text{args}_2 \rangle, \dots, \langle c_k, \text{args}_k \rangle\big]$$
Only tasks with `status == TaskStatus.COMPLETED` and $k \ge 2$ are considered.

### 2.2 Subgraph N-Gram Enumeration
Enumerates contiguous n-grams of length $L \in [2, 5]$ across all trajectories:
$$\text{support}(\sigma) = |\{T \in \mathcal{T} : \sigma \subseteq T\}|$$

If $\text{support}(\sigma) \ge \text{min\_support}$ (default: 3 occurrences across distinct tasks), the sequence is passed to parameterization.

### 2.3 Parameter Abstraction
Concrete literal arguments (e.g. `project="E:\Workspace\Active\AstraRun"`) are generalized into typed template parameters:
- `project`, `folder`, `path`, `cwd` ➔ `{target_project}` or `{target_path}`.
- Step bindings link concrete step inputs to candidate parameters:
  ```json
  {
    "step_index": 1,
    "capability_id": "capability.projects.open",
    "parameter_bindings": {"project": "target_project"}
  }
  ```

---

## 3. Risk & Safety Evaluation

A mined pattern inherits the risk of its most dangerous constituent step:
$$\text{Risk}(\text{Pattern}) = \max_{s \in \text{steps}} \text{Risk}(s)$$

- If any step requires user confirmation (e.g. process termination), the compound candidate is marked `requires_confirmation = True`.
- If any step is classified as `ToolRisk.BLOCKED`, the entire pattern is immediately discarded.
- Mined patterns are emitted as `SkillCandidate` with status `CANDIDATE` and **never execute automatically without user review**.
