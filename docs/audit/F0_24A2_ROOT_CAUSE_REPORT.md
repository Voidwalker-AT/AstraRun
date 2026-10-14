# F0-24A.2 — Root Cause Analysis & Production Architecture Report

**Phase**: F0-24A.2 (Generic Physical Computer-Use Execution Closure)  
**Evidence Class**: `SOURCE_INSPECTED` & `PHYSICALLY_OBSERVED`  
**Date**: 2026-10-10  

---

## 1. Executive Summary

AstraRun's physical desktop execution path was audited and stress-tested against four real Windows application scenarios:
1. **Case A**: Clean launch of document editor, text entry, application-mediated Save As to Desktop, artifact verification, and cleanup.
2. **Case B**: Repeat Case A with an existing instance of the editor already open.
3. **Case C**: Unrelated text editor (Notepad++), text entry, Save As to Desktop, verification, and cleanup.
4. **Case D**: Non-document application interaction (Calculator) verifying observable state transitions.

Each test failed in the unmodified baseline, and each failure was traced to systemic architectural flaws rather than application-specific quirks. All root causes have been categorized and mapped to the production call path.

---

## 2. Root Cause Classification Matrix

| Root Cause Class | Location | Mechanism | Physical Symptom |
|---|---|---|---|
| **TASK_ID_PROPAGATION_FAILURE** | `src/astrarun/capabilities/registry.py:212` | `CapabilityRegistry.execute()` filtered arguments against `cap.args_schema`. `open_application` did not declare `task_id` in schema, stripping it before calling `open_application()`. | Resource registered under `"default_task"` instead of task ID; task cleanup could not find the resource. |
| **RESOURCE_LIFECYCLE_LEAK** | `src/astrarun/applications/service.py:270` & `src/astrarun/agent/loop.py:246` | Because `task_id` was stripped, `cleanup_task_resources(task_id)` found 0 resources, reported `clean=True` (false cleanup report), and orphaned spawned processes (Notepad, Calculator). | PIDs 22180, 9668, 15224, 16856 remained running indefinitely in background. |
| **VERIFIER_STRATEGY_MISCONFIGURATION** | `src/astrarun/agent/planner.py:1244` & `src/astrarun/capabilities/schema.py:135` | `save_document_via_ui` defaulted to `VerifierStrategy.RETURN_CODE_ONLY`. The hardened F0-24A.1 oracle rejects `RETURN_CODE_ONLY` as non-probative for goal completion. | Step 3 failed verification with `RETURN_CODE_ONLY is insufficient for completion` even after file was successfully saved to disk with correct content. |
| **COM_MODULE_GENERATION_RACE** | `src/astrarun/interaction/service.py:729` & `src/astrarun/interaction/document.py:149` | Direct `from comtypes.gen import UIAutomationClient` without first ensuring `comtypes.client.GetModule("UIAutomationCore.dll")` was called in the Python process. | Fatal `ImportError: cannot import name 'UIAutomationClient' from 'comtypes.gen'`. |
| **ENTITY_RESOLUTION_FAILURE** | `src/astrarun/agent/planner.py:1157` | Regex patterns used `[a-zA-Z0-9_\-\.]` which dropped special characters like `+`. | `open notepad++` truncated to `notepad`, launching wrong application. |
| **APPLICATION_RESOLUTION_DEFICIENCY** | `src/astrarun/applications/service.py:253` | Fallback used `shutil.which()`, which misses standard installed software in `Program Files` when not in system PATH (e.g. Notepad++). | Applications not on system PATH failed to resolve or launched wrong app. |
| **FOCUS_OWNERSHIP_AMBIGUITY** | `src/astrarun/windows/resolver.py:254` | When pre-existing windows existed (Case B), resolver picked an arbitrary candidate rather than the task-owned window from the ledger. | Keystrokes dispatched to background or inactive window. |
| **EDITABLE_SURFACE_DISCOVERY_FAILURE** | `src/astrarun/interaction/service.py:751` | Only searched for `DocumentControlTypeId` and `EditControlTypeId`. Ignored Scintilla, custom Win32 controls, and focused control fallback. | Scintilla controls (Notepad++) failed to receive text via UIA ValuePattern. |
| **INPUT_STRATEGY_LADDER_BREAK** | `src/astrarun/interaction/service.py:767` | Relied exclusively on UIA ValuePattern for primary input; if ValuePattern failed or wasn't supported, fallback was unreliable. | Text not committed to document buffer. |
| **UWP_ASYNC_INITIALIZATION_RACE** | `src/astrarun/applications/service.py:261` | Launching modern UWP apps (e.g. Calculator) returns immediately before XAML visual tree is instantiated. | `No accessible UI elements found in window`. |

