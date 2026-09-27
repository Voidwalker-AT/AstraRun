# Kev Hardware & Runtime Specification

> **Document Status**: APPROVED SPECIFICATION  
> **Hardware Target**: Local Engineering Workstation  
> **Milestone**: AstraRun v0.4  

---

## 1. Workstation Hardware Profile (Re-Measured 2026-09-27)

Measurements gathered directly via Win32 `GlobalMemoryStatusEx` and `nvidia-smi`:

| Hardware Subsystem | Measured Specification | Runtime Availability | Operational Implication for AstraRun |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 11 Pro 64-bit (build 26200) | Native host | Primary target platform |
| **CPU** | Intel Core i5-12450H (8 Cores, 12 Threads) | ~85% idle | Excellent multi-core CPU inference |
| **System RAM** | **15.65 GB Total** | **4.43 GB Available** (71% Load) | Workstation limit: models must stay $\le 3.5\text{ GB}$ to avoid OS paging |
| **Discrete GPU** | **NVIDIA GeForce RTX 2050** | Active | CUDA 12 / Driver 596.49 |
| **Total VRAM** | **4096 MiB (4.0 GB)** | — | Compact mobile workstation GPU |
| **Free VRAM** | **2676 MiB (~2.61 GB)** | Dynamic | **1287 MiB used by Windows DWM, display, browser** |
| **Storage Cache** | `E:\AI_Models\HF_CACHE` | Canonical platform location | Shared model weights storage (Platform Rule 9) |

---

## 2. Model Variant Feasibility Analysis

### 2.1. `jaredpalmer/kev-0.8b` (FEASIBLE)
- **Parameter Count**: 0.8 Billion parameters.
- **Disk Footprint**:
  - Base model (`Qwen/Qwen3.5-0.8B-Base`): 1,666.01 MB (~1.63 GB).
  - LoRA Adapter (`adapter_model.safetensors`): 41.33 MB.
  - Readout Head (`head.pt`): 2.01 MB.
  - **Total Disk Footprint**: **~1.71 GB**.
- **Memory Footprint**:
  - FP32 CPU: ~3.2 GB RAM (Comfortably fits inside 4.43 GB available system RAM).
  - FP16/BF16: ~1.6 GB (Fits inside 2.61 GB free VRAM or host RAM).
- **Workstation Impact**: Leaves Windows responsive, does not cause disk swapping, and preserves memory for PySide6 and developer tools.

### 2.2. `jaredpalmer/kev-4b` (UNFEASIBLE FOR THIS WORKSTATION)
- **Parameter Count**: 4.0 Billion parameters.
- **Disk Footprint**: Base model (~8.0 GB) + adapter (123 MB) + head (5 MB) = **~8.2 GB**.
- **Memory Footprint**:
  - FP16/BF16: **~8.0 GB minimum memory required**.
  - FP32: **~16.0 GB minimum memory required**.
- **Constraint Violation**:
  - Exceeds total GPU VRAM (4.0 GB total, 2.61 GB free). Attempting to load onto GPU triggers immediate `torch.cuda.OutOfMemoryError`.
  - Exceeds available System RAM (4.43 GB free). Attempting to load into CPU RAM forces Windows into aggressive swap file thrashing, freezing the desktop and threatening process termination.
- **Result Pursuant to Prompt Section 62**:
  *"If Kev-4B is too large for this machine: that is a result... Do not distort the workstation configuration merely to make a benchmark model look viable. The model must fit AstraRun and this workstation. AstraRun and this workstation do not need to fit the model."*

---

## 3. Selected Model & Runtime Strategy for v0.4

1. **Selected Model**: **`jaredpalmer/kev-0.8b`**.
2. **Device**: **CPU** (`torch+cpu`) with option for GPU where VRAM permits.
   - Preserves 100% of GPU VRAM for the workstation user's interactive display, IDEs, browser hardware acceleration, and AI Bridge.
   - Eliminates CUDA driver contention and runtime crash risks.
3. **Execution Mode**: **Strict Shadow Mode** (`"mode": "shadow"`).
   - Zero production execution authority.
   - Dispatched asynchronously on background threads to ensure 0ms latency impact on the PySide6 launcher interface.
