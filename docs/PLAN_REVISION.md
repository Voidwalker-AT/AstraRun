# Plan Revision & Dynamic Replanning in AstraRun v0.11.1

> **Milestone**: AstraRun v0.11.1 (Generality & Reality Gate)  
> **Status**: APPROVED  
> **Last Verified**: 2026-09-29  

---

## 1. Overview

In real physical workstation environments, actions may fail due to dynamic conditions: missing permissions, unavailable devices, port collisions, or locked files. Rather than aborting or throwing unhandled errors, AstraRun v0.11.1 implements **Closed-Loop Dynamic Replanning**.

When a step fails or produces an unexpected observation, the engine requests a revision from [`GoalPlanner`](file:///E:/Workspace/Active/AstraRun/src/astrarun/agent/planner.py), preserving already completed steps and safely substituting or appending alternate execution paths.

---

## 2. The PlanRevision Data Contract

Every modification to an active plan DAG is recorded as an immutable [`PlanRevision`](file:///E:/Workspace/Active/AstraRun/src/astrarun/agent/models.py) entry in `task.revisions`:

```python
@dataclass
class PlanRevision:
    revision_id: str = field(default_factory=lambda: f"rev_{uuid.uuid4().hex[:8]}")
    task_id: str = ""
    timestamp: float = field(default_factory=time.time)
    previous_plan_version: int = 1
    new_plan_version: int = 2
    reason: str = ""
    added_steps: list[str] = field(default_factory=list)
    removed_steps: list[str] = field(default_factory=list)
```

---

## 3. Replanning Invariants & Safety Gating

```mermaid
flowchart TD
    StepFailure["Step Execution or Verification Fails"] --> CaptureObs["Capture Machine Observation"]
    CaptureObs --> TriggerReplan["Planner.replan(task, failed_step, obs)"]
    TriggerReplan --> BuildRevision["Construct Candidate PlanRevision (Substitute/Append Steps)"]
    BuildRevision --> QualityAudit["PlanQualityValidator Audit of Revised DAG"]
    
    QualityAudit -->|Passes Quality Checks| ApplyRevision["Apply Revision: Increment Version, Append rev to task.revisions"]
    ApplyRevision --> ContinueGraph["ExecutionGraph Resumes with Revised Topology"]
    
    QualityAudit -->|Violates Quality (Cycle / Dangling)| RejectRevision["Reject Revision: Unsafe Replan Rate = 0.0%"]
    RejectRevision --> FailSafely["Task Transitions to FAILED with Detailed Diagnostic Error"]
```

### Critical Rules:
1. **Preserve Completed History**: Completed steps are never re-executed. Their outputs remain available in `task.plan.steps` for downstream reference.
2. **Pre-Execution Validation**: Any candidate plan revision must pass all `PlanQualityValidator` checks (cycles, dangling references, schema violations). The benchmark guarantees **0.00% Unsafe Replan Execution**.
3. **Audit Trail**: Every revision step is visible in the telemetry and task history, explaining why the initial plan changed.
