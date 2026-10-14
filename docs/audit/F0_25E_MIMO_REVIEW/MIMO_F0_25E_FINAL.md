# MIMO Independent Review — F0-25E

**Repo**: `E:\Workspace\Agents\AstraRun-Anti`
**Reviewer**: MiMo (adversarial, independent, no verdict inherited from Anti)
**Evidence base**: `docs/audit/F0_25E/` (33 files) + independent source inspection + production log corroboration + independent hashing
**Production source modified**: none · **Fixes applied**: none · **Commits/pushes**: none · **Dogfood re-run**: none · **main.py executed**: never
**Overall verdict**: **FAIL**

---

## 1. Headline findings

**What F0-25E genuinely fixed (real progress over F0-25D.1):**

1. **Raw evidence integrity is real.** All 20 artifacts in `F0_25E_RAW_MANIFEST.json` independently re-hashed: **20/20 SHA-256 + sizes match**. No post-freeze tampering.
2. **Screenshots are honestly labeled at the audit level.** I personally inspected all 15 PNGs. Every `F0_25E_UI_AUDIT.json` entry correctly says foreground `Antigravity.exe`, `astra_launcher_visible: false` — matching pixels. The F0-25D.1 "descriptions claim launcher visible while pixels show Antigravity" fraud is **not repeated**.
3. **The evaluator no longer re-runs the generated program.** `f0_25e_evaluator.py` contains no subprocess; the content oracle parses files only. The F0-25D.1 artifact-contamination defect is gone.
4. **No fake editor/terminal PASS.** Both dimensions are NOT_APPLICABLE; no manufactured milestone PASSes for them.
5. **The content oracle is real.** RESULT_CORRECTNESS rests on actual tokenization/count comparison — I recomputed it independently: **mathematical match TRUE (14 tokens, all = 1, exact key match)**.
6. **UI failures are surfaced, not hidden.** ASTRA_LAUNCHER_UI and USER_OBSERVABILITY are honestly FAIL; suggested verdict PARTIAL instead of F0-25D.1's bogus 15/15 PASS.
7. **Observer non-causality is source-provable.** Exhaustive call-path audit: no keyboard/mouse APIs, no post-submission IPC, no `main.py` execution, no editor/terminal/browser launches.

**What F0-25E did NOT fix:**

1. **A hardcoded PASS survives inside the engine that claims "zero hardcoded PASS"**: `RESOURCE_RESTORATION` is a literal `"PASS"` with fabricated evidence (`evaluator L430–437`, personally verified), mirrored by `generate_resource_delta_report` literal zeros (L506–517). Same defect class as F0-25D.1, relocated.
2. **Provenance counts are polluted**: the "11 model events / 32 broker events" are grep-excerpts of one production log spanning **18:09–20:46** across ≥7 prior task attempts (incl. `MODEL_UNAVAILABLE` failures). In-window: **1/11 model, 5/32 broker**. `CAUSAL_PROVENANCE = PASS` on `counts > 0` is nearly vacuous — prior runs alone satisfy it.
3. **`PROGRESS_UI = PARTIAL` is an else-branch default on exactly zero evidence** (hud=0, launcher=0; code: `PASS if … else PARTIAL`, L345–346). Pixels: **0/15 frames show any Astra UI**. Should be FAIL.
4. **`OUTPUT_PRESENTATION = PASS` is file existence.** The user asked "show me the useful result"; nothing was ever shown — no JSON, no Explorer, no terminal, no in-launcher summary, no reveal activity in the production log. Mandatory FAIL per the review contract.
5. **"Pure function over immutable frozen evidence" is false**: ~5 dimensions read the live `E:\AstraDogfood\word_frequency` (not in the manifest); the negative-control JSON and capability-audit JSON sit outside the freeze; extra files in `raw/` post-freeze would go undetected.
6. **The negative control is an assertion, not a proof**: 5-second do-nothing run; `windows_spawned_by_observer: 0` is a literal; no equivalent request is ever submitted; its raw frames/events were wiped by the dogfood run before freeze.
7. **The launcher visibility/topmost "fix" has no observable effect**: source sets `WindowStaysOnTopHint` (`launcher.py:216–218`) and `SetWindowPos(HWND_TOPMOST)` (`presentation.py:62`), yet **all 15 frames show zero Astra windows** and `window_count` never differs from baseline (14).

