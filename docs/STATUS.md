# AstraRun v0.2 Status Report

> **Date**: 2026-09-27  
> **Status**: STABLE / VERIFIED  
> **Milestone**: v0.2 Complete (Discovery, Fuzzy Search & Routing Intelligence Foundation)  

---

## 1. What Works Completely

1. **Multi-Signal Fuzzy Matching Engine**:
   - Evaluates exact matches (`1.0`), alias exact matches (`0.98`), prefix matches (`0.92`), word-token prefix matches (`0.88`), contiguous substring matches (`0.82`), acronym matches (`0.78`), single-drop typos (`0.80 - 0.86`), and Damerau-Levenshtein edit-distance (`0.65 - 0.80`).
   - Uses precomputed terms (`PrecomputedTerm`) to evaluate ~400+ candidates in under 3.03ms mean (21µs p50).
   - Frequency/recency ranking boost is strictly bounded (`<= 0.03`) and cannot overpower a superior textual match.

2. **Ranked Suggestions UI**:
   - Dynamic suggestion drawer with visual category badges (`APP`, `FOLDER`, `WEB`, `COMMAND`).
   - Keyboard navigation via `Up` and `Down` arrow keys.
   - `Tab` autocompletes the selected suggestion title into the input box.
   - `Enter` executes the selected suggestion or evaluates the raw query against the `0.75` threshold.
   - Smooth window height transitions and focus handling.

3. **Expanded Application Discovery**:
   - Added Windows User and System Start Menu `.lnk` shortcut scanning (`%APPDATA%` and `%PROGRAMDATA%`).
   - Filtered out uninstaller binaries, documentation links, and invalid targets.
   - Discovered applications expanded from 83 to **395 applications** (411 total candidates).
   - Added native Windows `os.startfile()` support for `.lnk` shortcuts to avoid `CreateProcess` failures.

4. **Multi-Monitor Foreground Positioning**:
   - Queries `GetForegroundWindow()` and `MonitorFromWindow()` via Win32 ctypes.
   - Positions launcher centered horizontally and upper-third vertically on the active display.
   - Robust fallback cascade: Foreground Monitor -> Mouse Cursor Monitor -> Primary Monitor.

5. **Local-Only Privacy-Preserving Telemetry**:
   - Records structured routing and execution events in `data/routing_events.jsonl`.
   - Defensive regex redaction strips API keys (`sk-...`), Bearer tokens, query credentials, and passwords.
   - 100% local operation with zero outbound network telemetry.

6. **Usage Store**:
   - Thread-safe persistence of launch counts and timestamps in `data/usage.json`.
   - Corrupted file resilience with automatic default state recovery.

7. **Evaluation Benchmark Suite**:
   - Standardized 88-query test suite across exact, alias, verb-prefixed, fuzzy, acronym, typo, and adversarial queries.
   - **100.0% Exact Resolution Accuracy**
   - **100.0% Fuzzy Resolution Accuracy**
   - **100.0% Unresolved Rejection Accuracy**
   - **0.0% FALSE EXECUTION RATE**
   - Mean Latency: **3.03 ms**, p50 Latency: **21.7 µs**.

8. **Automated Test Suite**:
   - **44 automated tests passing** across 11 test modules in 1.48s.

---

## 2. What Partially Works

- **Rich File Indexing**: AstraRun indexes known system folders and active workspaces. Full-disk document indexing (PDFs, code repos) is deferred to workspace orchestration milestones.

---

## 3. What Does Not Work (By Design in v0.2)

- **AI Inference (Laya / Kev)**: Not introduced in v0.2 by strict architectural specification. The deterministic and fuzzy engine is designed to act as the ground-truth baseline and fallback for future neural classifiers.
- **Complex Multi-Step / OS Modification**: Commands like "kill port 3000" or "open the project from yesterday" are safely rejected as `unknown` (0.0% false execution rate).

---

## 4. Known Bugs & Edge Cases

- **PowerToys Run Collision**: If PowerToys Run is enabled on `Alt+Space`, AstraRun logs a diagnostic and continues running with direct command line and `--show-now` accessibility.
- **Single-Drop Typo Edge Case**: Queries with single-dropped letters (e.g. `notpad`) are treated with high typo confidence (`0.80 - 0.86`) to ensure auto-execution while rejecting multi-letter acronym abbreviations below `0.75`.

---

## 5. Next Recommended Step

**Milestone v0.3: Laya Fast Classifier**:
- Implement local microsecond intent classifier for natural language variations.
- Route unknown/ambiguous requests through Laya before final fallback.
- Train/evaluate Laya using telemetry gathered in `data/routing_events.jsonl`.

