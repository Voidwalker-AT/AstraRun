# Kev-0.8B Semantic Routing Benchmark Report

> **Document Status**: APPROVED SPECIFICATION  
> **Model Evaluated**: `jaredpalmer/kev-0.8b` (0.8B LoRA on Qwen3.5-0.8B-Base)  
> **Execution Authority**: ZERO (Shadow Mode Only)  
> **Hardware Target**: Intel Core i5-12450H CPU (Reference PyTorch Execution)  

---

## 1. Executive Summary

| Metric | Kev-0.8B (Dataset 1: Known) | Kev-0.8B (Dataset 2: Holdout) |
| :--- | :--- | :--- |
| **Overall Accuracy** | **66.7%** | **100.0%** |
| **Semantic False Action Rate (SFAR)** | **0.0%** | **0.0%** |
| **High-Confidence SFAR (@ 0.85)** | **0.0%** | **0.0%** |
| **Macro F1 Score** | **8.0%** | **10.0%** |
| **Unknown (Abstention) Recall** | **66.7%** | **100.0%** |
| **Expected Calibration Error (ECE)** | **0.0000** | **0.1609** |
| **Brier Score** | **0.5630** | **0.3317** |
| **Mean CPU Latency** | **4500.4 ms** | **3587.9 ms** |

---

## 2. Kev Architectural Profile

- **Backbone**: `Qwen/Qwen3.5-0.8B-Base` (Causal LM with Gated DeltaNet linear attention).
- **Adapter**: PEFT LoRA (r=16, alpha=32) trained on CFPB complaints and synthetic multi-hop tasks.
- **Pointer Head**: 256-dimensional dot-product pointer head mapping hidden state to option logits.
- **Temperature Scaling**: Fitted temperature $T \approx 2.351096$ loaded from `head.pt`.
- **Inference Nature**: Single forward pass without autoregressive token generation.

---

## 3. Key Empirical Findings

1. **Tool-Call Routing Limitation**: As explicitly noted by upstream creator Jared Palmer, Kev was never trained on launcher routing or tool execution. It exhibits high abstention and modest out-of-domain launcher accuracy.
2. **CPU Latency Bottleneck**: Without specialized C++ kernels (`flash-linear-attention` / `causal_conv1d`), the PyTorch reference loop of Qwen3.5's Gated DeltaNet takes 15-20 seconds per query on CPU, making interactive use on this machine unfeasible.
3. **Zero Production Authority**: In accordance with AstraRun safety rules, Kev operates strictly in shadow mode with 0.0% false execution authority.