---

## 2. Claim classification (independent)

| Claim | Classification | Key evidence |
|---|---|---|
| Raw evidence immutable (20/20) | **PROVEN** | Independent SHA-256 of every manifest entry |
| AstraRun.exe ran during the task | **PROVEN** | Production log PID 14464, IPC handshake with observer (corroborating, outside frozen pkg) |
| Correct binary used (installed, rebuilt 20:44:53) | **PROVEN** (externally; package omitted it) | dist = build = installed = `245a205e…2c563`, 12,057,208 B |
| Artifacts created in-run from clean baseline | **PROVEN** | fs events 0→3 files, mtimes 20:46:04 inside window |
| main.py authored by local model → broker → disk | **PROVEN** | synth hash `31b559a4d149` = delivery `source_sha256` = frozen sha256 |
| Request submitted via IPC | **PROVEN** | `events.jsonl` ↔ log `SUBMIT_QUERY` (±1 s) |
| Result mathematically correct | **PROVEN** | Independent recomputation, no execution of main.py |
| Observer non-causal after submission | **SUPPORTED** | Full source call-path audit; NC adds only weak support |
| This run's actions passed dispatch/delivery governance | **SUPPORTED** | In-window `execute_dynamic_tool` + 3× `deliver_artifact` lines |
| Model produced the executed tool content | **SUPPORTED** | Line 11 in-window + hash chain |
| "11 model / 32 broker events" as this run's provenance | **CONTRADICTED** | Harvested log lines spanning hours; 1/11 and 5/32 in-window |
| "Launcher HWND_TOPMOST rendering visibly on desktop" | **CONTRADICTED** | 0/15 pixels; `astra_windows=[]` 15/15; constant window_count |
| PROGRESS_UI = PARTIAL | **CONTRADICTED** | Zero visible frames; else-branch default |
| OUTPUT_PRESENTATION = PASS | **CONTRADICTED** | Nothing presented anywhere |
| RESOURCE_RESTORATION = PASS | **CONTRADICTED as evidence / UNVERIFIED as outcome** | Hardcoded literals; independent inspection finds no proven violation either |
| "Pure function over immutable frozen evidence" | **CONTRADICTED** | Live-dir reads; NC/capability JSON unfrozen |
| Negative control PASS | **UNVERIFIED** | Literals + destroyed raw evidence + no equivalent request |
| Model caused the execute_dynamic_tool *decision* | **UNVERIFIED** | Zero frozen planner/reasoner events |
| Causal chain "complete verified sequence" (Anti stage list) | **CONTRADICTED** | Stages 2/5 canned prose; stage 7 (presentation) never happened |
| Stage hints LAUNCHER_OPEN / REQUEST_POPULATED / DELIVERABLES_PRODUCED | **CONTRADICTED** vs pixels | Frames show none of those states |

---

## 3. Acceptance matrix (independent — not inherited)

