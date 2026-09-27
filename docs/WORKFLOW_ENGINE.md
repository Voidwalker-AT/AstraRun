# Workflow Engine Specification (AstraRun v0.6)

> **Status**: PRODUCTION READY  
> **Package**: `astrarun.workflows`  
> **Last Verified**: 2026-09-27  

---

## 1. Overview & Non-Autonomous Architecture

The **Workflow Engine** provides structured, multi-step workstation task orchestration without autonomous agent loops. In AstraRun v0.6, workstation orchestration is strictly bounded:

- **No Self-Directing Loops**: The engine does NOT ask an LLM *"what should I do next?"* in an unbounded feedback cycle.
- **Typed, Predefined Templates**: Every workflow is an explicit sequence of `WorkflowStep` items calling registered workstation tools.
- **Fail-Fast Semantics**: If any critical step fails, the workflow immediately halts execution, logs diagnostic details, and reports partial failure to the user. It never asserts false success.
- **Audit Traceability**: All workflow executions append a structured transaction record to `data/workflow_audit.jsonl`.
- **Honest Rollback Semantics**: Because OS operations (launching applications, focusing windows, terminating processes) cannot be deterministically reversed on Windows, workflows explicitly declare `rollback_supported=False`.

---

## 2. Predefined Workflow Templates

AstraRun v0.6 provides three factory templates in `WorkflowEngine`:

### 1. `open_project` (`create_open_project_workflow(project_id)`)
- **Intent**: Open project directory in Windows File Explorer and update recency indices.
- **Steps**:
  1. `open_folder` (`open_project_folder`): Launches File Explorer targeting the verified workspace path.
  2. Updates `WorkstationContextEngine` recency store with project interaction.
- **Risk**: `ToolRisk.LOW` (Auto-allowed).

### 2. `open_project_in_vscode` (`create_open_project_vscode_workflow(project_id)`)
- **Intent**: Launch Visual Studio Code for the target project and update workstation context.
- **Steps**:
  1. `launch_vscode` (`open_project_in_vscode`): Launches VS Code executable targeting the project root.
  2. Updates `WorkstationContextEngine` foreground project state.
- **Risk**: `ToolRisk.LOW` (Auto-allowed).

### 3. `inspect_dev_port` (`create_inspect_port_workflow(port)`)
- **Intent**: Query network listeners on a TCP port and cache process context for follow-up actions.
- **Steps**:
  1. `query_port` (`inspect_port`): Read-only socket and process query via `psutil`.
  2. Caches `_last_inspected_port` and `_last_inspected_process` in `WorkstationContextEngine` with 300s TTL.
- **Risk**: `ToolRisk.LOW` (Read-only, allowed on all ports including port 80).

---

## 3. Data Models (`astrarun.workflows.models`)

### `WorkflowStep`
```python
@dataclass
class WorkflowStep:
    step_id: str
    name: str
    tool: str                          # Registered tool in ToolRegistry
    arguments: dict[str, Any]          # Strongly typed arguments
    critical: bool = True              # If True, failure immediately aborts workflow
```

### `WorkflowStepResult`
```python
@dataclass
class WorkflowStepResult:
    step_id: str
    name: str
    tool: str
    success: bool
    message: str
    data: Any = None
    latency_ms: float = 0.0
```

### `WorkflowExecutionResult`
```python
@dataclass
class WorkflowExecutionResult:
    workflow_id: str
    entity_id: str
    success: bool                      # False if ANY critical step failed
    message: str
    steps_attempted: int
    steps_succeeded: int
    steps_failed: int
    step_results: list[WorkflowStepResult]
    rollback_supported: bool = False
    timestamp: float
    total_latency_ms: float

    @property
    def status(self) -> str:
        return "completed" if self.success else "failed"
```

---

## 4. Execution Flow & Partial Failure Handling

```
                      ┌──────────────────────────────┐
                      │    execute_workflow(wf)      │
                      └──────────────┬───────────────┘
                                     │
                                     ▼
                      ┌──────────────────────────────┐
                      │    Iterate Workflow Steps    │
                      └──────────────┬───────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
       ┌───────────────────────────┐   ┌───────────────────────────┐
       │   Execute Tool Action     │   │   All Steps Completed?    │
       │ToolRegistry.execute_action│   │   Generate Final Result   │
       └─────────────┬─────────────┘   └─────────────┬─────────────┘
                     │                               │
             SUCCESS │ FAILURE                       ▼
                     ▼                               ┌───────────────────────────┐
       ┌───────────────────────────┐                 │  Append to Transaction    │
       │ Update Step Metrics &     │                 │  Audit Log (JSONL)        │
       │ Record Context Action     │                 └───────────────────────────┘
       └─────────────┬─────────────┘
                     │
       ┌─────────────┴─────────────┐
       │ Is Step Critical?         │
       └─────────────┬─────────────┘
            YES      │       NO
       ┌─────────────┴─────────────┐
       ▼                           ▼
┌───────────────────────────┐┌───────────────────────────┐
│ Abort Remaining Steps &   ││ Log Warning & Continue    │
│ Return Failed Result      ││ to Next Step              │
└───────────────────────────┘└───────────────────────────┘
```

---

## 5. Audit Logging & Verification

Every workflow execution produces a permanent append-only record in `data/workflow_audit.jsonl`:
```json
{
  "workflow_id": "open_project_in_vscode",
  "entity_id": "project:astrarun",
  "success": true,
  "message": "Workflow 'Open Project in VS Code (astrarun)' completed successfully (1/1 steps)",
  "steps_attempted": 1,
  "steps_succeeded": 1,
  "steps_failed": 0,
  "step_results": [
    {
      "step_id": "launch_vscode",
      "name": "Launch VS Code",
      "tool": "open_project_in_vscode",
      "success": true,
      "message": "Opened project AstraRun in VS Code (Active/AstraRun)",
      "data": {"project_id": "astrarun", "path": "E:\\Workspace\\Active\\AstraRun"},
      "latency_ms": 2.14
    }
  ],
  "rollback_supported": false,
  "timestamp": 1790509120.45,
  "total_latency_ms": 2.38
}
```

### Automated Test Coverage
- `test_workflow_engine_execution`: Verifies successful multi-step execution and audit logging.
- `test_workflow_engine_partial_failure_stops_execution`: Verifies that step failure stops remaining steps and accurately records `success=False` without false success assertions.
