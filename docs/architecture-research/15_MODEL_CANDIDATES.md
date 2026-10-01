# 15 — Local Model Candidate Survey (0.5B to 4B Class)

> **Status**: APPROVED RESEARCH ARTIFACT  
> **Phase**: 7 — Model Research & Feasibility  
> **Focus**: Small Foundation Models, Tool-Calling Specialization, Quantization Footprints, and Hardware Viability  
> **Target System**: Local Windows 11 Workstation (RTX 2050 4GB, ~3.30 GB Free RAM, ~3.43 GB Free VRAM)  

---

## 1. Executive Summary & Hardware Feasibility Envelope

The local hardware constraints establish a strict upper bound on viable model architectures:
- **Maximum VRAM Budget**: $\le 2.80\,\text{GB}$ (leaving $\ge 600\,\text{MB}$ for Windows DWM and GPU buffer headroom).
- **Maximum Host RAM Budget**: $\le 1.50\,\text{GB}$ if running on CPU (leaving $\ge 1.80\,\text{GB}$ for active user applications).
- **Hard Upper Parameter Limit**: $\le 4.0\text{B}$ parameters in 4-bit quantization ($\approx 2.4\,\text{GB}$ weights). 7B models ($\approx 4.4\,\text{GB}$ in Q4) **exceed physical VRAM** and spill into system RAM, triggering devastating memory thrashing.

| Model Candidate | Parameters | Q4_K_M Weight Size `[ESTIMATED]` | Q8_0 Weight Size `[ESTIMATED]` | Native Tool Calling? | GGUF / llama.cpp Support | Architectural Role Suitability |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Qwen2.5-Coder-1.5B-Instruct** | 1.54B | **~1.02 GB** | ~1.65 GB | **Yes (Hermes/Qwen)** | **Universal (Mainline)** | **Tier 1 Candidate** (Fast Workhorse) `[TARGET]` |
| **Qwen2.5-Coder-3B-Instruct** | 3.09B | **~1.95 GB** | ~3.30 GB | **Yes (Hermes/Qwen)** | **Universal (Mainline)** | **Tier 1 Candidate** (High-Reasoning Planner) `[TARGET]` |
| **Spark-X2.5-1.7B** | 1.70B | **~1.15 GB** | ~1.85 GB | **Yes (FC Fine-tuned)** | **Requires Patch/Branch** | **Tier 1 Candidate** (Hybrid Attention) `[HYPOTHESIS]` |
| **Spark-X2.5-4B** | 4.10B | **~2.45 GB** | ~4.30 GB | **Yes (FC Fine-tuned)** | **Requires Patch/Branch** | **Tier 2 Candidate** (Near VRAM Ceiling) `[HYPOTHESIS]` |
| **SmolLM2-1.7B-Instruct** | 1.71B | ~1.08 GB | ~1.78 GB | Basic | Universal (Mainline) | Secondary Fallback |
| **Gemma-2-2B-IT** | 2.61B | ~1.70 GB | ~2.80 GB | Basic | Universal (Mainline) | Sliding window KV overhead |
| **LFM-1.3B (Liquid)** | 1.30B | ~850 MB | ~1.40 GB | No (Early Stage) | Experimental | Niche / Unstable tool calling |
| **BitNet b1.58 2B (Ternary)** | 2.00B | ~400 MB (1.58-bit) | N/A | No | Specialized fork | High CPU efficiency, low tool fidelity |

---

## 2. In-Depth Candidate Evaluations

### 2.1 Qwen2.5-Coder-1.5B & 3B-Instruct (Alibaba Cloud)
- **Architecture**: Standard Transformer with RoPE, GQA (Grouped Query Attention), 32k native context (expandable to 128k with YaRN).
- **Tool Calling Capabilities**: Trained explicitly on massive tool-use datasets; supports standard JSON schema and Hermes-style XML tool blocks with zero prompting acrobatics.
- **Coder Specialization**: Exceptional syntax accuracy for Python, Bash/PowerShell, JSON, and regex generation.
- **Hardware Profile (1.5B Q4_K_M)**:
  - Weight size: 1.02 GB.
  - Context buffer (8k tokens, Q8 KV): ~280 MB.
  - Total VRAM usage: **~1.45 GB** (easily fits in 3.4 GB free VRAM with 2.0 GB headroom).
  - Generation speed: **~65–85 tokens/sec** on RTX 2050 `[ESTIMATED]`.