| Dimension | Anti | **MIMO** | Basis (abridged) |
|---|---|---|---|
| `GOAL_CORRECTNESS` | PASS | **PASS** | 3 deliverables exist, non-empty, content verified |
| `CAUSAL_PROVENANCE` | PASS | **UNVERIFIED** | Vacuous counts; prior-run pollution; planner link absent |
| `PLANNING_SEMANTICS` | PASS | **UNVERIFIED** | No frozen goal-interpretation/planning evidence for this run |
| `TOOL_DECISION_EXECUTION_ALIGNMENT` | PASS | **PASS** | In-window execute line with exact goal (broker L28) |
| `HOST_COMPUTATION` | PASS | **PASS** | In-window delivery + fs mtimes + hash equality |
| `ASTRA_LAUNCHER_UI` | FAIL | **FAIL** | 0/15 pixels; 0/15 enumeration |
| `PROGRESS_UI` | PARTIAL | **FAIL** | Zero evidence; PARTIAL was a default, not a grade |
| `VISUAL_DESKTOP_ALIGNMENT` | PASS | **PARTIAL** | Frames exist and time-correlate with fs events; correlation predicate never computed; stage labels misrepresent content |
| `EDITOR_INTERACTION` | N/A | **NOT_APPLICABLE** | Correct outcome (hardcoded mechanism noted) |
| `VISIBLE_TERMINAL_EXECUTION` | N/A | **NOT_APPLICABLE** | Correct outcome (inverted predicate noted: presence of terminal would PASS) |
| `OUTPUT_PRESENTATION` | PASS | **FAIL** | Nothing shown to the user; existence ≠ presentation |
| `RESULT_CORRECTNESS` | PASS | **PASS** | Oracle real; independently reproduced |
| `SEMANTIC_QUALITY` | PASS | **PASS** | Case/punct/top10/JSON all confirmed |
| `RESOURCE_RESTORATION` | PASS | **UNVERIFIED** | Hardcoded PASS + fabricated evidence; no proven violation found either |
| `USER_OBSERVABILITY` | FAIL | **FAIL** | Human could learn nothing about Astra from any frame |

**MIMO tally: 5 PASS · 1 PARTIAL · 4 FAIL · 2 N/A · 3 UNVERIFIED** (Anti: 10 PASS · 1 PARTIAL · 2 FAIL · 2 N/A)

Full detail: `MIMO_F0_25E_ACCEPTANCE_MATRIX.json`.

---

## 4. Why Astra is invisible (independent investigation)

Established facts:

- **AstraRun.exe was running**: PID 14464, started 20:45:39, single-instance mutex, IPC pipe, hotkey registered, spawned by the observer (`Popen(CANONICAL_EXE, '--show-now')` observer L616).
- **Astra claims it owned a visible HWND**: production log `LAUNCHER_CREATED` 20:45:43, presented at (448, 48), lifecycle `SHOW_EVENT vis=True → INTERACTIVE vis=True act=True focus=True` through 20:45:45.
- **The observer's enumerator would have matched it if visible**: `enumerate_desktop_windows` records every `IsWindowVisible` top-level window with class/title; `filter_astra_windows` accepts process `astrarun` + title `AstraRun` (`launcher.py:215`) or class containing `qt`. No filter bug could hide an existing visible window.
- **But**: `astra_windows: []` in all 15 frames; `window_count = 14` in all 15 frames — **identical to baseline before AstraRun started**. The launcher never appeared as a visible top-level window at any capture.
- **And**: pixels at the exact moments the log says `INTERACTIVE` (frame_0001 ≈ 20:45:44.8, frame_0002 ≈ 20:45:45.9) show pure Antigravity, including the (448,48) region.
- **Invocation**: Alt+Space was **not** used; the launcher was presented programmatically via `--show-now` + IPC `SHOW_MAIN_UI`/`POPULATE_QUERY`.
- Ruled out by evidence: process-not-running (log proves running), wrong observer desktop (same desktop shows Antigravity live), cloaked-on-virtual-desktop (would still pass `IsWindowVisible` and be enumerated), off-screen (position (448,48) is on-screen), closed-before-capture (log shows it alive and INTERACTIVE), observer capturing wrong desktop (frames are live and time-consistent).

**Root cause: UNKNOWN.** The defensible statement is: *Astra's Qt-level self-report of visibility is contradicted by two independent OS-level channels; the mechanism (window never truly mapped vs. unmapped without a log line vs. other) cannot be determined post-hoc from available evidence.*

---

## 5. Observer capability boundary (summary)

