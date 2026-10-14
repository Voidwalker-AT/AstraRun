# PHASE F0-24A.2B — Perception-First Computer Use + Deep Notepad++ Physical Laboratory Evidence Report

> **Branch**: `agent/anti-f0-24a1`  
> **Worktree**: `E:\Workspace\Agents\AstraRun-Anti`  
> **Status**: COMPLETED (Development Physical Gates A through J Verified)  
> **Evidence Class**: `PHYSICAL_COMPUTER_USE` / `SOURCE_TREE_TEST`  
> **Oracle Baseline**: 70/70 F0-24A.1 Oracle, Mutation, Runtime, Broker, and Lifecycle Tests PASS  

---

## 1. Executive Summary & Why This Phase Existed

Phase F0-24A.2B was commissioned after independent review identified five critical contradictions in the predecessor F0-24A.2 report:
1. **Notepad++ False Pass**: `type_result.success=false`, `save_result.success=false`, `file_size_bytes=0`, yet counted as pass.
2. **Generalization Accounting**: 119/120 reported misleadingly as 100%.
3. **Resource Cleanup Contradiction**: `process_cleaned_up=false`, `post_debris_detected=true`, yet claimed `PASS_CLEAN`.
4. **Plan-Only Validation**: Actions evaluated purely against plan output rather than physical machine execution.
5. **Exit-Code Only Holdouts**: Verification relying on return codes rather than affirmative postcondition state inspection.

**Phase F0-24A.2B mandates that AstraRun's Computer Use loop become strictly OBSERVABLE**:
* Frame-by-frame immutable perception snapshots (`OBSERVE N -> DECIDE -> ACT -> OBSERVE N+1`).
* Notepad++ utilized as an exhaustive physical laboratory for generic Windows desktop interaction patterns (launch, discover, type, append, replace, Save As, modify & Save, tabs, Find/Replace dialogs, unsaved changes modals, failure recovery, user takeover, cleanup).
* Strictly zero application-specific brand checks (`if app == "notepad++"`, `scintilla`, etc.) in production decision/execution logic.
* Fail-closed F0-24A.1 execution-truth oracle strictly preserved without modification.

---

## 2. Perception-First Architecture Implementation

