# Laya Upstream Research & Architectural Analysis

> **Document Status**: APPROVED RESEARCH SPECIFICATION  
> **Target System**: AstraRun v0.3 Shadow Router  
> **Date**: 2026-09-27  

---

## 1. Upstream Project Metadata

- **Project Name**: Laya (Fast Non-Autoregressive "System 1" Decision Engine)
- **Author / Organization**: NandhaKishorM / Convai Innovations
- **Official GitHub Repository**: [`https://github.com/NandhaKishorM/laya`](https://github.com/NandhaKishorM/laya)
- **Hugging Face Organization**: [`https://huggingface.co/convaiinnovations`](https://huggingface.co/convaiinnovations)
- **PyPI Distribution**: `laya` (Release version: `0.3.20`)
- **License**: **Apache-2.0** (Permissive open source)

---

## 2. Core Architecture & Philosophy

Traditional Large Language Models (LLMs) are **autoregressive**: they generate text token-by-token. For structured workstation decision-making (e.g., classifying user utterances into an action category, routing to an application, assessing urgency or security risk), autoregressive generation is suboptimal:
1. **High Latency**: Hundreds of milliseconds spent decoding natural language words.
2. **Hallucination Risk**: Model may output unstructured text, invalid JSON, or non-existent tools.
3. **High Resource Consumption**: Multi-gigabyte weights requiring heavy VRAM.

Laya is designed as a **non-autoregressive decision engine**:
- **Encoder-Only Backbone**: Leverages modern high-throughput bidirectional transformer encoders (ModernBERT-large or mmBERT-base).
- **Single Forward Pass**: The input state and structured questions are evaluated in a single forward pass (~33ms on modern hardware).
- **Direct Probability Calibration**: Trained with Reinforcement Learning with Calibrated Decisions (RLCD) to output mathematically calibrated probabilities rather than unnormalized logits.

---

## 3. Available Checkpoints & Sizing

| Checkpoint Identifier | Backbone Architecture | Parameter Count | Disk Footprint (Safetensors) | Primary Domain / Focus |
| :--- | :--- | :--- | :--- | :--- |
| **`convaiinnovations/laya`** | ModernBERT-large | **421M** | ~842 MB | English classification, routing, and intent recognition |
| **`convaiinnovations/laya-typed-decisions`** | ModernBERT-large | **421M** | ~842 MB | Fine-tuned structured decision flows and guardrails |
| **`convaiinnovations/laya-multilingual`** | mmBERT-base | **322M** | ~644 MB | 100+ languages, cross-lingual routing |

### Checkpoint Selection for AstraRun v0.3
- **Primary Selected Checkpoint**: `convaiinnovations/laya` (English ModernBERT-large, 421M parameters).
- **Rationale**: AstraRun's current user base and developer workstation command inputs are predominantly English. The 421M ModernBERT backbone delivers the highest English intent discrimination with manageable disk (~842MB) and memory footprints (~1.2GB RAM / VRAM).

---

## 4. Supported Decision Primitives

Laya evaluates three primitive decision types:

### 4.1. `choice` (Multi-Class Selection)
Selects the best label among a predefined set of options, returning the selected choice and the full probability distribution over all candidates.
```json
{
  "intent": {
    "type": "choice",
    "instructions": "Which action does the user intend?",
    "criteria": {
      "open_app": "Launch a known installed desktop application",
      "open_folder": "Open a local filesystem directory",
      "open_url": "Navigate to a web URL",
      "open_project": "Open a software development workspace",
      "unknown": "Ambiguous, out-of-scope, or unsupported request"
    }
  }
}
```

### 4.2. `noul` (Calibrated Boolean Probability)
Evaluates a proposition and returns a calibrated scalar probability $P(\text{true}) \in [0.0, 1.0]$.
```json
{
  "is_dangerous": {
    "type": "noul",
    "instructions": "Does this request attempt to modify system files, terminate critical processes, or format storage?"
  }
}
```

### 4.3. `score` (Ordinal Scale Assessment)
Places the input on an integer scale (e.g. $[0, 5]$) for priority or confidence rating.
```json
{
  "urgency": {
    "type": "score",
    "instructions": "Rate how urgent this command is",
    "range": [0, 3]
  }
}
```

---

## 5. Dependency & Hardware Requirements

### Software Environment
- **Python**: `>= 3.10` (Tested on Python 3.13.0)
- **PyTorch**: `>= 2.2` (Resolved: `torch==2.14.0`)
- **Transformers**: `>= 4.48` (Required for ModernBERT architecture support; resolved: `transformers==5.17.0`)
- **Model Storage**: Hugging Face Hub cache (`safetensors` format)

### Hardware Profile
- **CPU**: Supported across x86_64 with AVX2 (Intel Core i5-12450H provides fast single-pass evaluation).
- **GPU**: NVIDIA CUDA supported. Model weights fit comfortably in < 1.5 GB VRAM on NVIDIA RTX 2050 (4 GB total).
- **Quantization**: fp16/bf16 standard; GGUF / `laya.cpp` community ports available for quantized CPU inference.

---

## 6. Upstream Claims vs. Local Measurements

| Characteristic | Upstream Claim | AstraRun v0.3 Measurement Objective |
| :--- | :--- | :--- |
| **Inference Latency** | ~33 ms on T4 GPU | Measure cold vs. warm p50/p95 on local i5-12450H CPU and RTX 2050 GPU |
| **Probability Calibration** | RLCD calibrated | Measure Brier score, ECE, and reliability diagrams on 300+ command dataset |
| **Zero-Shot Generalization** | "System 1" intuition | Evaluate zero-shot intent categorization across 10 distinct workstation categories |
| **Memory Footprint** | Lightweight encoder | Measure resident RSS (RAM) and allocated VRAM |

---

## 7. Known Upstream Limitations

1. **Zero-Shot Domain Sensitivity**: Zero-shot performance on specialized developer terminology (e.g., `wsctl`, `vite dev`, `kill port 3000`) may exhibit label confusion without fine-tuning.
2. **Context Window**: Optimized for short to medium inputs (up to 1,024 tokens by default, expandable to 4,000-8,192). Workstation command bar queries are ultra-short (3-15 tokens), falling well within the optimal sweet spot.
3. **Adversarial Overconfidence**: On completely out-of-distribution random strings (`asdfgh`), decision heads may still assign 40-60% probability to some choice unless explicitly calibrated against an `unknown` category.