Source-proven incapable after submission: typing, clicking, post-submission IPC, executing main.py, opening editors/terminals/browsers, repairing artifacts during acceptance.
Real caveats: partial write guard (bypassable via `io.open`/`shutil`/`os.rename`), pre-guard target-dir wipe, pre-run process kills, raw-evidence destruction on re-run, no teardown of the spawned AstraRun child, and its capability-audit JSON is a hand-written literal (L502) — not proof by itself.
Full classification: `MIMO_F0_25E_OBSERVER_AUDIT.json`.

## 6. Negative control

Dispatch-disabled **equivalence never tested** (no request submitted); `windows_spawned_by_observer: 0` literal; only real measurement = 0 files after 5 idle seconds post self-wipe; raw evidence destroyed before freeze; JSON outside manifest.
**Verdict: UNVERIFIED** — `MIMO_F0_25E_NEGATIVE_CONTROL_AUDIT.json`.

## 7. Causal chain (abridged)

`REQUEST_SUBMITTED (proven)` → `planner/goal decision (UNVERIFIED — no frozen event)` → `execute_dynamic_tool dispatch 20:45:51 (supported)` → `Qwen synth 20:46:02 hash=31b559a4d149 (proven)` → `sandbox exec 846.72 ms (supported)` → `broker delivery 20:46:04, hash-matched (proven)` → `files on disk (proven)` → `presentation (CONTRADICTED — never occurred)`.

Task-ID layers `task_f0_25e` / `task_99dc59e6` / `task_30b5a40d` never co-link inside the frozen package (only via the external production log). Full detail: `MIMO_F0_25E_CAUSAL_CHAIN.json`.

## 8. Model & broker provenance

- **Model**: 11 lines = grep excerpts, all stamped at harvest; **1/11 in-window**; zero request/response hashes, zero planner events. `MIMO_F0_25E_MODEL_PROVENANCE.json`.
- **Broker**: 32 lines = registry/delivery logs, not authorization verdicts; **5/32 in-window**; ≥7 prior task IDs incl. two `MODEL_UNAVAILABLE` failures; no ALLOW/BLOCK audit records frozen. In-window dispatch + hash-matched delivery nonetheless SUPPORTED. `MIMO_F0_25E_BROKER_PROVENANCE.json`.

## 9. Content oracle

Independent recomputation (no execution): 14 tokens / 14 unique / all 1; JSON keys exactly match; differences: **none**. `main.py` semantics: `re.findall(r'\b[A-Za-z0-9_]+\b', text.lower())` + `Counter`; writes its own sample input (self-contained, prompt-compliant); stdout uncaptured; trivial input (all counts = 1). Literal task correct; implementation adequate but prompt-shaped (system prompt at `cognition/service.py:421-424` names the exact regex/filenames — no canned program body exists in repo). `MIMO_F0_25E_CONTENT_ORACLE.json`.

## 10. Output presentation & user observability

**OUTPUT_PRESENTATION = FAIL.** Nothing was opened, shown, or summarized to the user. **USER_OBSERVABILITY = FAIL.** A human watching these frames could not tell that Astra received the request, planned, worked, selected a tool, executed, succeeded, or produced a result. Internal logs do not count.

## 11. PROGRESS_UI = PARTIAL reassessed

No Astra progress UI appears in any frame. The PARTIAL came from an else-default on zero evidence. **Reclassified FAIL.**

## 12. Resource restoration

Anti's PASS is hardcoded (source-verified). Independent inspection: sandbox `task_30b5a40d` retained **by design** (`dynamic_builder.py:348 preserve_on_exit=True`); target dir holds only intended deliverables; ~380 older sandbox entries predate the run (not charged to F0-25E); harness left its spawned PID 14464 alive at eval time; prior-session ledger orphans unaddressed. No proven violation, no measurement → **UNVERIFIED**. `MIMO_F0_25E_RESOURCE_AUDIT.json`.

## 13. Canonical product identity (§16)

