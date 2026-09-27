# AstraRun v0.3 Status Report

> **Date**: 2026-09-27  
> **Status**: STABLE / VERIFIED  
> **Milestone**: v0.3 Complete (Laya Shadow Router & Semantic Decision Benchmark)  

---

## 1. What Works Completely

1. **Laya Neural Decision Router (`astrarun.routing.laya`)**:
   - Integrates `convaiinnovations/laya` (421M parameter ModernBERT-large non-autoregressive decision model).
   - Deployed strictly in **Shadow Mode** (`"mode": "shadow"`).
   - **ZERO Production Execution Authority**: All user launches remain 100% deterministic and fuzzy. Laya predictions are never dispatched to OS APIs.
   - Evaluates on CPU via `torch+cpu` on Intel Core i5-12450H, consuming 0MB VRAM and leaving RTX 2050 available for heavy developer workflows.
   - Weights stored canonically in `E:\AI_Models\HF_CACHE` (Platform Rule 9).

2. **Categorical Intent Taxonomy**:
   - 10 mutually exclusive, strictly defined intent classes (`open_app`, `open_folder`, `open_url`, `open_project`, `find_file`, `process_action`, `system_action`, `ai_query`, `browser_action`, `unknown`).
   - Clean execution authority separation: only primitive registered tools map to `is_executable_now=True`; complex intents map to `requires_resolution=True`.

3. **Local Shadow Event Telemetry (`astrarun.telemetry.shadow_collector`)**:
   - Pairs production deterministic decisions with concurrent Laya neural predictions in `data/laya_shadow_events.jsonl`.
   - Thread-safe background execution with zero UI thread blocking.
   - Defensive regex redaction strips API keys, Bearer tokens, query credentials, and passwords.

4. **Comprehensive 325-Query Semantic Benchmark Suite**:
   - 325 curated queries across 15 distinct categories (`direct_app`, `direct_folder`, `direct_url`, `semantic_app`, `semantic_project`, `semantic_file`, `semantic_process`, `semantic_system`, `semantic_ai`, `semantic_browser`, `ambiguous`, `underspecified`, `unsupported`, `dangerous`, `adversarial`).
   - Three-way evaluation comparing System A (Deterministic/Fuzzy), System B (Laya Zero-Shot), and System C (Simulated Cascade).
   - Computes Expected Calibration Error (ECE = 0.0443), Brier score (0.7450), 10x10 confusion matrix, per-intent F1 scores, automation trade-off curve, and microsecond latency percentiles.

5. **Deterministic Foundation Preservation (v0.2 Regression)**:
   - 88-query deterministic routing benchmark remains at **100.0% accuracy** and **0.0% false execution rate**.
   - 395 applications and known folders discoverable in <3.5ms.

6. **Automated Test Suite**:
   - **52 automated unit, UI, and safety tests passing** across 12 test modules.
   - 8 dedicated Laya router and shadow mode isolation tests in `tests/test_laya_router.py`.

---

## 2. What Partially Works

- **Zero-Shot Calibration on Long-Tail Queries**:
  - While Laya achieves strong classification on semantic processes (96% recall) and projects (80% recall), zero-shot performance on direct folder lookups and subtle ambiguous queries exhibits overconfidence in bins >0.80 (+17% to +23% gap).
  - Standing Semantic False Action Rate (SFAR) is 21.67%, justifying keeping Laya in shadow mode until domain fine-tuning.

---

## 3. What Does Not Work (By Design in v0.3)

- **Laya Production Execution**: Laya has **ZERO execution authority** in v0.3. Production execution is 100% deterministic/fuzzy.
- **Kev, Jev, Qwen, Ollama, Cloud LLMs**: Intentionally excluded in v0.3. The focus was empirically testing whether non-autoregressive decision inference alone justifies production inclusion.
- **Complex Multi-Step OS Actions**: Queries like `kill port 3000` or `open project from yesterday` are recognized semantically by Laya as `process_action` and `open_project`, but are safely blocked from immediate execution (`requires_resolution=True`).

---

## 4. Empirical Benchmark Highlights

| Metric | System A (Deterministic) | System B (Laya Zero-Shot) | System C (Cascade Sim) |
| :--- | :--- | :--- | :--- |
| **Accuracy (325 queries)** | **41.54%** | **40.92%** | **53.23%** |
| **Semantic False Action Rate** | **4.17%** | **21.67%** | **23.75%** |
| **Mean Latency** | **3.56 ms** | **507.99 ms** | **511.55 ms** |
| **Execution Authority** | FULL | **ZERO (Shadow)** | NONE |

---

## 5. Next Recommended Step

**Milestone v0.4: Semantic Entity Resolution & Gated Production Router**:
- Domain fine-tuning of Laya on accumulated `data/laya_shadow_events.jsonl` to eliminate the 21.7% false-action risk.
- Entity resolution engine: resolve semantic targets (e.g. `open_project` -> directory path, `process_action` -> PID).
- Gated production promotion: allow Laya decisions with confidence $\ge 0.85$ to execute once parameters are verified.


