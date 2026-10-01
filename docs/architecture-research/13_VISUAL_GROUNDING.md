# 13 — Visual Grounding, DPI Scaling & Coordinate Architecture

> **Status**: APPROVED RESEARCH & ARCHITECTURAL SPECIFICATION  
> **Phase**: 5 — Windows Control Surfaces & Direct Interaction APIs  
> **Focus**: Visual Grounding Models, DPI Scaling, Virtual Screen Geometry, Coordinate Normalization, and Fallback Verification  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Executive Summary & Grounding Feasibility

When native Windows control surfaces (Win32, COM, UIA, CDP) fail, AstraRun must locate interactable elements directly on a rendered display. However, naive visual automation on a physical workstation routinely fails due to **multi-monitor virtual coordinate spaces**, **per-monitor DPI scaling (100%, 125%, 150%)**, and **excessive VRAM requirements of general-purpose VLMs**.

| Model / Approach | Parameters | VRAM Footprint `[ESTIMATED]` | Latency (RTX 2050) `[ESTIMATED]` | Coordinate Precision | Feasibility on RTX 2050 4GB |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **UI-TARS 7B / Qwen2-VL 7B** | 7.0B | 4.8 GB – 6.2 GB (Q4) | 2,200 – 4,500 ms | High | **PROHIBITED** (Exceeds 3.4 GB VRAM limit) |
| **Florence-2 Large (Microsoft)** | 770M | ~1.4 GB (FP16) / ~850 MB (INT8) | 120 – 250 ms | High (OD / OCR / Dense BBoxes) | **HIGHLY FEASIBLE** `[TARGET]` |
| **Florence-2 Base (Microsoft)** | 230M | ~450 MB (FP16) | 45 – 90 ms | Moderate | **EXCELLENT FAST PATH** `[TARGET]` |
| **OmniParser v2 IconDetect (YOLO)** | 50M | ~180 MB | 25 – 40 ms | High for standard icons | **HIGHLY FEASIBLE** `[TARGET]` |
| **WinRT Native OCR (Windows API)** | 0 (Host OS) | 0 MB (Host Service) | `ESTIMATED` (15 – 45 ms) | `NOT_MEASURED` (Clean text target) | Candidate Tier 1 Detector `[HYPOTHESIS]` |

---

## 2. Multi-Monitor Coordinate Normalization & DPI Geometry

### 2.1 The Windows Virtual Desktop Space
A Windows workstation with multiple monitors or high-DPI laptop displays does not have a simple $(0, 0)$ origin.
- The **Virtual Screen** spans all monitors:
  ```
  x_min = GetSystemMetrics(SM_XVIRTUALSCREEN)      (Can be negative!)
  y_min = GetSystemMetrics(SM_YVIRTUALSCREEN)      (Can be negative!)
  width = GetSystemMetrics(SM_CXVIRTUALSCREEN)
  height = GetSystemMetrics(SM_CYVIRTUALSCREEN)
  ```
- If a secondary 1080p monitor is positioned to the left of the primary 4K display, coordinates on that monitor have negative $x$ values (e.g., $x = -1920$). Passing raw normalized coordinates $[0, 1]$ mapped to a single screen causes clicks to land in the void or on the wrong monitor.

### 2.2 Per-Monitor DPI Awareness (PerMonitorV2)
Windows applies scaling factors (e.g., 125% on 1080p laptops, 150% or 200% on 4K laptops). If an agent is not DPI-aware, Windows returns virtualized DPI-scaled coordinates, but physical mouse injection uses unscaled hardware pixels.

**Mandatory AstraRun Initialization**:
```python
import ctypes
# Inform Windows OS that Astra process is per-monitor DPI aware v2
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)) # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
```

### 2.3 Window-Relative Coordinate Protocol
To avoid multi-monitor drift and accidental desktop clicks, AstraRun must **normalize coordinates relative to the target application's window bounding box**, not the global screen:

