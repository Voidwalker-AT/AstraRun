# AstraRun Observable Task Events & Event Bus

## 1. Ground-Truth Observability Invariant
> [!IMPORTANT]
> **Rule #59 Invariant**:
> Task events represent ground-truth system occurrences.
> AstraRun strictly prohibits:
> - Fabricating "thinking", "reasoning", or "pondering" steps.
> - Emitting fake progress indicators or simulated delays.
> - Granting execution authority through event listeners. Events are strictly observation-only.

---

## 2. Event Taxonomy (31 Observable Event Types)

### Task Lifecycle Events
- `TASK_CREATED`: Initial task registration and allocation.
- `TASK_STARTED`: Transition to active processing.
- `TASK_COMPLETED`: Successful terminal completion.
- `TASK_FAILED`: Error termination with structured code.
- `TASK_BLOCKED`: Hard security interception.
- `TASK_CANCEL_REQUESTED`: Cooperative abort signal received.
- `TASK_CANCELLED`: Task cleanly stopped.
- `TASK_INTERRUPTED`: Post-crash startup recovery.

### NLP & Understanding Events
- `NLP_PARSE_STARTED`: Request tokenization and clause decomposition.
- `NLP_PARSE_COMPLETED`: Structured utterance compiled.
- `NLP_PARSE_FAILED`: Syntactic breakdown failure.

### Entity Resolution Events
- `ENTITY_RESOLUTION_STARTED`: Matching text references against workstation state.
- `ENTITY_RESOLVED`: Unambiguous entity target bound.
- `ENTITY_AMBIGUOUS`: Multiple candidates detected requiring user choice.

### Action Gate Events
- `ACTION_GATE_ALLOW`: Safe read-only or low-risk operation permitted.
- `ACTION_GATE_CONFIRM`: High-risk state change flagged for confirmation.
- `ACTION_GATE_CLARIFY`: Disambiguation dialog required.
- `ACTION_GATE_BLOCK`: Hard-prohibited operation intercepted.

### Capability Execution Events
- `CAPABILITY_STARTED`: OS capability dispatched with sanitized inputs.
- `CAPABILITY_COMPLETED`: OS capability finished successfully with timing.
- `CAPABILITY_FAILED`: Capability raised or returned error code.

### User Interaction Events
- `CONFIRMATION_REQUESTED`: Confirmation dialog rendered to user.
- `CONFIRMATION_ACCEPTED`: User approved action.
- `CONFIRMATION_REJECTED`: User cancelled action.
- `CLARIFICATION_REQUESTED`: Candidate selection rendered to user.
- `CLARIFICATION_RESOLVED`: User selected specific candidate.

### Workflow Orchestration Events
- `WORKFLOW_COMPILED`: Multi-action plan structured into dependency graph.
- `WORKFLOW_STARTED`: Step sequence processing began.
- `WORKFLOW_STEP_STARTED`: Discrete step started.
- `WORKFLOW_STEP_COMPLETED`: Discrete step completed.
- `WORKFLOW_STEP_FAILED`: Step failure recorded.
- `WORKFLOW_COMPLETED`: Final workflow execution summary.

### Forward-Looking Placeholders (v0.9+)
- `WINDOW_FOCUSED`: Native desktop window focus switched.
- `WINDOW_MOVED`: Window repositioned.
- `REASONING_REQUESTED`: Unconfigured System-2 escalation.

---

## 3. Event Bus Design (`TaskEventBus`)
- Thread-safe pub/sub broker with lock-protected subscriber lists.
- Supports global subscriptions (`bus.subscribe(callback)`) and task-scoped subscriptions (`bus.subscribe(callback, task_id="...")`).
- Callback exception safety: subscriber failures are isolated and logged without corrupting other listeners or runtime execution.
