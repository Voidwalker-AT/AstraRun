# 02 — Comprehensive Claim / Evidence Matrix

> **Milestone**: Architecture Research & Reality Audit  
> **Repository**: `E:\Workspace\Active\AstraRun`  
> **Status**: EVIDENCE CLASSIFICATION COMPLETE  
> **Date**: 2026-09-30  

---

## 1. Classification Categories

Every technical capability and architectural claim in AstraRun is classified strictly under one of the following evidence tiers:
- `LIVE_PHYSICAL_VERIFIED`: Directly executed and empirically verified on host Windows 11 hardware with real OS state changes.
- `LIVE_READ_ONLY`: Empirically verified on host hardware without state mutation (e.g. querying ports, Wi-Fi status).
- `LIVE_MUTATING`: Empirically verified on host hardware producing real physical side effects (files written, windows moved).
- `USER_DOGFOOD`: Validated during resident daily-driver usage by human user.
- `LIVE_FIXTURE_VERIFIED`: Verified with live hardware using isolated temporary fixtures (temp files, loopback ports).
- `AUTOMATED_ONLY`: Verified only within automated pytest unit/integration test runs.
- `SYNTHETIC_ONLY`: Evaluated purely against mock objects or synthetic benchmark dictionaries.
- `ARCHITECTURAL_SCAFFOLDING`: Skeleton classes and interfaces implemented without complete production engine wiring.
- `DOCUMENTED_ONLY`: Claimed in documentation or ADRs but not found in active code.
- `BROKEN`: Code exists but fails under real physical execution.
- `NOT_IMPLEMENTED`: Architectural target planned for future milestones with zero code present.
- `UNKNOWN`: Insufficient evidence to classify without dedicated hardware experiment.

---

## 2. Complete Claim / Evidence Matrix