$$\begin{aligned}
X_{\text{screen}} &= X_{\text{window\_left}} + (X_{\text{norm}} \times W_{\text{window}}) \\
Y_{\text{screen}} &= Y_{\text{window\_top}} + (Y_{\text{norm}} \times H_{\text{window}})
\end{aligned}$$

Where:
- $X_{\text{norm}}, Y_{\text{norm}} \in [0.0, 1.0]$ are normalized bounding box offsets.
- $(X_{\text{window\_left}}, Y_{\text{window\_top}}, W_{\text{window}}, H_{\text{window}})$ are retrieved via `GetWindowRect(hwnd)`.

---

## 3. Grounding Pipeline Architecture

```mermaid
flowchart TD
    Req[Visual Target Request:\n'Click Export Button'] --> Win[Capture Window Region\nTarget HWND Screenshot]
    
    Win --> Step1[Step 1: WinRT Native OCR\nExtract exact text matches + bboxes\nLatency: 15-30ms | 0 VRAM]
    Step1 --> TextFound{Text Found?}
    
    TextFound -->|Yes| TargetBox[Compute Bounding Box Center]
    TextFound -->|No| Step2[Step 2: Lightweight Visual Detector\nFlorence-2 / OmniParser IconDetect\nLatency: 80-150ms | < 800 MB VRAM]
    
    Step2 --> IconFound{Icon / Element Found?}
    IconFound -->|Yes| TargetBox
    IconFound -->|No| Escalate[Escalate to Teacher Model or\nPrompt User Clarification]

    TargetBox --> Translate[Translate to Absolute Pixels\nWindow Rect Offset + DPI Scaling]
    Translate --> Act[Execute Action\nClick or Focus]
    Act --> Verify[Post-Action Screenshot Diff\nVerify visual state change]
```

### 3.1 Step 1: WinRT Native OCR (Zero-Memory Fast Path)
- Windows 10/11 includes built-in OCR accessible via `Windows.Media.Ocr`.
- Runs on the CPU via OS runtime services.
- Returns word-level and line-level bounding boxes in **< 30 ms**.
- **90% of visual button clicks** ("Submit", "Save", "Settings", "Cancel") are resolved here without loading any ML model.

### 3.2 Step 2: Florence-2 / OmniParser (Icon & Shape Detection)
- For graphical buttons without text (magnifying glass, trash can, hamburger menu, gear):
- Florence-2 Base/Large (230M–770M parameters) or OmniParser YOLO detect visual UI primitives.
- Memory budget: **450 MB – 850 MB VRAM**, comfortably within the 3.4 GB free VRAM headroom on the RTX 2050.

---

## 4. Visual Verification via Screenshot Diffing

`[USER_REQUIREMENT]` In the Observe $\to$ Act $\to$ Verify loop, every visual action must verify its outcome:
1. **Pre-Action Snapshot**: Capture hash/features of target region.
2. **Action Dispatch**: Dispatch synthetic click or keyboard entry.
3. **Post-Action Snapshot**: Wait 100 ms (UI animation settle) and capture target region.
4. **Verification Delta**:
   - Did the button enter an active/pressed state?
   - Did a modal or dropdown appear?
   - Did the text input field acquire a cursor / update its value?
5. If delta is 0% after 2 retries, flag action failure and trigger replanning.

---

## 5. Synthesis & Architectural Invariants

1. **No 7B+ VLMs for Local Desktop Use**: Qwen2-VL 7B and UI-TARS are excluded from local resident execution due to VRAM overflow.
2. **WinRT OCR Fast-Path Hypothesis**: Evaluate OS-native text OCR as candidate zero-VRAM fast path prior to neural visual models `[HYPOTHESIS]` (subject to validation in Lab E).
3. **PerMonitorV2 Awareness**: All coordinate transformations must strictly account for monitor offsets and DPI scaling factors.
4. **Window-Relative Scoping**: Never perform full-desktop unconstrained visual sweeps when the target application window is known.
