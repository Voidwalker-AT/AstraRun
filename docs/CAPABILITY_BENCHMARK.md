# Capability Benchmark V1 Report — AstraRun v0.7

> **Scope**: Specification, methodology, and evaluation results for Capability Benchmark V1  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Evaluation Date**: 2026-09-27  

---

## 1. Benchmark Overview & Invariants

AstraRun v0.7 establishes **Capability Benchmark V1** (`benchmarks/capabilities/`), a standardized 520-case test suite designed to evaluate:
1. **Capability Selection & Dispatch**: Correct mapping of requests to registered capabilities and argument schemas.
2. **Permission Integrity**: Strict alignment of expected permissions (`AUTO`, `CONFIRM`, `BLOCK`).
3. **Safety Enforcement**: **100% Block Recall** on dangerous/unsupported actions and **100% Confirm Recall** on high-risk operations.
4. **Execution Latency**: Sub-millisecond execution across all workstation domains.

### Dataset Integrity:
- **File**: `benchmarks/capabilities/capability_benchmark_v1.json`
- **Case Count**: **520**
- **Dataset SHA256**: `32ca0f2946a55403d77e0e55b969aad81289aa5da9617ea1f8c8086e391d8fdc`

---

## 2. Evaluation Results Summary

Evaluation conducted via `benchmarks/capabilities/run_capability_benchmark.py`:

```text
======================================================================
  AstraRun v0.7 Workstation Capability Benchmark Harness
======================================================================
Cases Evaluated:      520
Dataset SHA256:       32ca0f2946a55403d77e0e55b969aad81289aa5da9617ea1f8c8086e391d8fdc
Capability Accuracy:  100.0%
Permission Accuracy:  100.0%
Block Recall:         100.0% (PRIME SAFETY)
Confirm Recall:       100.0% (HIGH RISK GATING)
Mean Latency:         0.590 ms (p50: 0.506 ms, p95: 1.035 ms)
======================================================================
```

---

## 3. Category Breakdown

| Category | Cases | Capability Accuracy | Permission Accuracy | Block Recall | Confirm Recall |
|---|---|---|---|---|---|
| `APPLICATION` | 75 | 100.0% | 100.0% | N/A | N/A |
| `FILE` | 80 | 100.0% | 100.0% | 100.0% | N/A |
| `PROCESS` | 85 | 100.0% | 100.0% | 100.0% | 100.0% |
| `NETWORK` | 50 | 100.0% | 100.0% | N/A | N/A |
| `SYSTEM` | 65 | 100.0% | 100.0% | 100.0% | N/A |
| `PROJECT` | 55 | 100.0% | 100.0% | N/A | N/A |
| `WINDOW` | 40 | 100.0% | 100.0% | N/A | N/A |
| `AUDIO` | 30 | 100.0% | 100.0% | N/A | N/A |
| `WORKFLOW` | 40 | 100.0% | 100.0% | 100.0% | N/A |
| **TOTAL** | **520** | **100.0%** | **100.0%** | **100.0%** | **100.0%** |

---

## 4. Key Verification Findings

1. **Perfect Safety Gating**: All blocked capabilities (`shutdown_system`, `restart_system`, `execute_shell`, `delete_system_path`, `open_executable_script`) were intercepted with 100.0% recall.
2. **Deterministic High-Risk Confirmation**: 100.0% of `terminate_process` calls correctly enforced `CONFIRM` permission requirements.
3. **Execution Robustness**: Every capability handler produced a valid, strongly-typed `CapabilityResult` envelope with zero uncaught exceptions.
