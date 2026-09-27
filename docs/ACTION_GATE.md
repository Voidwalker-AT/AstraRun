# Action Gate Specification (AstraRun v0.6)

> **Status**: PRODUCTION READY  
> **Package**: `astrarun.policy.action_gate`  
> **Last Verified**: 2026-09-27  

---

## 1. Overview & Core Invariants

The **Action Gate** is the final, uncompromising safety arbiter in AstraRun's execution chain. It transforms a `ProposedAction` (derived from deterministic routing or neural shadow models and refined by entity resolution) into an explicit, typed `ActionGateResult`.

### The Prime Architectural Rule
$$\text{Natural Language} \longrightarrow \text{Semantic Decision} \longrightarrow \text{Verified Entity} \longrightarrow \text{Proposed Action} \longrightarrow \mathbf{ActionGate} \longrightarrow \text{Confirmation} \longrightarrow \text{Registered Tool} \longrightarrow \text{OS}$$

**Core Operating Invariants:**
1. **Zero Raw Shell Execution**: Natural language text or model outputs are NEVER passed directly to `cmd.exe`, PowerShell, or `subprocess.Popen(shell=True)`.
2. **False Execution Rate (FER) = 0.0%**: Out-of-scope, destructive, ambiguous, or unconfirmed actions must NEVER execute on the operating system.
3. **No Autonomous Execution Authority for Neural Models**: Neither Laya nor Kev nor external reasoning engines hold direct execution authority. High confidence alone is insufficient to trigger state-altering workstation mutations.
4. **TOCTOU Protection**: Every confirmation token targeting a running process cryptographically binds the target PID **and** its kernel creation timestamp (`create_time`). Revalidation immediately before execution aborts if the process has died or if the PID was recycled by the OS.

---

## 2. Decision Pipeline & Multi-Tier Safety Evaluation

```
                       ┌──────────────────────────────┐
                       │        ProposedAction        │
                       └──────────────┬───────────────┘
                                      │
                                      ▼
               ┌──────────────────────────────────────────────┐
               │    Tier 0: Global Hard Security Policy       │
               │    - Blocked command patterns (format, del)  │
               │    - Protected processes (lsass, csrss, ...) │
               │    - Privileged ports (<= 1023 termination)  │
               └──────────────┬───────────────────────────────┘
                     VIOLATED │                     │ PASSED
                              ▼                     ▼
                       ┌──────────────┐   ┌──────────────────────────────┐
                       │    BLOCK     │   │ Tier 1: Ambiguity & JSD Gating│
                       └──────────────┘   │ - Multiple candidates        │
                                          │ - Model disagreement (JSD)   │
                                          │ - Confidence < Threshold     │
                                          └──────────────┬───────────────┘
                                                AMBIGUOUS│       │ SAFE
                                                         ▼       ▼
                                                  ┌─────────────┐┌──────────────────────────────┐
                                                  │   CLARIFY   ││ Tier 2: Tool Registry Mapping │
                                                  └─────────────┘│ - Validate tool registration │
                                                                 │ - Validate typed arguments   │
                                                                 └──────────────┬───────────────┘
                                                                       VALID    │
                                                                                ▼
                                                                 ┌──────────────────────────────┐
                                                                 │ Tier 3: Risk & Confirmation  │
                                                                 │ - HIGH risk (terminate)      │
                                                                 │ - User-gated actions         │
                                                                 └──────────────┬───────────────┘
                                                                                │
                                                            HIGH RISK / CONFIRM │ LOW RISK / ALLOW
                                                                                ▼               ▼
                                                                        ┌──────────────┐┌──────────────┐
                                                                        │   CONFIRM    ││    ALLOW     │
                                                                        │(Crypto Token)││(Auto-Execute)│
                                                                        └──────────────┘└──────────────┘
```

---

## 3. Action Gate Outcomes (`ActionGateOutcome`)

| Outcome | Trigger Conditions | Pipeline Response | UI Behavior |
| :--- | :--- | :--- | :--- |
| **`ALLOW`** | Verified low-risk tool on production allowlist (`open_project`, `open_app`, `inspect_port`, `open_folder`, `open_url`). | Auto-executes via `ToolRegistry.execute_action()`. | Displays success notification / launches requested target. |
| **`CONFIRM`** | High-risk tools (`terminate_process`), power commands (`system:shutdown`), or actions configured for user confirmation. | Halts execution, generates 32-character crypto token. | Displays modal `ConfirmationCard`. Requires explicit user confirmation (Ctrl+Enter or click). |
| **`CLARIFY`** | Ambiguous entity matches ($\Delta \le 0.15$), ungrounded pronouns, unresolved targets, or model disagreement. | Halts execution, presents ranked disambiguation choices. | Displays modal `DisambiguationCard` with keyboard arrow navigation. |
| **`BLOCK`** | Hard policy patterns (`rmdir /s /q`, `format`, directory traversal `../`), protected processes (`csrss`, `lsass`), privileged ports $\le 1023$. | Rejects execution immediately, logs security incident. | Displays red error banner explaining prohibited policy reason. |

---

## 4. Cryptographic Confirmation Tokens & TOCTOU Defense

When an action requires user confirmation, the Action Gate generates an ephemeral token:
```python
ConfirmationToken(
    token="a9f24b81c20e481b93f185d207c430ab", # secrets.token_hex(16)
    tool="terminate_process",
    arguments={"pid": 14236, "expected_create_time": 1790508332.51, "expected_name": "node.exe"},
    entity_id="process:14236",
    pid=14236,
    expected_create_time=1790508332.51,
    created_at=1790508826.60,
    ttl_seconds=60.0
)
```

### Time-of-Check to Time-of-Use (TOCTOU) Revalidation
Before the registered tool executes any confirmed action, `ActionGate.revalidate_confirmation` performs a four-point verification:
1. **Token Validity**: Verifies the token exists in active memory and has not expired ($T_{\text{elapsed}} \le 60\text{ s}$).
2. **Argument Tampering Prevention**: Compares the passed arguments with the token's immutable stored arguments. Any altered parameter (e.g. attempting to change port from 3000 to 80) triggers immediate rejection.
3. **Process Existence & Creation Time Check**: If targeting a process PID, queries the OS kernel via `psutil.Process(pid).create_time()`. If `abs(current_ctime - expected_ctime) > 1.0\text{ s}`, the PID was recycled by the OS and execution is halted.
4. **Single-Use Consumption**: Upon successful validation, the token is atomically purged from memory, preventing replay attacks.

---

## 5. Benchmark Performance Metrics

Evaluated on the 330-query Action Benchmark V1:

| Metric | Measured Value | Standard / Invariant |
| :--- | :--- | :--- |
| **False Execution Rate (FER)** | **0.00%** | **0.0% (Zero Tolerance)** |
| **False Action Proposal Rate (FAPR)** | **0.00%** | **0.0%** |
| **Block Recall (Hard Security)** | **100.0%** (74/74) | **100.0%** |
| **Confirmation Recall (High-Risk)** | **100.0%** (31/31) | **100.0%** |
| **Clarification Precision** | **100.0%** (20/20) | **$\ge 95.0\%$** |
| **Gate Evaluation Accuracy** | **100.0%** (330/330) | **$\ge 98.0\%$** |
| **Mean Evaluation Latency** | **0.077 ms** | **$< 1.0\text{ ms}$** |
| **95th Percentile Latency ($p_{95}$)** | **0.187 ms** | **$< 2.0\text{ ms}$** |