The perception subsystem was re-architected in [`src/astrarun/computer_use/observation/frame.py`](file:///e:/Workspace/Agents/AstraRun-Anti/src/astrarun/computer_use/observation/frame.py):

### 2.1 Immutable Frame Separation (Raw vs Derived)
* **Raw Desktop State**:
  * Foreground HWND, PID, process name, window title.
  * Desktop bounds, physical cursor coordinate `(x, y)`.
  * Active keyboard modifiers, hardware user takeover status.
  * Visible top-level windows, class names, rectangles, styles.
  * Deep child control tree and UIA properties (`automation_id`, `control_type`, `bounds`, focus state).
  * Modal dialog detection (HWND, title, class, button tree).
  * Target file artifact metrics (size in bytes, mtime, SHA-256 hash).
  * Task-scoped resource ownership via `AstraResourceLedger`.
* **Derived Interpretation**:
  * Semantic role classification (`APPLICATION_WINDOW`, `MODAL_DIALOG`, `IDLE_DESKTOP`).
  * Dialog classification (`SAVE_AS`, `SAVE`, `OPEN`, `UNSAVED_CHANGES`, `NONE`).
  * Target ownership status (`TASK_OWNED`, `PRE_EXISTING_USER`, `UNKNOWN`).
  * Input readiness (`can_receive_input = not user_takeover_active and foreground_matches_target`).

### 2.2 Telemetry & Trace Persistence
Every closed-loop step records complete machine-readable telemetry under `outputs/computer_use_traces/<task_id>/`:
* `frames/frame_*.json`: Full raw and derived state snapshots at decision points.
* `decisions.jsonl`: Action selection, chosen capability, arguments, confidence, and rationale.
* `actions.jsonl`: Broker verdict, dispatch timestamp, completion timestamp, OS return status, action result.
* `transitions.jsonl`: Pre-frame ID, post-frame ID, expected transition, observed transition, and empirical match status.
* `trace_summary.json` & `task_manifest.json`: Task-level lifecycle verdict and summary.

---

## 3. Physical Laboratory Results: Gates A through J

All 10 development gates were executed physically against Notepad++ on the live Windows workstation:

| Gate | Objective | Physical Result & Transition Observed | Verdict | Evidence Artifact |
|---|---|---|---|---|
| **A** | **Perception Inventory** | Cataloged 15 child controls, UIA properties, bounding boxes. Discovered Scintilla editing pane generically by client area ranking (306,364 px²). | **PASS** | [`docs/audit/F0_24A2B_NOTEPADPP_PERCEPTION.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_NOTEPADPP_PERCEPTION.json) |
| **B** | **Text Insertion & Editing** | Injected unique token `ASTRA_NPP_*`; verified text via universal Win32 `WM_GETTEXT`; appended text; selected & replaced text. | **PASS** | [`docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json) |
| **C** | **Application Save As** | Save As triggered via UI, entered path, saved file to disk. Verified non-empty (124 bytes), SHA-256 matches, content verified. | **PASS** | [`docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json) |
| **D** | **Modify & Save Existing** | Opened existing file, appended text, triggered standard `Ctrl+S`, verified disk file growth (124 B → 150 B) and content update. | **PASS** | [`docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json) |
| **E** | **Multi-Tab Management** | Spawned Tab 2 (`Ctrl+N`), typed distinct tokens in Tab 1 and Tab 2, switched tabs (`Ctrl+PageUp`), verified active document buffer. | **PASS** | [`docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json) |
| **F** | **Dialog Interactions** | Opened & observed Find dialog (`Ctrl+F`), dismissed with `Esc`; opened & observed Replace dialog (`Ctrl+H`), dismissed with `Esc`; detected unsaved changes modal, safely dismissed via `Alt+N` (No). | **PASS** | [`docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_NOTEPADPP_PHYSICAL_RESULTS.json) |
| **G** | **Failure & Recovery** | Target window minimized mid-task; AstraRun observed minimized state, restored to foreground via `SW_RESTORE`, and completed typing. | **PASS** | [`docs/audit/F0_24A2B_RECOVERY_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_RECOVERY_RESULTS.json) |
| **H** | **User Takeover** | Physical input takeover simulated; AstraRun halted synthetic dispatch with `"Physical user input detected. Step paused."`. | **PASS** | [`docs/audit/F0_24A2B_USER_TAKEOVER_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_USER_TAKEOVER_RESULTS.json) |
| **I** | **Wrong-Target Safety** | Action targeting nonexistent application/surface rejected by security pre-condition checks. | **PASS** | [`docs/audit/F0_24A2B_RESOURCE_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_RESOURCE_RESULTS.json) |
| **J** | **Resource Ownership** | Affirmative cleanup verified via `AstraResourceLedger` (0 orphaned processes, 0 orphaned HWNDs). | **PASS** | [`docs/audit/F0_24A2B_RESOURCE_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_RESOURCE_RESULTS.json) |
| **Audit** | **Anti-Hardcoding Scan** | Static AST/string scan across all production files in `src/astrarun/`: 0 brand-check violations (`if app == "notepad++"`, `scintilla`, etc.). | **PASS** | [`docs/audit/F0_24A2B_HARDCODING_AUDIT.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_24A2B_HARDCODING_AUDIT.json) |

All 10 gates passed synchronously in `74.51s` (`scripts/run_f0_24a2b_laboratory.py`).

---

## 4. Special Discovery & Fix: HP System Information OEM Hotkey Collision

During laboratory execution on this workstation (HP environment), a popup dialog titled **HP System Information** was observed.

### Investigation
* **Process**: `HPSEU.UI.WPF` (PID 17300, HP System Event Utility UI).
* **Cause**: On HP laptops, the OEM hotkey daemon listens globally for `Ctrl+Alt+S` to display hardware system information.
* **Mechanism in AstraRun**: In [`src/astrarun/interaction/document.py`](file:///e:/Workspace/Agents/AstraRun-Anti/src/astrarun/interaction/document.py#L208), the Save As shortcut fallback loop included `"Ctrl+Alt+S"`. When dispatched, Windows intercepted the hotkey at the OEM driver level, displaying the dialog.
* **Remediation**:
  1. Terminated `HPSEU.UI.WPF` immediately to clear the UI.
  2. Modified `document.py` to remove `Ctrl+Alt+S` completely, using standard non-colliding Windows shortcuts: `("Ctrl+Shift+S", "F12", "Ctrl+S")`.
  3. Re-verified all save flows; zero OEM dialog popups occurred.

---

## 5. Authoritative Oracle & Baseline Regression

The F0-24A.1 fail-closed completion oracle was re-evaluated against the authoritative test suite:
* **Test Suite**:
  * `tests/test_agent_runtime.py` (11 tests)
  * `tests/eval_v1/test_f0_24a1_adversarial_oracle.py` (36 tests)
  * `tests/eval_v1/test_f0_24a1_oracle_mutations.py` (7 tests)
  * `tests/test_f0_21_adversarial_false_completion.py` (6 tests)
  * `tests/unit/test_f0_15_resource_lifecycle.py` (7 tests)
  * `tests/unit/test_execution_broker.py` (3 tests)
* **Result**: **70 passed in 19.60s (100% PASS)**.
* **Integrity**: Zero oracle mutations, zero relaxed thresholds, zero bypassed verifications.

---

## 6. Stop Boundary Compliance

In strict adherence to the phase mission boundary:
* **NO installer built.**
* **NO packaging executed.**
* **NO frozen holdout executed.**
* **NO git commit or push performed.**
* **Development phase cleanly concluded at Gate J.**

<!-- GOAL_COMPLETE -->
