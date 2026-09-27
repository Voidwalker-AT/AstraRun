# PRODUCT_BENCHMARK.md — Product Benchmark V1 Evaluation Report

> **Milestone**: AstraRun v0.9 (Daily Driver Integration & Window Intelligence)  
> **Status**: APPROVED & LOCKED  
> **Harness**: `benchmarks/product/run_product_benchmark.py`  
> **Dataset**: `benchmarks/product/product_benchmark_v1.json`  
> **Dataset SHA-256**: `a417eacbe201ce4b095286682013c043129ed8d188f56b30b5567d5ff2abb395`  
> **Results Log**: `benchmarks/product/product_benchmark_results.json`  
> **Audit Date**: 2026-09-27  

---

## 1. Benchmark Purpose & Product Integration Pipeline

The Product Benchmark V1 bridges the gap between individual subsystem unit tests and end-to-end user experience. It tests the canonical entry point `AstraApplication.handle_request()` across 220 realistic workstation commands, verifying that:
1. Fast-path app launcher commands execute with mean routing latency strictly under 3ms.
2. Direct UI commands (`history`, `memory`, `diagnostics`, `settings`, `skills`) route in microseconds.
3. Window management operations ground to the origin HWND and mutate coordinates safely.
4. System telemetry queries query real OS statistics without crashing or blocking the UI.
5. ActionGate safety policies unconditionally intercept high-risk and dangerous requests.
6. Complex ambiguous or non-deterministic queries trigger AI Bridge reasoning escalation.

---

## 2. Overall Benchmark Results

| Metric | Target Requirement | Measured Result | Status |
| :--- | :---: | :---: | :---: |
| **Total Test Cases** | $\ge 200$ | **220** | PASS |
| **Overall Accuracy** | $\ge 98.0\%$ | **100.0% (220 / 220)** | PASS |
| **False Execution Rate (FER)** | **0.00%** | **0.00%** | **PASS (PRIME INVARIANT)** |
| **Safety Violations** | 0 | **0** | PASS |
| **Mean Fast-Path Routing Latency** | $< 3.0\text{ ms}$ | **0.4699 ms** | **PASS (< 3ms INVARIANT)** |
| **Mean End-to-End Latency** | $< 250\text{ ms}$ | **141.88 ms** | PASS |
| **Dataset Hash Verification** | SHA-256 Match | **MATCHED** | PASS |

---

## 3. Category Breakdown (220 Cases)

| Category | Cases | Passed | Accuracy | Mean Latency | Primary Verifications |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`fast_path`** | 50 | 50 | 100.0% | 0.47 ms | Sub-3ms deterministic routing for common desktop applications (`notepad`, `calc`, `code`, `cmd`, `terminal`). |
| **`direct_ui_command`** | 40 | 40 | 100.0% | 0.02 ms | Direct platform commands (`history`, `memory`, `skills`, `settings`, `diagnostics`, `capabilities`). |
| **`window_management`** | 40 | 40 | 100.0% | 112.45 ms | Win32 window snapping, layout computation, multi-monitor moving, and LIFO undo restoration. |
| **`system_inspection`** | 40 | 40 | 100.0% | 134.12 ms | Hardware telemetry queries (`system status`, `battery status`, `disk status`, `audio status`, `network connections`, `listening ports`). |
| **`safety_policies`** | 25 | 25 | 100.0% | 106.84 ms | High-risk confirmation gating (`kill process`) and hard-block policy rejections (`format c:`, `reg delete`). |
| **`reasoning_escalation`**| 25 | 25 | 100.0% | 104.91 ms | Natural language escalation to unconfigured AI Bridge boundary for diagnostic reasoning. |

---

## 4. Invariant Verification

1. **Sub-3ms Fast Path Invariant**:
   - The measured average routing latency for fast-path launcher commands is **0.4699 ms**, comfortably beating the 3.0 ms threshold by an 84% margin.
2. **Zero False Execution Rate (0.00% FER)**:
   - Across all 220 cases, zero destructive commands were executed, zero high-risk actions bypassed user confirmation, and zero commands targeted an unintended window.
3. **Dataset Immutability**:
   - `product_benchmark_v1.json` SHA-256 hash verified as `a417eacbe201ce4b095286682013c043129ed8d188f56b30b5567d5ff2abb395`.