- **Hardware Profile (3B Q4_K_M)**:
  - Weight size: 1.95 GB.
  - Context buffer (8k tokens, Q8 KV): ~450 MB.
  - Total VRAM usage: **~2.60 GB** (fits within the 2.8 GB safe VRAM ceiling).
  - Generation speed: **~35–50 tokens/sec** on RTX 2050 `[ESTIMATED]`.

### 2.2 Spark-X2.5-1.7B & 4B (iFLYTEK / XHToken)
- **Architecture**: Hybrid Attention (1 Global Attention layer per 3 Sliding Window Attention layers).
- **Core Value Proposition**: Drastically lowers KV cache footprint during long-context execution (up to 1M tokens), making deep observation histories viable without linear VRAM expansion.
- **Consideration**: Requires custom llama.cpp branch or specialized loader support; not fully merged into mainline upstream llama.cpp master branch at audit time `[UPSTREAM_PRIMARY_SOURCE]`.

### 2.3 Gemma-2-2B-IT (Google)
- **Architecture**: 2.61B effective parameters with interleaved local sliding window (4096) and global attention (8192).
- **Limitation**: While reasoning is strong, Gemma-2 has severe logit-capping behavior that can cause repetition loops in low-bit quantizations (Q4), and requires specialized GGUF un-capping flags in llama.cpp.

### 2.4 BitNet b1.58 & Liquid Foundation Models (LFM)
- **BitNet b1.58**: Ternary weights (-1, 0, 1) promise $10\times$ CPU inference energy savings. However, open-weights releases lack mature tool-calling fine-tunes and robust Windows inference runtimes.
- **LFM-1.3B**: State-space / Conv / Attention hybrid. Extremely high throughput, but lacks structured function calling support and reliable JSON schema constraint compliance.

---

## 3. Quantization vs. Schema Compliance Tradeoff

Empirical LLM evaluation demonstrates that aggressive quantization (e.g., Q2_K, Q3_K_S) severely degrades **JSON grammar adherence** and **tool parameter formatting** long before natural language coherence degrades.

| Quantization Type | Bits / Weight | Weight Size (1.5B) | Syntax / Schema Integrity | Recommendation for AstraRun | Evidence Tag |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FP16** | 16.0 | `CALCULATED` (~3.10 GB) | Baseline reference | Prohibited (VRAM ceiling exceeded) | `TARGET` |
| **Q8_0** | 8.5 | `CALCULATED` (~1.65 GB) | `NOT_MEASURED` (High expected fidelity) | Benchmark control baseline | `TARGET` |
| **Q5_K_M** | 5.5 | `CALCULATED` (~1.18 GB) | `NOT_MEASURED` (Target balance) | Candidate production target | `HYPOTHESIS` |
| **Q4_K_M** | 4.5 | `CALCULATED` (~1.02 GB) | `NOT_MEASURED` (Subject to Lab B) | Candidate high-speed target | `HYPOTHESIS` |
| **Q3_K_M** | 3.5 | `CALCULATED` (~0.85 GB) | `NOT_MEASURED` (Risk of syntax errors) | Falsification test target | `HYPOTHESIS` |
| **Q2_K** | 2.5 | `CALCULATED` (~0.65 GB) | `NOT_MEASURED` (Severe degradation expected) | Falsification test target | `HYPOTHESIS` |

---

## 4. Synthesis & Architectural Invariants

1. **Top Candidate for Fast-Path Engine**: `Qwen2.5-Coder-1.5B-Instruct` (in Q5_K_M or Q4_K_M) represents the lowest-risk, highest-velocity engine available, supported universally by llama.cpp.
2. **Top Candidate for Deep-Reasoning Local Engine**: `Qwen2.5-Coder-3B-Instruct` or `Spark-X2.5-1.7B` pending empirical benchmark verification.
3. **Strict Ban on Local 7B Resident Models**: Models $> 4\text{B}$ are banned from primary resident execution on the RTX 2050 to prevent swap thrashing.
4. **Quantization Baseline**: Standardize on **Q4_K_M minimum** and **Q5_K_M / Q8_0 preferred** for 1.5B models to safeguard structured JSON tool calling.
