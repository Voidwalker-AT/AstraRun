# Kev Decision Model Architecture & Upstream Research

> **Document Status**: APPROVED SPECIFICATION  
> **Investigation Date**: 2026-09-27  
> **Target Framework**: `jaredpalmer/kev`  
> **Milestone**: AstraRun v0.4  

---

## 1. Upstream Identification & Provenance

- **Official Repository**: [`jaredpalmer/kev`](https://github.com/jaredpalmer/kev)
- **Author & Maintainer**: Jared Palmer
- **License**: **Apache-2.0** (Permissive open source)
- **Hugging Face Model Registry**: [`jaredpalmer`](https://huggingface.co/jaredpalmer) (Collection: `jaredpalmer/kev`)
- **API Standard**: Drop-in compatible with TypeSafe's `/v1/systemone` specification (`choice`, `score`, `noul`).

---

## 2. Architectural Analysis: Is Kev a "Qwen Version of Jev"?

### The "Jev" Heritage
TypeSafe's **Jev** established the paradigm of "System 1" non-autoregressive decision models: models that receive a document/state and a set of typed questions, producing calibrated probability distributions in a single forward pass without emitting conversational text tokens. However, Jev is a proprietary, closed-source cloud API.

### How Kev Works Under the Hood
Inspection of `kev/model.py`, `kev/checkpoint.py`, and `kev/api.py` confirms that Kev is a clean-room open-source reconstruction of this architecture built on top of Alibaba Cloud's **Qwen** foundation models:

1. **Backbone**:
   - Uses `Qwen3.5-Base` causal language model backbones (specifically `Qwen/Qwen3.5-0.8B-Base`, `Qwen/Qwen3.5-4B-Base`, `Qwen/Qwen3.5-9B-Base`, and `Qwen3.8-27B-Base`).
   - The base model weights remain frozen, adapted via a low-rank adapter (**LoRA**, rank $r=16$, $\alpha=32$).
   - The LM text generation head (`lm_head`) is discarded at inference. Kev **never generates text**.

2. **Special Delimiter Tokens**:
   - Reuses rarely-used Qwen FIM/box tokens as structural delimiters without retraining embedding matrices:
     - State prefix: `<|fim_prefix|>`
     - Question start: `<|fim_middle|>`
     - Option start: `<|box_start|>`
     - Option end: `<|box_end|>`
     - Decision readout anchor: `<|fim_suffix|>`

3. **Block-Causal Branch Masking (`branch_mask`)**:
   - Evaluates state and multiple question branches in a single forward pass.
   - Attention mask condition: Token $i$ attends to token $j$ if and only if $j \le i$ and (`seg[j] == 0` [state] or `seg[j] == seg[i]` [same question branch]).
   - Questions can read the input state and their own prompt/options, but cannot see or bleed information into other concurrent question branches.

4. **Pointer Readout Head (`PointerHead`)**:
   - A dedicated linear projection layer mapping hidden states ($d=1024$ for 0.8B, $d=2560$ for 4B) into a pointer projection space ($d_p=256$):
     $$\mathbf{q} = \mathbf{W}_q \mathbf{h}_{\text{decide}}, \quad \mathbf{k}_i = \mathbf{W}_k \mathbf{h}_{\text{opt}, i}$$
   - Readout logits are computed via scaled dot-product:
     $$z_i = \frac{\mathbf{k}_i^\top \mathbf{q}}{\sqrt{d_p} \cdot T}$$
     where $T$ is the fitted calibration temperature stored in `head.pt` (e.g. $T \approx 2.351$ for Kev-0.8B).
   - Softmax over $z_i$ produces the exact probability distribution across options.

---

## 3. Available Upstream Kev Variants

| Variant ID | Base Model | Backbone Type | Total Parameters | Disk Footprint | Expected FP32 Memory | Expected BF16 Memory | Workstation Suitability |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **`jaredpalmer/kev-0.8b`** | `Qwen/Qwen3.5-0.8B-Base` | Hybrid recurrent/attention | **0.8B** | **~1.7 GB** | **~3.2 GB** | **~1.6 GB** | **HIGH** (Fits CPU RAM & RTX 2050) |
| **`jaredpalmer/kev-4b`** | `Qwen/Qwen3.5-4B-Base` | Hybrid recurrent/attention | **4.0B** | **~8.5 GB** | **~16.0 GB** | **~8.0 GB** | **EXCEEDS VRAM** (Exceeds 4GB VRAM & 4.4GB free RAM) |
| **`jaredpalmer/kev-9b`** | `Qwen/Qwen3.5-9B-Base` | Dense attention | **9.0B** | **~18.0 GB** | **~36.0 GB** | **~18.0 GB** | **UNFEASIBLE** (Requires >= 24GB VRAM) |
| **`jaredpalmer/kev-27b`** | `Qwen3.8-27B-Base` | MoE (35B-A3B) | **27.0B** | **~54.0 GB** | **~108.0 GB** | **~54.0 GB** | **UNFEASIBLE** (Requires 80GB H100/H200) |

---

## 4. Upstream Claims vs. AstraRun Local Measurements

| Characteristic | Upstream Claim (`jaredpalmer/kev`) | AstraRun Local Reality / Measurement |
| :--- | :--- | :--- |
| **Primary Task** | Fast System 1 classification & routing | Evaluated on AstraRun 10-class workstation intent taxonomy |
| **Text Generation** | "No text generation" | **Verified**: Pointer head outputs softmax over delimiter tokens |
| **API Contract** | TypeSafe `/v1/systemone` | **Verified**: Implements identical `choice`, `score`, and `noul` shapes |
| **Inference Mode** | Single forward pass | **Verified**: One forward pass across encoded block-causal tokens |
| **Kev-0.8B Footprint** | ~1.7 GB disk, runs on laptops/CPU | **Verified**: Base model 1.63 GB + adapter 41 MB + head 2 MB |
| **Kev-4B Footprint** | Standard recommended checkpoint | **Unfeasible**: ~8.5 GB weights exceed our 4.43 GB free RAM & 2.6 GB free VRAM |
| **Calibration** | RLCD / Temperature scaling | Calibrated using temperature parameter ($T = 2.351$ on 0.8B) |
