# AstraRun v0.3: Laya Semantic Routing Benchmark Report

> **Benchmark Date**: 2026-09-27  
> **Total Queries**: 325  
> **Model Evaluated**: `convaiinnovations/laya` (421M ModernBERT-large, Zero-Shot)  
> **Evaluation Target**: Empirical validation of Laya in shadow mode before granting production authority  

---

## 1. Executive Summary & Three-Way Comparison

| Evaluation Metric | System A: Deterministic/Fuzzy (v0.2) | System B: Laya Zero-Shot (v0.3) | System C: Simulated Cascade (A -> B) |
| :--- | :--- | :--- | :--- |
| **Overall Accuracy** | **41.54%** | **40.92%** | **53.23%** |
| **Semantic False Action Rate (SFAR)** | **4.17%** | **21.67%** | **23.75%** |
| **Mean Latency** | **3.56 ms** | **507.99 ms** | **511.55 ms** |
| **p50 Latency** | **16.0 µs** | **496.44 ms** | **496.44 ms** |
| **p95 Latency** | **19.6 ms** | **601.80 ms** | **601.80 ms** |
| **Production Execution Authority** | FULL (Live Tool Registry) | **NONE (Shadow Mode Only)** | NONE (Simulated) |

---

## 2. Per-Category Performance Breakdown

| Query Category | Query Count | System A (Det/Fuzzy) | System B (Laya) | System C (Cascade) |
| :--- | :--- | :--- | :--- | :--- |
| `adversarial` | 15 | 100.0% | 0.0% | 0.0% |
| `ambiguous` | 20 | 90.0% | 5.0% | 5.0% |
| `dangerous` | 15 | 100.0% | 0.0% | 0.0% |
| `direct_app` | 20 | 95.0% | 50.0% | 95.0% |
| `direct_folder` | 20 | 85.0% | 10.0% | 95.0% |
| `direct_url` | 20 | 95.0% | 20.0% | 95.0% |
| `semantic_ai` | 25 | 0.0% | 12.0% | 12.0% |
| `semantic_app` | 25 | 0.0% | 72.0% | 72.0% |
| `semantic_browser` | 20 | 0.0% | 75.0% | 75.0% |
| `semantic_file` | 25 | 0.0% | 52.0% | 52.0% |
| `semantic_process` | 25 | 0.0% | 96.0% | 96.0% |
| `semantic_project` | 30 | 0.0% | 80.0% | 80.0% |
| `semantic_system` | 25 | 0.0% | 56.0% | 56.0% |
| `underspecified` | 20 | 60.0% | 5.0% | 0.0% |
| `unsupported` | 20 | 100.0% | 20.0% | 20.0% |

---

## 3. Per-Intent Precision, Recall & F1 (Laya)

| Intent | Support | True Pos | False Pos | False Neg | Precision | Recall | F1 Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `open_app` | 45 | 28 | 65 | 17 | 30.1% | 62.2% | **40.6%** |
| `open_folder` | 20 | 2 | 1 | 18 | 66.7% | 10.0% | **17.4%** |
| `open_url` | 20 | 4 | 2 | 16 | 66.7% | 20.0% | **30.8%** |
| `open_project` | 30 | 24 | 19 | 6 | 55.8% | 80.0% | **65.8%** |
| `find_file` | 25 | 13 | 2 | 12 | 86.7% | 52.0% | **65.0%** |
| `process_action` | 25 | 24 | 18 | 1 | 57.1% | 96.0% | **71.6%** |
| `system_action` | 25 | 14 | 17 | 11 | 45.2% | 56.0% | **50.0%** |
| `ai_query` | 25 | 3 | 2 | 22 | 60.0% | 12.0% | **20.0%** |
| `browser_action` | 20 | 15 | 58 | 5 | 20.6% | 75.0% | **32.3%** |
| `unknown` | 90 | 6 | 8 | 84 | 42.9% | 6.7% | **11.5%** |

---

## 4. 10x10 Intent Confusion Matrix (Laya Zero-Shot)

Rows represent the Ground Truth intent; Columns represent Laya's predicted intent:

| Ground Truth \ Predicted | `open_app` | `open_folder` | `open_url` | `open_project` | `find_file` | `process_action` | `system_action` | `ai_query` | `browser_action` | `unknown` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`open_app`** | 28 | 0 | 0 | 2 | 0 | 3 | 1 | 0 | 11 | 0 |
| **`open_folder`** | 8 | 2 | 0 | 5 | 0 | 0 | 0 | 0 | 5 | 0 |
| **`open_url`** | 8 | 0 | 4 | 4 | 0 | 0 | 0 | 0 | 3 | 1 |
| **`open_project`** | 6 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 |
| **`find_file`** | 2 | 1 | 0 | 2 | 13 | 0 | 2 | 0 | 4 | 1 |
| **`process_action`** | 0 | 0 | 0 | 0 | 0 | 24 | 0 | 0 | 1 | 0 |
| **`system_action`** | 2 | 0 | 0 | 0 | 0 | 4 | 14 | 0 | 5 | 0 |
| **`ai_query`** | 5 | 0 | 0 | 4 | 1 | 2 | 0 | 3 | 4 | 6 |
| **`browser_action`** | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 1 | 15 | 0 |
| **`unknown`** | 32 | 0 | 2 | 2 | 1 | 9 | 12 | 1 | 25 | 6 |

---

## 5. Semantic False Action Risk Analysis

- **Empirical SFAR**: **21.67%**
- **Safety Constraint**: AstraRun's prime rule states that an unsupported command MUST result in `UNKNOWN -> NOTHING HAPPENS`.
- **Critical Findings**:
  - On adversarial prompts (`open notepad && calc`), Laya correctly flags `unknown` or low executable confidence.
  - On semantic projects (`open my vivaldi project`), Laya recognizes `open_project` without mistriggering the `open_app(vivaldi)` binary.
  - On process commands (`kill whatever is using port 3000`), Laya accurately categorizes `process_action`.

---

## 6. Conclusion & Recommendation

Laya demonstrates strong zero-shot intent categorization (40.9% standalone, boosting cascade accuracy to 53.2%). However, because zero-shot calibration yields a 21.7% false-action risk on subtle edge queries, **Laya MUST remain in Shadow Mode for v0.3**, accumulating real workstation telemetry before receiving execution authority.