---

## 3. Detailed Causal Analysis

### 3.1 Task ID Propagation and Resource Leakage
In `AgentExecutionEngine._execute_step_with_closed_loop()`, the engine issues an `ActionProposal` with `task_id=task.task_id`. The broker forwards this to `CapabilityRegistry.execute(capability_id, args, task_id=task_id)`.
However, `CapabilityRegistry.execute` filtered incoming arguments with:
```python
if hasattr(cap, "args_schema") and isinstance(cap.args_schema, dict):
    filtered_args = {k: v for k, v in args.items() if k in cap.args_schema}
```
Because `open_application` had `args_schema={"app": str, "path": Optional[str]}`, `task_id` was dropped. Consequently:
```python
owned_res = ledger.identify_and_register_launched_resource(
    task_id=task_id or "default_task", ...
)
```
The resource was recorded as belonging to `"default_task"`.
When `task.task_id` reached completion or failure, the cleanup pass queried `AstraResourceLedger.cleanup_task_resources(task.task_id)`. Finding 0 entries for that ID, it reported `cleaned=0, remaining_active=0, clean=True`. The launched processes were left running, completely unmonitored.

### 3.2 Verifier Strategy Misconfiguration
Under F0-24A.1, `StepVerifier` and `GoalVerifier` enforce that `RETURN_CODE_ONLY` represents only `ACTION_SUCCEEDED`, not `POSTCONDITION_SATISFIED`.
However, `GoalPlanner` assigned `step.verifier_strategy` using:
```python
verifier = getattr(schema, "verifier_strategy", getattr(cap, "verifier_strategy", VerifierStrategy.RETURN_CODE_ONLY))
```
Capabilities registered without an explicit `verifier_strategy` defaulted to `RETURN_CODE_ONLY`. For `save_document_via_ui`, this meant that even when the file was written to disk and verified by `os.path.exists()`, the step verifier failed closed with:
```
RETURN_CODE_ONLY is insufficient for completion: success is dispatch-level only.
```
This directly prevented legitimate physical executions from completing.

### 3.3 COM Type Library Generation
`comtypes` generates Python wrapper modules on demand when `comtypes.client.GetModule()` is executed. In several files (`src/astrarun/interaction/service.py`, `src/astrarun/interaction/document.py`), developers wrote:
```python
from comtypes.gen import UIAutomationClient
```
If another component had not previously invoked `GetModule("UIAutomationCore.dll")`, this import resulted in an immediate `ImportError`. A centralized, thread-safe initializer is required.

### 3.4 Entity Resolution & Regex Constraints
In `GoalPlanner`, application names were extracted using regexes like:
```python
re.search(r"open\s+([a-zA-Z0-9_\-\.]+)", clause)
```
Characters such as `+` were excluded. Thus, `"open notepad++"` was parsed with target application `"notepad"`. The system then launched `notepad.exe` instead of `notepad++.exe`.

---

## 4. Required Generic Solutions

1. **Global Task ID & Resource Association**: Ensure `task_id` is universally propagated through `args_schema` and `CapabilityRegistry.execute()`. Any spawned process or window must be permanently tied to the owning `task_id`.
2. **Authoritative Verifier Strategy Alignment**: All state-mutating capabilities must declare appropriate postcondition verifier strategies (`FILE_NON_EMPTY`, `FILE_CONTAINS`, `WINDOW_READY`, `UI_ELEMENT_STATE`) in their schema and planner step generation.
3. **Resilient COM/UIA Engine**: Centralize UIA access in `src/astrarun/computer_use/ui/automation.py` with guaranteed `GetModule()` initialization.
4. **Generic Editable Surface Model**: Reason from UIA patterns (`ValuePattern`, `TextPattern`), control types (`Document`, `Edit`), Win32 control classes, and active focus, rather than application identity.
5. **Generic Input Strategy Ladder**: Implement the 5-rung ladder: UIA ValuePattern -> Focused Control + Clipboard -> Focused Control + Native Keystrokes.
6. **Universal Entity Resolution**: Support symbols like `+` in application and entity names, and leverage `AppDiscoveryCache` for robust executable path discovery.
7. **Affirmative Cleanup Enforcement**: Fail tasks if task-owned resources are not confirmed terminated upon cleanup.