| Subsystem / Capability | Location in Codebase | Classification | Empirical Evidence & Hardware Grounding | Critical Limitations & Technical Debt |
| :--- | :--- | :---: | :--- | :--- |
| **Fast-Path App Launcher** | `src/astrarun/routing/deterministic.py` | `LIVE_MUTATING` / `USER_DOGFOOD` | Alt+Space launches apps via `ShellExecuteW` / `os.startfile` in $< 15\,\text{ms}$. Dogfooded daily. | Only matches registered apps, folders, URLs. Fails on descriptive natural language. |
| **Fuzzy Candidate Search** | `src/astrarun/search/matcher.py` | `LIVE_READ_ONLY` / `USER_DOGFOOD` | In-memory search across ~400 apps/folders with $< 3.5\,\text{ms}$ mean latency. | Pure string fuzzy matching; lacks semantic understanding. |
| **Native Wi-Fi Scanning & Status** | `src/astrarun/tools/wifi.py` | `LIVE_READ_ONLY` | Verified in Live Acceptance Gate B via `wlanapi.dll`. Scans BSS networks in $< 120\,\text{ms}$. | Does not support captive portal authentication. |
| **Native Wi-Fi Connection** | `src/astrarun/tools/wifi.py` | `LIVE_MUTATING` | Connects to targeted SSID profile via `WlanConnect`. Verified in Gate B. | Requires pre-existing Windows network profile for encrypted networks. |
| **Battery Health Report Generation**| `src/astrarun/tools/system_adapter.py` | `LIVE_MUTATING` | Generates official HTML report via `powercfg /batteryreport` in Downloads. Verified 154KB output. | Bounded to powercfg.exe; does not expose granular live discharge wattage. |
| **Hardware Telemetry (CPU/RAM/Disk)**| `src/astrarun/capabilities/registry.py` | `LIVE_READ_ONLY` | Queries psutil and ctypes for real-time CPU, RAM, and disk quotas in $< 100\,\text{ms}$. Verified Gate C. | Basic metrics only; lacks per-process GPU utilization metrics. |
| **Workstation Resource Locking** | `src/astrarun/agent/locking.py` | `LIVE_FIXTURE_VERIFIED` | Verified mutual exclusion for `WINDOW`, `FILE`, `NETWORK:WIFI`, and `PROCESS` in Gate 3. | Single-machine in-memory mutex only; lacks distributed or OS-level file handle hooks. |
| **Live Task HUD V2 & Motion System**| `src/astrarun/ui/hud.py`, `motion.py` | `LIVE_PHYSICAL_VERIFIED` | Non-focus-stealing floating window (`WS_EX_NOACTIVATE`) with rolling ETA and reduced-motion zeroing. | Multi-task queuing currently limited; does not support dynamic task swapping in UI. |
| **Topological DAG Execution Engine**| `src/astrarun/agent/graph.py`, `loop.py` | `LIVE_FIXTURE_VERIFIED` | Full Kahn's cycle detection, multi-branch scheduling, and OutputReference resolution. Verified Gate G. | In-process execution only; cannot pause and resume across host restarts. |
| **Dynamic Plug-In Discovery** | `src/astrarun/agent/indexer.py` | `LIVE_FIXTURE_VERIFIED` | Discovered and ranked novel `reverse_text` capability at runtime in $< 55\,\text{ms}$. Verified Gate D. | Semantic retrieval works; however, argument extraction still relies on hardcoded regexes in planner. |
| **Multi-Step OutputReference Dataflow**| `src/astrarun/agent/planner.py`, `models.py` | `LIVE_FIXTURE_VERIFIED` | Chained `reverse_text` $\to$ `save_text_file` writing to disk. Verified Gate E. | Output field mapping is hardcoded for known names (`"reversed"`, `"output_file"`). |
| **Dynamic Closed-Loop Replanning** | `src/astrarun/agent/planner.py`, `loop.py` | `LIVE_FIXTURE_VERIFIED` | Substituted fallback sensor on failure, recorded `PlanRevision`. Verified Gate F. | Replan logic currently looks up sibling tools in same domain; cannot synthesize novel recovery DAGs. |
| **Laya Intent Router** | `src/astrarun/routing/laya.py` | `AUTOMATED_ONLY` / `RESIDENT_OVERHEAD` | Evaluated in shadow mode. Consumes ~1 GB RAM. Zero execution authority. | Massive RAM tax for simple 10-class labeling; completely redundant given semantic indexer. |
| **Kev LoRA Pointer Router** | `src/astrarun/routing/kev.py` | `ARCHITECTURAL_SCAFFOLDING` | Code exists for Qwen-0.8B LoRA pointer head. Operates only in shadow tests. | Heavy dependency overhead; dead code in production runtime. |
| **Jev External Reference Router** | `src/astrarun/routing/jev.py` | `ARCHITECTURAL_SCAFFOLDING` | HTTP client for external System One API. | Unused in daily driver; dead code. |
| **Neural Structure Engine (spaCy)** | `src/astrarun/nlp/structure_engine.py` | `LIVE_FIXTURE_VERIFIED` | Clause segmentation and literal preservation via `en_core_web_sm` (~40 MB RAM). | Brittle on complex colloquial phrasing with missing conjunctions. |
| **UI Automation (UIA) Control** | `src/astrarun/capabilities/` | `AUTOMATED_ONLY` / `FRAGILE` | Tested on Windows Notepad in unit tests. | Highly brittle on Chromium, Vivaldi, and modern desktop apps. Slow latency ($200–800\,\text{ms}$). |
| **Browser CDP / DOM Control** | None | `NOT_IMPLEMENTED` | Zero code in codebase. | Planned for future milestone. |
| **Visual Grounding & Screenshots** | None | `NOT_IMPLEMENTED` | Zero code in codebase. | Planned for future milestone. |
| **Local OCR Engine** | None | `NOT_IMPLEMENTED` | Zero code in codebase. | Planned for future milestone. |
| **Dynamic Code Execution Sandbox**| None | `NOT_IMPLEMENTED` | Zero code in codebase. | Planned for future milestone. |
| **Terminal / CLI Command Sandboxing**| None | `NOT_IMPLEMENTED` | Zero code in codebase. | Planned for future milestone. |
| **Secret Broker Architecture** | None | `DOCUMENTED_ONLY` | Specified in `04_USER_REQUIREMENTS.md`. | Not yet implemented in codebase. |
| **Procedural Skills Compiler (Hermes)**| `src/astrarun/learning/skills.py` | `ARCHITECTURAL_SCAFFOLDING` | Rudimentary SQLite pattern miner from v0.8.5. | Cannot synthesize or generalize executable code trajectories. |
| **Model Residency Manager** | None | `NOT_IMPLEMENTED` | Proposed in research plan. | Models currently load directly in main thread. |
