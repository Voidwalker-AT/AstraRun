# AstraRun Cooperative Task Cancellation

## 1. Safety Principles
AstraRun strictly rejects abrupt thread termination (`thread.terminate()`, `os.kill(SIGKILL)`) as it leaves file descriptors open, network ports wedged, and SQLite transactions corrupted.
Instead, AstraRun implements **cooperative cancellation** governed by `CancellationToken` in `src/astrarun/tasks/cancellation.py`.

---

## 2. Cancellation Checkpoints
Workflows, capabilities, and loops periodically invoke:
```python
token.check_cancelled()
```
If cancellation has been requested by the user, this call immediately raises `TaskCancelledError(reason)`, triggering safe cleanup.

Key checkpoints in `TaskManager`:
1. **Pre-Dispatch Check**: Evaluated before calling `registry.execute()`. Prevents starting a capability if already cancelled.
2. **Post-Dispatch Check**: Evaluated immediately after a capability returns. Catches cancellations that occurred during capability execution.
3. **Workflow Step Loop**: Evaluated between each workflow step in `WorkflowEngine`.
4. **Interactive Waiting**: Cancellation can be triggered directly from confirmation or disambiguation modals.

---

## 3. Lifecycle Impact
When a task is cancelled:
1. `token.cancel(reason)` is called, setting `token.is_cancelled = True` and running registered callbacks.
2. `TaskManager` emits `TaskEventType.TASK_CANCEL_REQUESTED`.
3. Task transitions to `TaskStatus.CANCELLED`.
4. `TaskManager` emits `TaskEventType.TASK_CANCELLED`.
5. Final result is recorded with error code `"CANCELLED"`.
