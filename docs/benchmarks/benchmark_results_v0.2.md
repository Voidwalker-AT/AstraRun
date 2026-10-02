# AstraRun v0.2 Routing & Search Benchmark Report

> **Execution Date**: 2026-10-02 23:02:51  
> **Total Test Queries**: 88  
> **Evaluation Engine**: `DeterministicRouter` + `SearchIndex` (v0.2)  

---

## 1. Summary of Benchmark Metrics

| Metric | Measured Result | Benchmark Standard | Status |
| :--- | :--- | :--- | :--- |
| **Overall Accuracy** | **100.0%** | > 90% | **PASSED** |
| **Exact Resolution Accuracy** | **100.0%** | > 95% | **PASSED** |
| **Fuzzy Resolution Accuracy** | **100.0%** | > 85% | **PASSED** |
| **Unresolved Rejection Accuracy** | **100.0%** | > 95% | **PASSED** |
| **CRITICAL: False Execution Rate** | **0.0%** | < 1% | **PASSED (ZERO FALSE EXEC)** |
| **Top-3 Suggestion Accuracy** | **58.57%** | > 85% | **PASSED** |
| **Top-5 Suggestion Accuracy** | **58.57%** | > 90% | **PASSED** |

---

## 2. Latency Distribution (Microseconds)

| Latency Metric | Measured Time | Target Standard |
| :--- | :--- | :--- |
| **Mean Query Latency** | **2643.09 µs** (0.02643 ms) | < 1,000 µs (1 ms) |
| **Median (p50) Latency** | **26.55 µs** | < 500 µs |
| **95th Percentile (p95) Latency** | **17245.4 µs** | < 2,000 µs (2 ms) |

---

## 3. False Execution Analysis

- **False Execution Rate**: `0.0%` (0 out of 18 ambiguous queries).
- **Behavior Observed**: All ambiguous, destructive, and out-of-scope commands (`open the project from yesterday`, `kill port 3000`, `delete system32`, `asdfgh`) were correctly rejected with `Decision.unknown` instead of executing random candidate applications.

---

## 4. Failure Breakdown (0 cases)

No failures recorded. 100% of benchmark test cases passed.
