# Visual Computer Use Research & Architecture (Shadow Mode)

> **Author**: AstraRun Architecture Team  
> **Status**: APPROVED (SHADOW / EXPERIMENTAL)  
> **Target Version**: v0.11 (Research & Prototype) -> v0.12 (Active Tier E)  
> **Platform**: Windows 11 x64  

---

## 1. Executive Summary

While AstraRun prioritizes Tier A (Native APIs) and Tier C (UI Automation) for speed, deterministic reliability, and background execution, certain desktop environments completely resist structured inspection. Examples include:
- Electron and Web applications with inaccessible canvas elements (Figma, Miro, Google Docs canvas mode).
- Legacy Win32 games, emulators, and DirectX full-screen applications.
- Remote Desktop (RDP, Citrix, VMware Horizon) and virtualized sandboxes.
- Custom proprietary GUI toolkits lacking accessibility providers.

To address these scenarios in future milestones without introducing brittle failure modes in v0.11, AstraRun introduces the **Visual Computer Use (VCU) Subsystem** in **Shadow Mode**.

In v0.11, the VCU subsystem captures screen context, computes visual element proposals, and evaluates geometric alignment against UIA ground truth, but does **not** execute unverified mouse clicks on production user sessions.

---

## 2. Windows Screen Capture Architecture

Capturing screen state on Windows 11 involves trade-offs across latency, CPU/GPU overhead, and permission requirements:

| Capture API | Typical Latency | GPU Acceleration | Multi-Monitor Support | Window-Specific Capture |
| :--- | :--- | :--- | :--- | :--- |
| **GDI `BitBlt`** | $15-30\,\text{ms}$ | No (CPU copies) | Yes (Virtual screen) | Yes (`GetDC(hwnd)`) |
| **`PrintWindow` (PW_RENDERFULLCONTENT)** | $20-40\,\text{ms}$ | Partial (DWM) | Yes | Yes (Occuluded windows) |
| **Desktop Duplication API (DXGI)** | $1-3\,\text{ms}$ | Full (Direct3D 11) | Per GPU output | Full desktop only |
| **Windows Graphics Capture (WGC)** | $2-5\,\text{ms}$ | Full (Direct3D 11) | Yes | Yes (Specific HWND) |

### v0.11 Strategy:
- For lightweight observation and testing, AstraRun utilizes GDI / Pillow screenshot routines (`ImageGrab.grab()` or User32 GDI wrappers) with high-DPI awareness (`SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)`).
- Screenshots are saved exclusively to temporary sandboxes or in-memory byte buffers for verification and debugging.

---

## 3. Visual Element Grounding Pipeline

The visual grounding pipeline consists of three sequential stages:

```
┌─────────────────┐     ┌───────────────────────┐     ┌───────────────────────┐
│ Desktop Frame   │ ──> │ OCR & Region Proposal │ ──> │ Target Verification   │
│ (Screen Capture)│     │ (Bounding Boxes)      │     │ (Cross-Check with UIA)│
└─────────────────┘     └───────────────────────┘     └───────────────────────┘
                                                                  │
                                                                  ▼
                                                      ┌───────────────────────┐
                                                      │ Shadow Log / Telemetry│
                                                      │ (Zero Blind Clicks)   │
                                                      └───────────────────────┘
```

1. **OCR & Text Localization**:
   - Extraction of text blocks and associated bounding boxes.
   - Text filtering matches requested user targets (e.g. "Save", "File", "Submit").
2. **Geometric Cross-Validation**:
   - Compare proposed visual bounding boxes $[x, y, w, h]$ against known top-level window rectangles obtained via Win32 `GetWindowRect`.
   - Any visual proposal lying outside the target window's client rect is immediately rejected.
3. **Shadow Mode Logging**:
   - The engine computes what action *would* have been taken, logs the visual confidence score, and compares with the deterministic UIA/Win32 outcome.

---

## 4. Safety Constraints & Invariants

1. **Zero Blind Clicks**:
   - Under no circumstances may the visual pipeline emit a click event without at least one secondary confirmation (e.g., text match + window bounds match).
2. **Strict User Privacy**:
   - Screenshots captured during visual observation are ephemeral. They are never transmitted over the network, never written to persistent logs, and immediately garbage-collected after verification completes.
3. **Reduced Resource Footprint**:
   - Frame capture occurs on-demand (discrete triggers), never as a 60fps continuous screen recording daemon, conserving battery and GPU compute on mobile workstations.
