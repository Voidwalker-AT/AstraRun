# 03 — Physical Machine Profile & Memory Budget Envelopes

> **Execution Platform**: Local Windows 11 Workstation  
> **Date Measured**: 2026-09-30  
> **Target OS**: Windows 11 Home / Pro x64 (Build 26100)  
> **Status**: EVIDENCE-LABELED PROFILE (Facts separated from Hypotheses)  

---

## 1. Measured Physical Hardware Specifications [MEASURED]

The following metrics were collected via live Win32 CIM / WMI and NVIDIA Management queries on the physical host:

| Component | Physical Specification | Status | Measured State / Quota |
| :--- | :--- | :---: | :--- |
| **CPU** | 12th Gen Intel(R) Core(TM) i5-12450H | `[MEASURED]` | 8 Cores (4 P-Cores + 4 E-Cores), 12 Logical Processors |
| **Installed Physical RAM** | 16.0 GB visible (16,409,092 KB) | `[MEASURED]` | **12.35 GB Occupied** by OS & background user workflows |
| **Available Physical RAM** | Uncommitted physical memory headroom | `[MEASURED]` | **3.30 GB (3,462,004 KB Free)** before pagefile expansion |
| **Commit Limit (Virtual Memory)** | 31.0 GB total (32,454,132 KB) | `[MEASURED]` | 12.78 GB Free Virtual Commit |
| **Primary GPU (Dedicated)** | NVIDIA GeForce RTX 2050 Laptop GPU | `[MEASURED]` | 4096 MB VRAM Total, 533 MB active OS use, **~3430 MB Free** |
| **Secondary GPU (Integrated)** | Intel(R) UHD Graphics | `[MEASURED]` | Driver 32.0.101.7088, Shared system RAM adapter |
| **NVIDIA Driver** | 596.49 | `[MEASURED]` | CUDA compute capability supported up to 13.2 |
| **Storage: C:\ (System Drive)** | NVMe SSD | `[MEASURED]` | 288.5 GB Total, **26.9 GB Free** |
| **Storage: E:\ (Workspace Drive)** | NVMe / Data Partition | `[MEASURED]` | 223.3 GB Total, **39.0 GB Free** |

---

## 2. Physical Memory Constraints: Facts vs Hypotheses

### A. Established Machine Facts `[MEASURED]`
1. **Physical Headroom is ~3.30 GB**: With 12.35 GB occupied during measured daily-driver conditions, the machine has ~3.30 GB of physical RAM headroom before triggering disk pagefile swapping.
2. **Dedicated VRAM Headroom is ~3.43 GB**: The RTX 2050 currently has 3430 MB unallocated dedicated video memory.
3. **Storage Headroom is Bounded**: Drive C: has 26.9 GB free; Drive E: has 39.0 GB free. Multi-gigabyte caches or weights directly impact developer disk quotas.

### B. Critical Runtime Variables Requiring Experimental Accounting `[UNVERIFIED / REQUIRES_EXPERIMENT]`
Total inference memory is **never** equal to raw model weight file size on disk. The actual runtime memory equation is:

$$\text{RAM}_{\text{total}} = \text{RAM}_{\text{Astra core}} + \text{RAM}_{\text{worker process}} + \text{RAM}_{\text{mmap pointers}} + \text{RAM}_{\text{CPU buffers}} + \text{RAM}_{\text{context / tool prompt}}$$
$$\text{VRAM}_{\text{total}} = \text{VRAM}_{\text{OS compositor (533 MB)}} + \text{VRAM}_{\text{offloaded layers}} + \text{VRAM}_{\text{KV cache}} + \text{VRAM}_{\text{CUDA context overhead (150–350 MB)}}$$

The following factors are currently unverified on this physical hardware and require dedicated experimental measurement:
- **llama.cpp / Runtime CUDA Context Overhead**: `[ESTIMATED: 150–350 MB]` Initializing the CUDA runtime inside a Python or C++ worker consumes VRAM before any weights or KV cache are allocated.
- **mmap Behavior on Windows**: `[REQUIRES_EXPERIMENT]` Windows handles memory-mapped files differently from Linux. Whether `mmap` pages count against private commit or trigger memory pressure under tight RAM must be verified.
- **KV Cache Allocation**: `[ESTIMATED]` At 4K context with 16-bit KV cache, memory demand is modest (~100–250 MB); at 16K or 32K context with batching, KV cache can exceed 1.0–2.0 GB VRAM.
- **VRAM Spillover Behavior**: `[UNVERIFIED]` If total VRAM allocations cross the 4096 MB boundary (e.g. 533 MB OS + 3.0 GB model + 600 MB KV cache = 4.13 GB), NVIDIA drivers automatically spill the overflow into system RAM, instantly consuming the scarce 3.3 GB physical RAM.
- **Memory Reclamation Post-Termination**: `[REQUIRES_EXPERIMENT]` When a child model worker process exits, whether Windows and the NVIDIA driver immediately release 100% of physical RAM and dedicated VRAM without memory fragmentation or delayed garbage collection must be proven.

---

## 3. Projected Operating Envelopes (Candidate Targets Only)

> [!NOTE]
> The following table represents **candidate architectural budget targets**, NOT established empirical facts. Every line marked `[TARGET]` must be validated through safe empirical measurement before adoption.

| Operating State | Candidate Physical RAM Target | Candidate Dedicated VRAM Target | Status | Architectural Rationale |
| :--- | :---: | :---: | :---: | :--- |
| **Astra Resident Idle** | $< 100\,\text{MB}$ | $0\,\text{MB}$ | `[TARGET]` | Lean background Qt event loop, Win32 hotkey listener, in-memory index. |
| **Lightweight Cognition (Fast Path)** | $< 180\,\text{MB}$ | $0\,\text{MB}$ | `[TARGET]` | Deterministic router, inverted lexical index, regex entity resolver. |
| **On-Demand Planning Worker (Spark 1.7B)** | $< 350\,\text{MB}$ (CPU side) | $\le 2.2\,\text{GB}$ (GPU side) | `[TARGET / HYPOTHESIS]` | Assumes Q4_K_M weights (~1.05 GB) + KV cache (~300 MB) + CUDA context (~250 MB) fit in VRAM. |
| **On-Demand Local Vision / OCR Worker** | $< 400\,\text{MB}$ | $\le 2.0\,\text{GB}$ | `[TARGET / HYPOTHESIS]` | Evaluates native WinRT OCR vs small vision transformer; evictable worker. |
| **Peak Complex Task Execution** | $< 650\,\text{MB}$ | $\le 2.8\,\text{GB}$ | `[TARGET / HYPOTHESIS]` | Enforces 600 MB VRAM safety cushion below the 3.43 GB free limit to prevent spillover. |

---

## 4. Next Empirical Experiments Required `[REQUIRES_EXPERIMENT]`

To convert these hypotheses into facts during Phase 3/Phase 10:
1. **Experiment E-M01**: Measure exact memory delta of the current AstraRun resident core across 100 show/hide hotkey cycles.
2. **Experiment E-M02**: Test CUDA allocation and release lifecycle in an isolated Python/llama.cpp subprocess, measuring VRAM before, during, and 1s/5s/30s post-termination.
3. **Experiment E-M03**: Measure Windows WinRT native OCR memory consumption during full-screen screenshot text extraction.
