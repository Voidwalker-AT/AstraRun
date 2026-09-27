# WINDOW_BENCHMARK.md — Window Benchmark V1 Evaluation Report

> **Milestone**: AstraRun v0.9 (Daily Driver Integration & Window Intelligence)  
> **Status**: APPROVED & LOCKED  
> **Harness**: `benchmarks/windows/run_window_benchmark.py`  
> **Dataset**: `benchmarks/windows/window_benchmark_v1.json`  
> **Dataset SHA-256**: `4307223c89e6676788d264009566b235550374e4661631fdcae0c06266bfc3fe`  
> **Results Log**: `benchmarks/windows/window_benchmark_results.json`  
> **Audit Date**: 2026-09-27  

---

## 1. Benchmark Purpose & Scope

The Window Benchmark V1 establishes a rigorous, automated regression harness assessing all aspects of AstraRun's Window Intelligence subsystem. It evaluates 330 synthetic and real-world test cases covering natural language resolution, pronoun grounding, spatial multi-monitor layouts, geometry clamping, undo mechanics, and safety policy barriers.

---

## 2. Overall Benchmark Results

| Metric | Target Requirement | Measured Result | Status |
| :--- | :---: | :---: | :---: |
| **Total Test Cases** | $\ge 300$ | **330** | PASS |
| **Overall Accuracy** | $\ge 98.0\%$ | **100.0% (330 / 330)** | PASS |
| **Wrong Window Action Rate** | **0.00%** | **0.00%** | **PASS (PRIME INVARIANT)** |
| **Policy Violations** | 0 | **0** | PASS |
| **Ambiguity Failures** | 0 | **0** | PASS |
| **Mean Evaluation Latency** | $< 1.0\text{ ms}$ | **0.0229 ms** | PASS |
| **Dataset Hash Verification** | SHA-256 Match | **MATCHED** | PASS |

---

## 3. Category Breakdown (330 Cases)

| Category | Cases | Passed | Accuracy | Focus & Test Invariants |
| :--- | :---: | :---: | :---: | :--- |
| **`direct_resolution`** | 50 | 50 | 100.0% | Explicit window title and app name resolution (e.g., `"focus chrome"`, `"find notepad"`). |
| **`pronoun_origin`** | 50 | 50 | 100.0% | Origin window grounding on pronouns (`"this window"`, `"it"`, `"current window"`) and implicit actions (`"snap left"`). |
| **`context_recall`** | 30 | 30 | 100.0% | Anaphora recall targeting recently mentioned or inspected windows (`"that window"`). |
| **`ambiguity_gating`** | 40 | 40 | 100.0% | Multiple candidate windows trigger `WAITING_CLARIFICATION` without guessing. |
| **`monitor_resolution`** | 40 | 40 | 100.0% | Natural language monitor routing (`"move to monitor 2"`, `"second screen"`, `"main display"`). |
| **`tiling_layout`** | 40 | 40 | 100.0% | Mathematical geometry generation across all 11 tiling layout presets. |
| **`geometry_clamping`** | 25 | 25 | 100.0% | Clamping offscreen or oversized windows within visible work areas (min 300x200). |
| **`undo_stack`** | 25 | 25 | 100.0% | Bounded LIFO restoration, max depth pruning, and TTL expiration behavior. |
| **`safety_policy`** | 30 | 30 | 100.0% | Hard protection of `_ASTRARUN_HWNDS`, system tray, desktop shell, and invalid PIDs. |

---

## 4. Key Performance Indicators

- **Mean Execution Latency**: **0.0229 ms** per case.
- **Wrong Window Action Rate (WWAR)**: **0.00%**. Across all 330 cases, AstraRun never targeted the incorrect window handle or modified a window belonging to another application without explicit resolution.
- **Ambiguity Precision**: 100.0% of ambiguous queries were caught and converted into structured clarification proposals.
- **Safety Enforcement**: 100.0% of self-window targeting attempts and shell class modifications were rejected.
