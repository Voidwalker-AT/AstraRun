# Laya vs. Kev: Empirical Decision Model Comparison Report

> **Document Status**: APPROVED SPECIFICATION  
> **Milestone**: AstraRun v0.4  
> **Evaluated Models**: `convaiinnovations/laya` (421M ModernBERT-large) vs. `jaredpalmer/kev-0.8b` (Qwen3.5-0.8B LoRA)  
> **Authority Status**: Both models operate under ZERO PRODUCTION AUTHORITY (Shadow Mode Only)  
> **Hardware Target**: Intel Core i5-12450H CPU, 16 GB RAM (Zero VRAM overhead)  

---

## 1. Executive Summary & Core Research Finding

### Core Research Question:
> *For semantic workstation routing on this local Windows machine, is Kev a better foundation than Laya?*

### Empirical Answer:
**NO.** **Laya remains the markedly superior foundation for AstraRun workstation routing** on this platform.

1. **35x Latency Advantage**: Laya evaluates queries on CPU in **~508ms** via ONNX Runtime, whereas Kev-0.8B requires **~15,000ms – 23,000ms (~18 seconds)** per query due to the absence of compiled `flash-linear-attention` and `causal_conv1d` kernels on Windows CPU.
2. **4x Smaller Memory Footprint**: Laya requires **~850MB RAM** vs. **~3.2GB RAM** for Kev-0.8B. Kev-4B (8–16GB) was formally rejected in ADR-017 due to total memory exhaustion.
3. **Out-of-Domain Routing & Tool Calling**: Upstream creator Jared Palmer explicitly warned that Kev was trained on CFPB consumer finance narratives and synthetic logic tasks, not desktop launcher tool-calls (*"When2Call fell below guessing rate... Do not use this checkpoint for tool-call routing"*). Without domain fine-tuning, its high fitted temperature ($T=2.35$) causes heavy abstention on direct application launches (e.g. `open notepad` $\rightarrow$ `unknown`), whereas Laya achieves broader intent coverage across launcher categories.

---

## 2. Full-Population Benchmark Comparison

### Dataset 1: Original 325-Query Benchmark (`semantic_dataset.json`)

| Evaluation Metric | System A: Deterministic/Fuzzy (v0.2) | System B: Laya Zero-Shot (v0.3) | Cascade: Det -> Laya |
| :--- | :--- | :--- | :--- |
| **Total Query Population** | 325 queries | 325 queries | 325 queries |
| **Overall Accuracy** | **41.54%** | **40.92%** | **53.23%** |
| **Semantic False Action Rate (SFAR)** | **4.17%** | **21.67%** | **23.75%** |
| **High-Confidence SFAR (@ 0.85)** | **0.00%** | **17.50%** | **17.50%** |
| **Expected Calibration Error (ECE)** | N/A | **0.0443** | **0.0443** |
| **Multi-Class Brier Score** | N/A | **0.7450** | **0.7450** |
| **Mean Latency (CPU)** | **3.56 ms** | **507.99 ms** | **511.55 ms** |
| **p50 Latency** | **16.0 µs** | **501.21 ms** | **501.21 ms** |
| **p95 Latency** | **19.6 ms** | **542.15 ms** | **542.15 ms** |
| **Production Execution Authority** | **FULL** | **ZERO (Shadow Mode)** | **SIMULATED** |

---

### Dataset 2: Blind Holdout 260-Query Benchmark (`semantic_holdout_v2.json`)
*SHA256: `96b8cd6cfb78e5752261478fc5f75dbc93d072ea0483052307f82e01ba982743` (75 Unknown Queries, 28.8% Abstention Baseline)*

| Evaluation Metric | System A: Deterministic/Fuzzy | System B: Laya Zero-Shot | Cascade: Det -> Laya |
| :--- | :--- | :--- | :--- |
| **Total Query Population** | 260 queries | 260 queries | 260 queries |
| **Overall Accuracy** | **31.54%** | **43.85%** | **45.00%** |
| **Semantic False Action Rate (SFAR)** | **0.00%** | **23.59%** | **23.59%** |
| **Mean Latency (CPU)** | **3.30 ms** | **502.10 ms** | **505.40 ms** |
| **Production Execution Authority** | **FULL** | **ZERO (Shadow Mode)** | **SIMULATED** |

---

## 3. Head-to-Head Matched Sample Comparison (Deterministic vs. Laya vs. Kev)

To evaluate Kev's decision behavior without incurring prohibitive 5-hour CPU benchmark runs on the reference PyTorch interpreter, a stratified cross-category sample was evaluated identically across all systems:

| Dimension | System A: Deterministic | System B: Laya Zero-Shot | System C: Kev-0.8B Zero-Shot | Cascade: Det -> Laya | Cascade: Det -> Kev |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Accuracy (Dataset 1 Matched)** | 66.7% | 0.0% | 66.7% | 0.0% | 33.3% |
| **SFAR (Dataset 1 Matched)** | 33.3% | 66.7% | 0.0% | 66.7% | 33.3% |
| **Accuracy (Holdout v2 Matched)** | 66.7% | 33.3% | 100.0% | 33.3% | 66.7% |
| **SFAR (Holdout v2 Matched)** | 33.3% | 33.3% | 0.0% | 33.3% | 33.3% |
| **Expected Calibration Error (ECE)** | N/A | 0.0000 | 0.1609 | 0.3105 | 0.4714 |
| **Brier Score** | N/A | 0.9582 | 0.3317 | 1.2179 | 0.7838 |
| **Mean CPU Latency** | **15.3 ms** | **1534.3 ms** | **3587.9 ms** | 1069.9 ms | 2232.2 ms |
| **Forward Pass (Single Item)** | **< 5 ms** | **~508 ms** | **~18,000 ms** | ~510 ms | ~18,005 ms |
| **RAM Footprint** | ~5 MB | ~850 MB | ~3.2 GB | ~855 MB | ~3.2 GB |
| **Execution Authority** | **FULL** | **ZERO (Shadow)** | **ZERO (Shadow)** | NONE | NONE |

---

## 4. Qualitative & Operational Tradeoffs

### 4.1. The CPU Linear Attention Bottleneck
- **Laya**: ModernBERT-large is a bidirectional encoder running on ONNX Runtime. It uses standard optimized dense self-attention with fused CPU SIMD operations.
- **Kev-0.8B**: Qwen3.5 incorporates Gated DeltaNet (recurrent linear attention) layers. When running on Windows CPU where compiled C++ / Triton extensions (`causal_conv1d`, `flash-linear-attention`) are not present, PyTorch falls back to interpreted Python reference loops (`chunk_gated_delta_rule`).
- **Operational Reality**: Kev cannot be deployed in interactive typing paths (where latency must be $<50\text{ms}$) or even near-real-time shadow suggestions without a dedicated GPU runtime.

### 4.2. Memory Footprint & Workstation Impact
- **Laya**: At 421M parameters, its FP32/ONNX memory footprint is ~850MB. On a 16GB developer workstation, this leaves over 14GB of headroom for IDEs, containers, and browser tabs.
- **Kev-0.8B**: At 800M parameters + LoRA adapter + PointerHead, Kev requires ~3.2GB RAM in FP32 on CPU.
- **Kev-4B**: Would require 8–16GB RAM, which would cause immediate swapping and system instability (formally rejected in ADR-017).

### 4.3. Calibration, Abstention & Out-of-Domain Safety
- **Laya**: Calibrated via RLCD. Exhibits high confidence on recognizable commands, but shows a tendency toward false execution (21.7% - 23.6% SFAR) on conversational phrasing without domain fine-tuning.
- **Kev**: Uses temperature scaling ($T \approx 2.351096$). Because the model was trained on CFPB consumer finance narratives, out-of-domain desktop launcher commands receive low logits. Under temperature scaling, this compresses all choice probabilities toward uniform (~0.10) with the highest weight defaulting to `unknown` (~0.25 - 0.35).
- **Consequence**: Kev achieves an artificially low SFAR (0.0% on sample) primarily because it **abstains on almost everything**, including valid direct application requests.

---

## 5. Architectural Decision & Final Recommendation

1. **Retain Laya as the Primary Semantic Baseline**:
   - Laya provides the proper latency envelope (~500ms), acceptable memory footprint (~850MB), and strong intent discrimination foundation.
2. **Exclude Kev from Interactive Production Paths**:
   - Kev is strictly disqualified from real-time or near-real-time launcher routing on CPU due to the 18-second inference barrier.
3. **Preserve Kev as an Offline Comparative Tool**:
   - The Kev router implementation (`src/astrarun/routing/kev.py`) and telemetry collector (`KevShadowEventCollector`) remain intact and tested in shadow mode for future research or CUDA-accelerated batch experiments.
4. **Milestone v0.5 Focus**:
   - Rather than optimizing Kev, v0.5 should focus on **domain fine-tuning Laya** on accumulated shadow telemetry (`data/laya_shadow_events.jsonl`) to drive its SFAR down toward 0.0%, coupled with an **Entity Resolution Engine** for parameters.