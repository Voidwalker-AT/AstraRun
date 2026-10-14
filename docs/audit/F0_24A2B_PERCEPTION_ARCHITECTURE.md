# AstraRun Computer Use Perception Architecture & Truth (Phase F0-24A.2B)

## 1. Executive Summary

This document establishes the authoritative perception architecture for AstraRun Computer Use. It documents the empirical reality of what models are available, what is executed at runtime, how desktop state is observed, and how raw sensory data is strictly segregated from derived model inferences.

---

## 2. The 9-Tier Perception Escalation Hierarchy

AstraRun defines a 9-tier hierarchical escalation path (`src/astrarun/perception/models.py:PerceptionTier`):

| Tier | Designator | Backend / Technology | Execution Authority | Latency Budget |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 0** | `TIER_0_WIN32` | Native Win32 APIs (`user32`, `kernel32`, `psutil`) | Hardware & OS Truth | < 5 ms |
| **Tier 1** | `TIER_1_COM` | Application-native COM interfaces (Office, Shell) | Structured API | < 15 ms |
| **Tier 2** | `TIER_2_CDP` | Chrome DevTools Protocol / Chromium DOM | Web Sandbox | < 25 ms |
| **Tier 3** | `TIER_3_UIA` | Windows UI Automation (`UIAutomationCore`) | Structured Accessibility | < 50 ms |
| **Tier 4** | `TIER_4_OCR` | Windows.Media.Ocr / WinRT OCR Engine | Ephemeral Observation | < 120 ms |
| **Tier 5** | `TIER_5_CV` | Classical Computer Vision (OpenCV template matching) | Ephemeral Observation | < 40 ms |
| **Tier 6** | `TIER_6_GROUNDER` | OmniParser v2.0 YOLO (`icon_detect/model.pt`) on CPU | Ephemeral Observation | < 350 ms |
| **Tier 7** | `TIER_7_LOCAL_VLM` | Local SmolVLM-500M on host CPU (`transformers`) | Quarantined Advisor | < 1800 ms |
| **Tier 8** | `TIER_8_EXTERNAL_VLM` | Cloud Multimodal API Fallback | Quarantined Advisor | Network bound |

---

## 3. Empirical Visual Perception Truth

To avoid previous failure modes where "vision" was claimed without actual model invocation, we document the empirical facts:

1. **Available Host Vision Models**:
   - `OmniParser v2.0 icon_detect`: Located at `E:\AI_Models\Vision\OmniParser\icon_detect\model.pt` (verified present).
   - `SmolVLM-500M`: Located at `E:\AI_Models\Vision\SmolVLM-500M` (verified present).
2. **Runtime Memory & Resource Footprint**:
   - Both models are designed to execute strictly on **host CPU** (0.0 MB GPU VRAM), preserving all GPU resources for daily-driver tasks.
   - Neither model is resident during routine desktop tasks. Both load on-demand when an explicit visual perception capability is requested.
3. **When Visual Perception Is Invoked vs Structured Perception**:
   - **Structure-First Principle**: Standard Windows desktop interactions (document editing, button clicks, tab switches, Save As dialogs) rely primarily on Tier 0 (Win32) and Tier 3 (UI Automation). These tiers provide deterministic, machine-readable names, control types, bounding boxes, ValuePatterns, and TextPatterns.
   - **Vision-as-Complement**: Visual perception is invoked when UI Automation is unavailable (canvas elements, game surfaces, custom-drawn icon toolbars, or visual verification).
   - **Observability vs Vision Inference**: Full-screen and window-targeted screenshots are captured at every decision point for human/machine auditability and trace reconstruction. However, the system **honestly records whether a visual semantic model was invoked** (`model_invoked: false`) rather than fabricating vision inferences from unanalyzed pixels.

---

## 4. Separation of Raw Observation vs Derived Interpretation

Every `ComputerUseObservationFrame` strictly separates:

### A. Raw Observation (What Windows / Sensors Reported)
- `foreground_hwnd`, `foreground_pid`, `foreground_title`
- Top-level window enumeration with Win32 bounding rectangles and styles
- Native UI Automation element tree nodes: `automation_id`, `control_type`, `class_name`, `name`, `value`, `patterns`
- Active dialog window handles and class `#32770`
- Raw pixel screenshot and SHA-256 hash
- File system metadata: path existence, file size bytes, raw SHA-256, mtime

### B. Derived Interpretation (What Astra Inferred)
- `semantic_role`: Inferred role (e.g. `EDITABLE_SURFACE`, `MODAL_SAVE_AS_DIALOG`, `TAB_CONTAINER`)
- `ownership_classification`: `TASK_OWNED` vs `PRE_EXISTING_USER` based on ledger fingerprint
- `dialog_classification`: Classification of modal (`SAVE_AS`, `CONFIRMATION`, `OVERWRITE`, `UNSAVED_CHANGES`)
- `can_receive_input`: Boolean inference based on focusability and read-only flags
- `confidence`: Explicit confidence metric (0.0 to 1.0)
- `evidence_sources`: Traceable list of raw fields that justified the inference

---

## 5. Machine-Readable Trace Architecture

Every task produces a self-contained trace under `outputs/computer_use_traces/<task_id>/`:

```
outputs/computer_use_traces/<task_id>/
├── task_manifest.json          # Task goal, start time, environment metadata
├── frames/
│   ├── frame_000001.json      # Structured frame: raw vs derived
│   ├── frame_000001.png       # Targeted screenshot at decision point
│   ├── frame_000002.json
│   └── frame_000002.png
├── decisions.jsonl             # DecisionContextSnapshot + DecisionRecord
├── actions.jsonl               # ActionRecord with mechanism & timing
├── transitions.jsonl           # StateTransitionRecord (PRE vs POST comparison)
├── resources.jsonl             # Task resource allocations and ledger state
├── artifacts.json              # Physical disk artifacts with hashes and byte sizes
└── trace_summary.json          # Overall task verdict, gate evaluations, and residue report
```

This guarantees that an external reviewer can replay Astra's exact information state, reasoning, physical actions, and observed state transitions.
