# AstraRun WorkflowContext Specification

> **Module**: `astrarun.workflows.context`  
> **Milestone**: v0.10.2  
> **Status**: APPROVED  
> **Date**: 2026-09-28  

---

## 1. Motivation

In compound desktop interactions, subsequent steps frequently depend on entities produced or discovered by earlier steps. For example:
- In `open notepad and type pqr`, the typing step does not explicitly state which window or process should receive the keystrokes; the target is implicitly the window created by the launch step.
- In `open code and snap right`, the window snap operation requires the `HWND` of the VS Code instance just opened.

Without contextual state propagation, downstream steps fail with missing parameter errors (e.g. `No HWND provided`) or incorrectly target the wrong foreground window.

`WorkflowContext` provides deterministic, scoped state passing across sequential workflow steps.

---

## 2. Data Model

```python
@dataclass
class WorkflowContext:
    """Carries runtime execution context and entity state across workflow steps."""
    
    # Implicit entity state
    last_opened_application: Optional[str] = None
    last_opened_window: Optional[int] = None       # HWND
    last_resolved_ui_root: Optional[int] = None     # HWND
    last_ui_element: Optional[dict[str, Any]] = None
    
    # Step-by-step history
    step_outputs: dict[int, dict[str, Any]] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
```

---

## 3. Context Lifecycle & Binding Rules

### 3.1 Step Recording (`record_step_result`)
After each capability execution in `AstraApplication.handle_request()`:
1. If capability is `open_application` and `app` is present:
   - Sets `last_opened_application = result_data["app"]`
2. If capability is `wait_for_window` or returns `hwnd`:
   - Sets `last_opened_window = int(result_data["hwnd"])`
3. If capability is `resolve_editable_element`:
   - Sets `last_ui_element = result_data.get("element")`
   - Sets `last_resolved_ui_root = int(result_data.get("hwnd", 0))`

### 3.2 Argument Binding (`bind_arguments`)
Before invoking a capability handler, `WorkflowContext.bind_arguments()` inspects the raw arguments and fills missing targets:
- For `wait_for_window`:
  - If `app` is missing, injects `last_opened_application`.
- For `resolve_editable_element`:
  - If `hwnd` is missing, injects `last_opened_window`.
- For `type_text`:
  - If `hwnd` is missing, injects `last_opened_window`.
  - If `target_element` is missing and `last_ui_element` exists, injects `last_ui_element`.
- For window layout capabilities (`snap_window_left`, `snap_window_right`, `maximize_window`, `minimize_window`, `restore_window`, `focus_window`):
  - If `hwnd` is missing, injects `last_opened_window`.

---

## 4. Verification

`WorkflowContext` is covered by:
- Unit tests: `tests/test_v0102_compound_pipeline.py` (Steps 4, 5)
- Live acceptance suite: `scripts/run_v0102_live_acceptance.py` (Steps 8, 9)
- Compound benchmark suite: `benchmarks/v0102_compound_benchmark.py` (CMP-01 to CMP-24)
