# AstraRun v0.11 Goal & Task Abstraction Model

> **Module**: `astrarun.agent.models`  
> **Status**: APPROVED  
> **Target**: AstraRun v0.11+  

---

## 1. Abstraction Transition: Command to Goal

Previous iterations of AstraRun operated on the concept of discrete **Commands**:
```
User Utterance ──> Pattern Match ──> Single Tool Call ──> Text Output
```

While sufficient for single application launches, this abstraction breaks down when handling compound, diagnostic, or conditional workstation tasks. AstraRun v0.11 introduces the **User Goal** as the primary unit of intent:

```
User Utterance ──> Goal ──> Execution Plan (DAG) ──> Closed Loop Execution ──> Verified Goal
```

---

## 2. Model Specifications

### 2.1 `Goal`
Represents the user's intended target outcome:
- `goal_id`: Unique identifier (e.g. `goal_a8f9b2c1`).
- `raw_prompt`: The unadulterated user prompt.
- `intent`: Normalized domain intent (e.g. `generate_battery_report`, `wifi_connect`, `composite_workflow`).
- `target_entities`: List of identified applications, files, or hardware components.
- `parameters`: Typed dictionary containing resolved inputs (e.g. `output_path`, `ssid`).
- `success_criteria`: Human-readable and machine-verifiable assertions.

### 2.2 `PlanStep`
Represents an atomic, typed unit of work:
- `step_id`: Unique step identifier (e.g. `step_gen_battery_report`).
- `capability_id`: ID of registered capability in `CapabilityRegistry`.
- `arguments`: Dictionary of validated arguments.
- `state`: Lifecycle enum (`PENDING`, `READY`, `RUNNING`, `WAITING`, `VERIFYING`, `COMPLETED`, `FAILED`, `BLOCKED`, `CANCELLED`, `SKIPPED`).
- `dependencies`: List of `StepDependency` prerequisites.
- `interaction_tier`: Declared tier (`TIER_A_NATIVE` through `TIER_E_VISUAL_FALLBACK`).
- `verifier_strategy`: Empirical verification strategy.
- `verifier_params`: Parameter dictionary for verification.
- `weight`: Numerical weight for progress calculation.

### 2.3 `AgentTask`
The root state container managing runtime lifecycle:
- `task_id`: Unique task session identifier.
- `goal`: Associated `Goal`.
- `plan`: Associated `Plan` DAG.
- `status`: Enum (`PENDING`, `RUNNING`, `PAUSED`, `AWAITING_INPUT`, `COMPLETED`, `FAILED`, `CANCELLED`).
- `progress_mode`: Enum (`INSTANT`, `DETERMINATE`, `INDETERMINATE`, `EVENT_DRIVEN`).
- `progress_pct`: Float ($0.0-100.0$) derived honestly from step completion.
- `cancellation_requested`: Boolean flag triggering cooperative task abort.
