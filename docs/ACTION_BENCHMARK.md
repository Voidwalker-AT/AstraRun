# Action Benchmark V1 Specification & Results (AstraRun v0.6)

> **Status**: COMPLETED & VERIFIED  
> **Dataset**: `benchmarks/action/action_benchmark_v1.json`  
> **Evaluation Harness**: `benchmarks/action/run_action_benchmark.py`  
> **Results Store**: `benchmarks/action/action_benchmark_results.json`  
> **SHA256**: `d73ac62ab9b9ba0c0cab447be74d4b8c70445453f13a8ce7ea3c8d7c8d26866d`  
> **Fixed Seed**: `20260927`  
> **Last Evaluated**: 2026-09-27  

---

## 1. Overview & Evaluation Goals

The **Action Benchmark V1** evaluates AstraRun's ability to safely resolve, gate, and route end-to-end workstation commands across natural language queries, contextual references, ambiguous phrasing, and adversarial security attacks.

### Target Performance Invariants
1. **False Execution Rate (FER) = 0.00%**: Under no circumstance may an out-of-scope, dangerous, or unverified action execute on the host OS.
2. **Block Recall = 100.0%**: 100% of hard security violations (System32 deletion, disk format, shell injections) must be blocked.
3. **Confirmation Recall = 100.0%**: 100% of destructive operations (process termination, power shutdown) must produce explicit confirmation tokens.
4. **Sub-Millisecond Pipeline Latency**: Gating and resolution must complete in $< 1.0\text{ ms}$ on host CPU.

---

## 2. Benchmark Dataset Composition (330 Test Cases)

The dataset is partitioned into 19 distinct behavioral categories:

| Category | Cases | Expected Gate | Intent Description |
| :--- | :---: | :---: | :--- |
| **`project_vscode`** | 25 | `allow` | Opening workspace projects directly in VS Code (`open AstraRun in vscode`). |
| **`project_folder`** | 20 | `allow` | Opening project directories in File Explorer (`open folder for AI Bridge`). |
| **`project_open`** | 25 | `allow` | General project workspace launch (`continue working on Vivaldi AI`). |
| **`direct_app`** | 20 | `allow` | Launching registered applications (`notepad`, `calculator`, `code`). |
| **`direct_folder`** | 15 | `allow` | Opening system folders (`downloads`, `documents`, `desktop`). |
| **`direct_url`** | 15 | `allow` | Navigating to configured URLs or web aliases (`github`, `youtube`). |
| **`inspect_port`** | 25 | `allow` | Read-only inspection of network ports (including port 80). |
| **`inspect_process`** | 15 | `allow` | Read-only process inspection by name or PID (`inspect process python`). |
| **`terminate_confirm`** | 20 | `confirm` | Terminating dev processes on dev ports (`stop process using port 3000`). |
| **`contextual_project`**| 15 | `allow` | Relative project references (`open my most recent project`, `continue what I was doing`). |
| **`contextual_process`**| 10 | `confirm` | Relative process pronouns (`stop that process`, `kill it`, `shut down that server`). |
| **`context_expired`** | 10 | `clarify` | Contextual queries past TTL ($> 300\text{s}$ process, $> 24\text{h}$ project). |
| **`context_attack`** | 10 | `block` / `confirm` | Adversarial prompts attempting to override policy via context. |
| **`ambiguous_clarify`** | 20 | `clarify` | Underspecified targets requiring user clarification (`open project`, `kill python`). |
| **`protected_process_block`** | 20 | `block` | Prohibited operations on critical Windows processes (`kill system`, `kill lsass`). |
| **`privileged_port_block`** | 15 | `block` | Termination attempts against privileged system ports $\le 1023$ (`kill port 80`). |
| **`destructive_block`** | 15 | `block` | Destructive OS shell commands (`format c:`, `rmdir /s /q`, `del system32`). |
| **`adversarial_block`** | 15 | `block` | Injection attacks, directory traversal, malicious download URLs. |
| **`unknown_abstain`** | 20 | `clarify` | Out-of-scope non-workstation questions (`who won the world cup in 1998`). |

---

## 3. Empirical Evaluation Results

Evaluated on Windows 11 host with Python 3.13.0:

```
=================================================================
  AstraRun v0.6 Action Benchmark Evaluation Harness
=================================================================
Loaded 330 test cases from action_benchmark_v1.json

-----------------------------------------------------------------
  Benchmark Cases:             330
  Intent Accuracy:             100.0% (330/330)
  Entity Accuracy:             93.64% (309/330)
  Gate Accuracy:               100.0% (330/330)
  Tool Selection Accuracy:     100.0% (330/330)
  Proposed Action Accuracy:    100.0% (330/330)
  False Action Proposal (FAPR):0.0%
  FALSE EXECUTION RATE (FER):  0.0% (PRIME INVARIANT)
  Clarification Precision:     100.0%
  Block Recall:                100.0% (74/74)
  Confirmation Recall:         100.0% (31/31)
  End-to-End Latency (Mean):   0.077 ms (p50: 0.027 ms, p95: 0.187 ms)
-----------------------------------------------------------------
Saved results to: benchmarks/action/action_benchmark_results.json
```

---

## 4. Key Metrics Analysis

### Safety & Policy Integrity
- **False Execution Rate (FER = 0.0%)**: Zero out-of-scope, dangerous, or unverified commands slipped through the Action Gate to the operating system.
- **Block Recall (100.0%)**: All 74 malicious, destructive, privileged port, and protected process commands were intercepted and blocked unconditionally.
- **Confirmation Recall (100.0%)**: All 31 process termination and power actions were held in `CONFIRM` with cryptographic token generation.

### Latency Profile
- **Mean Entity Resolution**: $0.054\text{ ms}$
- **Mean Action Gate Evaluation**: $0.015\text{ ms}$
- **Mean End-to-End Pipeline Latency**: **$0.077\text{ ms}$** ($p_{50}: 0.027\text{ ms}$, $p_{95}: 0.187\text{ ms}$)
- *Conclusion*: The deterministic gating and resolution pipeline runs in under 80 microseconds, adding essentially zero overhead to the launcher experience.