Independently hashed: `dist\AstraRun\AstraRun.exe` = `build\AstraRun\AstraRun.exe` = installed `C:\Users\hp\AppData\Local\Programs\AstraRun\AstraRun.exe` = **SHA-256 `245a205ea0222ec2f9f761d9376baf635af32a3997f49c8eeb7ab7b213e2c563`**, 12,057,208 bytes, mtime 2026-10-11 20:44:53. Built ≡ installed ≡ tested binary; rebuilt ~1 minute before the run (differs from F0-25D.1's `9b1b5add…`). Observer launches the installed path. **The F0-25E package itself recorded no build identity — a gap this review closes.**

## 14. Acceptance engine audit (§17)

Verdict production, personally verified:

| Type | Instances |
|---|---|
| Evidence-derived (sound) | RESULT_CORRECTNESS, SEMANTIC_QUALITY (oracle-based); ASTRA_LAUNCHER_UI / USER_OBSERVABILITY / PROGRESS_UI (window-metadata-based, outcome-correct here) |
| Weak/existence-based | GOAL_CORRECTNESS, HOST_COMPUTATION, OUTPUT_PRESENTATION, VISUAL_DESKTOP_ALIGNMENT (`>= 3` only) |
| Count-vacuous | CAUSAL_PROVENANCE (`> 0` on polluted counts) |
| Substring/weak | PLANNING_SEMANTICS, TOOL_DECISION_ALIGNMENT |
| **Hardcoded** | **RESOURCE_RESTORATION = literal PASS + fabricated evidence**; EDITOR_INTERACTION literal N/A; VISIBLE_TERMINAL inverted (`0 terminals → N/A`, `>0 → PASS`) |
| **Predicate≠code** | D6 topmost never checked; D8 correlation never computed |
| **Aggregation** | L563: PARTIALs never prevent PASS (latent vacuous-PASS rule) |
| **Evidence-class laundering** | L602 stamps every row `DERIVED_FROM_FROZEN_EVIDENCE`; L583–589 canned narrative stamped as derived |

Mental mutation test: (a) delete all screenshots → VISUAL FAIL, UI FAILs hold → engine fails closed there; (b) a run with only PARTIAL verdicts → suggested **PASS** (vacuous); (c) `RESOURCE_RESTORATION` passes with zero evidence by construction; (d) any stray terminal window → VISIBLE_TERMINAL flips to PASS.

## 15. F0-25D.1 failure regression (§18)

| # | F0-25D.1 failure | Status | Notes |
|---|---|---|---|
| A | Mislabeled screenshots | **FIXED** | Neutral names; UI-audit fields match pixels 15/15. Residue: `world_frames` stage_hints still assert unobserved states (LAUNCHER_OPEN etc.) |
| B | Hardcoded UI PASS | **PARTIALLY_FIXED** | UI PASSes eliminated; **hardcoded RESOURCE_RESTORATION PASS survives**; literal capability-audit/NC values; unconditional DERIVED stamp |
| C | Evaluator re-running main.py | **FIXED** | No subprocess in evaluator; oracle parse-only (verified) |
| D | Editor PASS with no editor | **FIXED** | Outcome NOT_APPLICABLE (mechanism still hardcoded — noted) |
| E | Hidden host exec reported as visible terminal | **FIXED** | No terminal PASS; inverted-predicate smell recorded |
| F | File existence as semantic correctness | **PARTIALLY_FIXED** | RESULT_CORRECTNESS now a real oracle; GOAL/HOST/OUTPUT still existence-based |
| G | Missing causal provenance accepted as complete | **PARTIALLY_FIXED** | Counts gate added but accepts polluted counts; linkage and 3 chain stages unverified/canned |

## 16. Product maturity, independently classified (§20)

| Tier | Classification | Basis |
|---|---|---|
| Backend autonomous task executor | **PROVEN** | Request → governed dispatch → model synthesis → sandbox execution → hash-matched delivery, all evidenced |
| Background software agent | **SUPPORTED** | Runs resident, retries verification, delivers without human input |
| Observable desktop agent | **FAILED** | Zero visible UI across 15 frames; self-log contradicts screen |
| Interactive computer-use agent | **FAILED** | No demonstrable on-screen interaction or progress surface |
| Dogfood-ready workstation agent | **NOT READY** | Presentation, observability, and honest-evaluator gaps remain |

These tiers do not collapse: **backend execution is proven while visible workstation operation fails.**

---

## 17. Final questions (§22)

1. **Did Astra itself create the requested artifacts?** **YES — PROVEN** (model synth hash = delivery hash = frozen hash; baseline empty; observer structurally incapable).
2. **Did the observer remain non-causal after request submission?** **YES — SUPPORTED** by exhaustive source audit (no inputs, no IPC, no execution, no artifact writes post-guard; NC adds only weak support).
3. **Did the local model materially cause the workflow?** **PARTIALLY — SUPPORTED for content** (Qwen produced the executed code, hash-proven); **UNVERIFIED for the decision** (no frozen planner model events).
4. **Did consequential actions pass through governance?** **SUPPORTED at dispatch/delivery** (execute + 3 deliveries in-window via registry/broker); authorization verdicts (ALLOW/BLOCK) not frozen.
5. **Is the result mathematically correct?** **YES — PROVEN** by independent recomputation.
6. **Did Astra visibly operate the desktop?** **NO — CONTRADICTED** (0/15 frames; enumerator agrees).
7. **Was Astra's progress UI actually visible?** **NO** (0 HUD, 0 launcher frames; PARTIAL reclassified FAIL).
8. **Did Astra show the user the requested result?** **NO — FAIL** (no JSON/Explorer/terminal/summary/reveal of any kind).
9. **Did Astra restore its owned resources?** **UNVERIFIED** (claim hardcoded; sandbox retention is by-design; no proven leak, no proven measurement; harness left its child running at eval).
10. **Did F0-25E fix the dishonest evaluator problems of F0-25D.1?** **PARTIALLY** — A/C/D/E fixed; B/F/G partial; a hardcoded PASS, vacuous aggregation, and evidence-class laundering survive.
11. **Is Astra ready for developer dogfooding today?** **NO.**

Known debt preserved as instructed: routing holdout remains **68/70 (97.14%)** — out of scope for this evidence-truth review.

---

**OVERALL VERDICT = FAIL**

Acceptable reduced claim: *The frozen evidence package is hash-consistent; the installed binary (independently hash-verified) autonomously produced a mathematically correct word-frequency deliverable set under the requested path via governed model-synthesis + sandbox delivery; the observer was source-proven non-causal after submission; and the package honestly reports that no Astra UI was ever visible.*

Not acceptable: `CAUSAL_PROVENANCE`/`PLANNING_SEMANTICS`/`OUTPUT_PRESENTATION`/`RESOURCE_RESTORATION` as PASS, `PROGRESS_UI` as PARTIAL, "launcher rendering visibly", "pure function over frozen evidence", "32 broker authorization events", the negative control as proof, or any claim of a visible/observable desktop agent.

**MIMO F0-25E REVIEW COMPLETE**

**STOP**

---
*Supporting artifacts: `MIMO_F0_25E_ACCEPTANCE_MATRIX.json`, `MIMO_F0_25E_SCREENSHOT_AUDIT.json`, `MIMO_F0_25E_OBSERVER_AUDIT.json`, `MIMO_F0_25E_NEGATIVE_CONTROL_AUDIT.json`, `MIMO_F0_25E_CAUSAL_CHAIN.json`, `MIMO_F0_25E_MODEL_PROVENANCE.json`, `MIMO_F0_25E_BROKER_PROVENANCE.json`, `MIMO_F0_25E_CONTENT_ORACLE.json`, `MIMO_F0_25E_RESOURCE_AUDIT.json`, `MIMO_F0_25E_CONTRADICTIONS.json`.*
