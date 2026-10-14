# Hermes Experiential Memory & Autonomous Exploration Security Model

## 1. Security Invariants & Principles

Autonomous exploration introduces an active agent into an unfamiliar application environment. Without rigorous governance, exploration could lead to accidental file corruption, unexpected process spawns, unintended keystrokes sent to sensitive applications, or persistent memory poisoning.

To prevent this, the Hermes subsystem is governed by **five strict security invariants**:

### Invariant 1: No Raw Shell Execution
Never execute raw natural-language user input or model output via `shell=True`, `os.system()`, `eval()`, or `Invoke-Expression`.
All actions must pass through:
$$\text{Request} \rightarrow \text{Router} \rightarrow \text{Structured Decision} \rightarrow \text{ActionGate} \rightarrow \text{ExecutionBroker} \rightarrow \text{Executor}$$

### Invariant 2: ActionGate Authorization & Risk Ceilings During Exploration
When in `EXPLORE` mode:
1. **Permitted Action Tiers**:
   - `READ_ONLY` probes (inspect UIA element tree, enumerate controls, observe window state).
   - `BENIGN_MUTATION` probes (e.g. focus window, click known non-destructive button, press safe navigational shortcut like `Ctrl+Tab` or benign alphanumeric typing into an isolated scratch area).
2. **Forbidden Actions**:
   - Any destructive capability (`DELETE_FILE`, `TERMINATE_UNOWNED_PROCESS`, `OVERWRITE_FILE`).
   - Any external network call or privileged system setting modification.
   - Any action flagged with `ToolRisk.HIGH` or `ToolRisk.CRITICAL`.
3. If an exploration experiment attempts an unauthorized action, `ActionGate` rejects the proposal immediately with `EXPLORATION_RISK_EXCEEDED`.

### Invariant 3: Affirmative Task-Owned Resource Scoping & Cleanup
1. All applications launched during diagnostic exploration are explicitly registered in `AstraResourceLedger`.
2. Clean teardown is verified affirmatively by polling PID exit codes and HWND destruction.
3. Pre-existing processes and windows (not launched by AstraRun) are strictly non-closeable (`CRITICAL_OWNERSHIP_RULE`).

### Invariant 4: Epistemic Anti-Poisoning & Environment Binding
1. **Cryptographic Binding**: All Hermes entity knowledge is keyed by:
   - Application binary path
   - Executable SHA-256 hash
   - Machine environment hash (`env_hash`)
2. **Namespace Isolation**: Knowledge learned for Application A cannot be applied to Application B unless explicitly passed through a generic abstraction layer.
3. **Observation-Grounded Ingestion**: A model's verbal claim that an action "worked" is never accepted. An edge is written to Hermes **only** when `ComputerUseObservationFrame` and `AstraVerifier` affirmatively confirm the observed postcondition delta.

### Invariant 5: Safe Fallibility & Reversibility
1. Exploratory probes prioritize reversible actions (e.g., opening a menu and pressing `Escape`, opening a dialog and pressing `Cancel`).
2. If an exploration probe triggers an unexpected dialog (e.g. "Do you want to save changes?"), recovery rules prioritize safe cancellation over unverified dismissal.
3. User takeover (`TakeoverSentinel` / `TakeoverMonitor`) has absolute preemption authority: any human physical mouse or keyboard input immediately aborts exploration and freezes synthetic dispatch.
