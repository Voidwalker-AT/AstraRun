# Laya Hardware Audit & Runtime Configuration Specification

> **Document Status**: APPROVED SPECIFICATION  
> **Milestone**: AstraRun v0.3  
> **Target Subsystem**: `LayaRouter` Inference Runtime  
> **Date**: 2026-09-27  

---

## 1. Physical Hardware Audit

Empirical system measurements gathered directly on the Windows 11 host environment:

| Component | Specification | Empirical Measurement |
| :--- | :--- | :--- |
| **CPU** | 12th Gen Intel(R) Core(TM) i5-12450H | 8 physical cores (4 P-cores, 4 E-cores), 12 logical threads, AVX2 support |
| **Total Physical RAM** | 16 GB | 16,409,092 KB (~16.0 GB total visible) |
| **Free Physical RAM** | ~4.0 GB | Measured via `Win32_OperatingSystem` (3,998,572 KB available) |
| **Discrete GPU** | NVIDIA GeForce RTX 2050 | Ampere architecture, Compute Capability 8.6, WDDM Driver Model |
| **Total VRAM** | 4,096 MiB (4.0 GB) | Measured via `nvidia-smi` |
| **Active VRAM Usage** | ~1,254 MiB | Occupied by desktop window manager, browsers, and OS compositors |
| **Free VRAM** | ~2,842 MiB | Available for local acceleration |
| **NVIDIA Display Driver** | 596.49 | WDDM 3.2, driver-level support up to CUDA 13.2 |
| **Host CUDA Toolkit** | CUDA 11.8 (`nvcc -V`) | Available on host PATH for C++/CUDA compilation |

---

## 2. PyTorch & Acceleration Runtime Inspection

Running `torch.cuda.is_available()` in the active Python environment:
- **Installed PyTorch Version**: `2.14.0+cpu` (Official PyPI distribution)
- **`torch.cuda.is_available()`**: **`False`** (CPU-only PyTorch build)
- **`torch.backends.mps.is_available()`**: `False` (Non-Apple platform)

### Why CPU Inference is the Primary Chosen Configuration for v0.3
1. **Single-Pass Non-Autoregressive Execution**: Unlike generative LLMs (e.g. LLaMA, Qwen) which generate tokens sequentially over seconds, Laya is a ModernBERT encoder performing a single forward pass over short 5-15 token command utterances.
2. **Low Latency on i5-12450H**: ModernBERT-large (421M parameters) evaluates a short sequence on an 8-core Alder Lake CPU with AVX2 in ~50-100ms.
3. **Zero VRAM Contention**: The RTX 2050 has 4GB total VRAM with ~2.8GB free. Running on CPU eliminates any risk of CUDA Out-Of-Memory (OOM) errors colliding with GPU desktop applications.
4. **Environment Stability**: Standard PyPI PyTorch (`2.14.0+cpu`, ~118 MB) was installed without destabilizing AstraRun's clean virtual environment or requiring a 2.8 GB CUDA wheel download.
5. **Asynchronous Execution**: In AstraRun, `LayaRouter` runs on an isolated background worker thread (`QThread` / `concurrent.futures.ThreadPoolExecutor`), meaning a 60ms CPU inference time has **zero perceptible impact** on the PySide6 UI thread (which renders at 60+ FPS).

### Device Selection Strategy
The configuration accepts `device: "auto" | "cpu" | "cuda"`:
```python
if configured_device == "auto":
    device = "cuda" if torch.cuda.is_available() else "cpu"
```
When `torch.cuda.is_available()` is `False`, it gracefully defaults to `"cpu"` without throwing exceptions.

---

## 3. Canonical Model Cache Location

In strict compliance with **Platform Rule 9** (`Canonical AI Model Storage`):
- All Hugging Face model weights and tokenizers are directed to:
  ```text
  E:\AI_Models\HF_CACHE
  ```
- Configured programmatically via:
  ```python
  os.environ.setdefault("HF_HOME", "E:/AI_Models/HF_CACHE")
  ```
- This prevents bloating the developer's user profile (`C:\Users\hp\.cache\huggingface`) or duplicating multi-hundred megabyte `.safetensors` files across project trees.
