# AstraRun Task Benchmark V1 Specification & Results

## 1. Benchmark Overview
AstraRun Task Benchmark V1 evaluates task lifecycles, state machine compliance, event emission ordering, SQLite persistence fidelity, and crash recovery.

- **Case Count**: 300 deterministic test cases
- **Dataset Path**: `benchmarks/tasks/task_benchmark_v1.json`
- **SHA-256 Hash**: `7979fb8dd6361aa6406f4ae318beae2901724c20671df68d34ad34c24378b4d4`
- **Evaluation Harness**: `benchmarks/tasks/run_task_benchmark.py`

---

## 2. Category Breakdown
| Category | Cases | Target Invariant |
|---|---|---|
| `single_capability_success` | 60 | Clean 7-event sequence, `COMPLETED` state |
| `multi_step_workflow` | 40 | Sequential step event ordering, `COMPLETED` state |
| `high_risk_confirmation_accepted` | 30 | `WAITING_CONFIRMATION` -> `RUNNING` -> `COMPLETED` |
| `high_risk_confirmation_rejected` | 20 | `WAITING_CONFIRMATION` -> `CANCELLED` |
| `hard_policy_blocked` | 40 | `ACTION_GATE_BLOCK` -> `BLOCKED` with policy code |
| `ambiguous_entity_clarification` | 30 | `WAITING_CLARIFICATION` -> `RUNNING` -> `COMPLETED` |
| `cooperative_cancellation` | 30 | `TASK_CANCEL_REQUESTED` -> `TASK_CANCELLED` |
| `partial_completion_failure` | 20 | Non-fatal step error -> `PARTIALLY_COMPLETED` |
| `crash_recovery_interrupted` | 20 | Dangling active task -> `INTERRUPTED` |
| `re_run_semantic_reevaluation` | 20 | Brand-new task, 0 stale arguments, `COMPLETED` |

---

## 3. Verified Benchmark Results
```
======================================================================
  AstraRun v0.8 Task Runtime & Lifecycle Benchmark Harness
======================================================================
Cases Loaded:    300
Dataset SHA256:  7979fb8dd6361aa6406f4ae318beae2901724c20671df68d34ad34c24378b4d4
----------------------------------------------------------------------
Status Accuracy:     100.0% (300/300)
Sequence Accuracy:   100.0% (300/300)
Persistence Acc:     100.0% (300/300)
Mean Latency:        64.636 ms (p50: 9.634 ms, p95: 256.514 ms)
----------------------------------------------------------------------
```
