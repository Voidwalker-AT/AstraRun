# AstraRun v0.4 Status Report

> **Date**: 2026-09-27  
> **Status**: STABLE / VERIFIED  
> **Milestone**: v0.4 Complete (Kev Shadow Router & Laya-vs-Kev Decision Model Evaluation)  

---

## 1. What Works Completely

1. **Kev Neural Decision Router (`astrarun.routing.kev`)**:
   - Integrates `jaredpalmer/kev-0.8b` (PEFT LoRA adapter on `Qwen/Qwen3.5-0.8B-Base` backbone with 256-dim dot-product `PointerHead`).
   - Calibrated temperature scaling ($T \approx 2.351096$) loaded from `head.pt`.
   - Formatted single-pass sequence with Qwen FIM/box delimiters (`<|fim_prefix|>`, `<|fim_middle|>`, `<|box_start|>`, `<|box_end|>`, `<|fim_suffix|>`).
   - Deployed strictly in **Shadow Mode** (`"mode": "shadow"`).
   - **ZERO Production Execution Authority**: All user launches remain 100% deterministic and fuzzy. Kev predictions are never dispatched to OS APIs (0.0% False Execution Rate).
   - Model weights stored canonically in `E:\AI_Models\HF_CACHE` (Platform Rule 9).

2. **Laya Fast Decision Router (`astrarun.routing.laya`)**:
   - Integrates `convaiinnovations/laya` (421M parameter ModernBERT-large non-autoregressive decision model).
   - Deployed strictly in **Shadow Mode** with zero execution authority.
   - Runs on CPU via ONNX Runtime, achieving ~508ms mean latency and 0MB VRAM footprint.

3. **Curated Blind Holdout Evaluation Dataset (`benchmarks/routing/semantic_holdout_v2.json`)**:
   - 260 curated queries across 15 distinct categories (`direct_app`, `direct_folder`, `direct_url`, `semantic_app`, `semantic_project`, `semantic_file`, `semantic_process`, `semantic_system`, `semantic_ai`, `semantic_browser`, `ambiguous`, `underspecified`, `unsupported`, `dangerous`, `adversarial`).
   - 75 unknown queries (28.8% unknown rate) specifically testing model abstention.
   - Verified SHA256 checksum: `96b8cd6cfb78e5752261478fc5f75dbc93d072ea0483052307f82e01ba982743`.

4. **Multi-Model Shadow Event Telemetry (`astrarun.telemetry.shadow_collector`)**:
   - Parallel collectors: `LayaShadowEventCollector` (`data/laya_shadow_events.jsonl`) and `KevShadowEventCollector` (`data/kev_shadow_events.jsonl`).
   - Thread-safe background execution with zero UI thread blocking.
   - Defensive regex redaction strips API keys, Bearer tokens, query credentials, and passwords.

5. **Unified Comparative Benchmark Harness (`benchmarks/routing/run_comparative_benchmark.py`)**:
   - Evaluates Deterministic, Laya, Kev, and Cascades across both Dataset 1 (325 queries) and Dataset 2 (260 queries).
   - Computes Expected Calibration Error (ECE), Brier score, reliability bins, automation trade-off curves, and latency percentiles.

6. **Deterministic Foundation Preservation (v0.2 Regression)**:
   - 88-query deterministic routing benchmark remains at **100.0% accuracy** and **0.0% false execution rate**.
   - 395 applications and known folders discoverable in <3.5ms.

7. **Automated Test Suite**:
   - **61 automated unit, UI, and safety tests passing** across 13 test modules.
   - 9 dedicated Kev tests in `tests/test_kev_router.py` verifying shadow isolation, formatting, confidence normalization, and zero execution authority.

---

## 2. Key Empirical Findings (Laya vs. Kev)

1. **CPU Latency Disparity (The Linear Attention Bottleneck)**:
   - **Laya**: ~508 ms on CPU using ONNX Runtime.
   - **Kev-0.8B**: 15,000 - 23,000 ms (~18s) on CPU because Qwen3.5's Gated DeltaNet linear attention falls back to PyTorch interpreter loops in the absence of `flash-linear-attention` / `causal_conv1d` kernels on Windows.
   - **Advantage**: Laya exhibits a **~35x latency advantage** on host hardware.

2. **Memory Footprint**:
   - **Laya**: ~850 MB RAM footprint.
   - **Kev-0.8B**: ~3.2 GB RAM footprint in FP32 on CPU.
   - **Kev-4B**: Formally rejected in ADR-017 due to 8–16 GB memory requirements causing swap thrashing on 16 GB workstation.

3. **Domain Specialization & Abstention**:
   - As upstream creator Jared Palmer documented, Kev was trained on CFPB consumer finance complaint narratives and synthetic logic tasks, not desktop launcher tool-calls.
   - Kev's calibrated temperature ($T=2.35$) causes heavy abstention on direct application queries (e.g. `open notepad` $\rightarrow$ `unknown`), while accurately categorizing URL and process actions.
   - Laya achieves higher intent recall across launcher categories.

4. **Recommendation**:
   - **Laya remains the superior foundation for AstraRun workstation routing** on this hardware platform. Kev is deferred from interactive production routing.

---

## 3. What Does Not Work (By Design in v0.4)

- **Production Execution for Laya or Kev**: Both models operate under **ZERO execution authority** in v0.4. Production execution remains 100% deterministic/fuzzy.
- **Model Fine-Tuning**: Neither model is fine-tuned in v0.4; this milestone establishes a pure zero-shot baseline comparison.
- **Kev on Interactive Keystroke Paths**: Excluded due to ~18s CPU latency.

---

## 4. Next Recommended Step

**Milestone v0.5: Semantic Entity Resolution & Gated Production Router**:
- Domain fine-tuning of Laya on accumulated `data/laya_shadow_events.jsonl` to eliminate false-action risk.
- Entity resolution engine: binding semantic intents to concrete targets (e.g., resolving `open_project(vivaldi-ai)` to its workspace directory or `process_action(port 3000)` to its PID).
- Gated production promotion: allow Laya decisions with confidence $\ge 0.85$ to execute once parameters are verified.
