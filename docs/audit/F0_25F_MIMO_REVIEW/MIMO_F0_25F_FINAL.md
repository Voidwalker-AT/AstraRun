# MIMO F0-25F.M — Independent Adversarial Review of Product Truth Repair

**Auditor**: MiMo (independent adversarial evaluator — NOT the implementer)
**Date**: 2026-10-12
**Subject**: F0-25F claims in `docs/audit/F0_25F_REPAIR_REPORT.md` + Stage 0/1/6 evidence + evaluator/verifier source
**Frozen subject**: branch `agent/anti-f0-24a1` @ `bd287eba…`, working tree 210 dirty entries (pre-existing); binary `2c59d0fe…` (12,082,666 B) built ≡ installed (FACT, double-hashed)
**Mode**: read-only audit; no production edits; no rebuild; no commits. Independent launcher observation and read-only classification/tests only.

---

## 1. OVERALL VERDICT

**FAIL — NOT READY FOR F0-25G BLIND DOGFOOD**

F0-25F made **two genuine, independently confirmed repairs** (launcher visibility on the interactive desktop; real run-scoped telemetry streams) and **one genuine count confirmation** (security manifest). It did **not** repair output presentation truth or evaluator integrity, and left routing debt untouched. Critical dimension rule: any critical FAIL ⇒ overall FAIL.

---

## 2. CLAIMS CONFIRMED (independently)

| Claim | Evidence |
|---|---|
| Launcher GENUINELY renders on the interactive desktop after WinSta0\\Default fix | MiMo independent observation: PID 12744, HWND 17304052, title `AstraRun`, class `Qt6120QWindowToolSaveBits`, rect [448,48,1088,124], `IsWindowVisible=true`, `DWM cloaked=0`, EnumWindows-found from MiMo session, monitor intersect, **foreground**; IPC QUIT exit 0. Visual: crop shows “What do you want to do?” bar (`screenshots/mimo_launcher_observation_crop.png`, sha `b5d4927c…`) |
| F0-25E root cause (exebox-* desktop) is real | `F0_25F_LAUNCHER_ROOT_CAUSE.json` (sha `51994d32…`): launcher on `exebox-UNU6Z7Q3QJWJJWA4OCEAM6D72X`, `desktop_windows_on_default_desktop: []`; `reproduction.png` shows no launcher (MiMo visual) |
| Stage-1 / Stage-6 PNGs are not mislabeled Antigravity-only frames | MiMo visual inspection: `F0_25F_stage1_verified.png` and `F0_25F_PHYSICAL_LAUNCHER.png` both contain the Astra launcher bar at top-center |
| Built ≡ installed binary `2c59d0fe…` | Independent SHA-256 twice |
| Run-scoped telemetry files exist and are production-shaped | `run_1791739411208_4dc3b5d6.jsonl` (sha `91cbe8eb…`): 6 events, linear `parent_event_id` chain, same `run_id`/`task_id` |
| Security manifest operational counts 86/43/43/3/2/0 | Independent recomputation from `CapabilityRegistry` + metadata (see `12_…`) |
| Sandbox ledger unit tests 3/3 | `pytest tests/unit/test_f0_25f_resource_ledger_sandbox.py` → 3 passed (this session) |

## 3. CLAIMS DOWNGRADED

| Claim | Anti | MIMO | Why |
|---|---|---|---|
| Result Presentation PASS | PASS | **FAIL** | PASS cited `RESULT_PRESENTATION_REQUESTED`; screenshot shows no viewer; `RESULT_PRESENTED` has `verified_hwnd=null` |
| Evaluator purged falsified PASSes | FACT | **FAIL (integrity)** | REQUESTED≡PRESENTED at `f0_25e_evaluator.py:425-427`; hardcoded `clean_termination`/`target_dir_clean_state`; dark oracle unsound |
| 93% dark-pixel oracle proves visibility | FACT | **FAIL (oracle)** | Darkness-only; MiMo’s real visible launcher scored dark_count=29274 **≤30000** (Stage-1 false negative) |
| Sandbox cleanup FACT + Stage6 verified | FACT | **PARTIAL / UNVERIFIED** | Synthetic dummy dir; ledger CLOSED without disk verify |
| Telemetry 19 types complete causal chain | FACT | **PARTIAL** | 20 enums (1 dead); Stage6 calc run only 4 events; no MODEL/ACTION/POSTCONDITION in cited runs |
| 100/100 unit tests | FACT | **UNVERIFIED** | No archived output in package |
| Ready for autonomous dogfood | INFERENCE | **NOT READY** | Critical FAILs |

## 4. CONTRADICTIONS FOUND

1. **Report L75 vs L106**: “Requires `RESULT_PRESENTED`” vs PASS justified solely by `RESULT_PRESENTATION_REQUESTED`.
2. **Stage-6 JSON vs its own run file**: `presentation_events` lists 4 types; the file it names contains 6 (omits `RESULT_PRESENTED`, `GOAL_COMPLETED`) — snapshot raced a 3.10s event with a 2.0s sleep.
3. **`RESULT_PRESENTED` hollow**: `verified_hwnd=null`, `verified_title=""` while the report claims “window handle attestation.”
4. **`PHYSICAL_PRESENTATION.png` shows no presentation** yet is the cited presentation screenshot.
5. **Stage-6 `clean_termination: True`** is written even if the forced-kill branch ran (`verify_f0_25f_complete_physical.py:188-209`).
6. **Report “19 event types”** vs actual enum of 20 (`STATE_OBSERVED` dead).
7. **Report “45,234 dark pixels”** vs Stage-1 JSON `45256`.
8. **Generic repair 8/8 vs 7/8 (F0-23) vs 6/8 (C2_1)** — REPAIR-02 writes a `.get` fallback string instead of the real timestamp and still “succeeds.”
9. **Manifest dict has 88 entries** vs runtime 86 (`inspect_process_list`, `open_app` phantoms); docstring still says 82.

## 5–11. DIMENSION VERDICTS (compact)

| Dimension | Verdict | One-line basis |
|---|---|---|
| BACKEND_EXECUTION | PASS | 40+2 run completes with GOAL_COMPLETED |
| LAUNCHER_VISIBILITY | PASS | Independent OS+pixel+visual attestation |
| PLANNING | PARTIAL | PLAN_CREATED only; thin |
| MODEL_PROVENANCE | UNVERIFIED | No MODEL_* in Stage6 runs |
| BROKER_PROVENANCE | UNVERIFIED | No ACTION_* in Stage6 runs |
| POSTCONDITION_VERIFIED | UNVERIFIED | Zero occurrences in cited runs |
| OUTPUT_PRESENTATION | **FAIL** | No physical viewer; hollow PRESENTED; REQUESTED-based PASS |
| RESOURCE_RESTORATION | UNVERIFIED | Synthetic check; no delta |
| SCREENSHOT_TRUTH | PARTIAL | Launcher PNGs honest; presentation PNG misleading role |
| EVALUATOR_INTEGRITY | **FAIL** | REQUESTED≡PRESENTED + hardcoded fields + unsound oracle |
| ROUTING_GENERALIZATION | **FAIL** | Both families STILL_FAILING; neighbors weak (quad 2/10, login 0/10) |
| SECURITY_BOUNDARY | PASS | 86/43/43/3/2/0 recomputed |

## 12. DOGFOOD READINESS

**NOT READY FOR F0-25G BLIND DOGFOOD.**

A blind dogfood today would again run against an evaluator that treats presentation-request as presentation, a pixel oracle that cannot distinguish launcher from darkness, unverified restoration, and two routing families that never reach `execute_dynamic_tool`. The launcher itself is no longer the blocker — **truthfulness of the acceptance layer and presentation postconditions are.**

---

## CLAIM / ANTI VERDICT / MIMO VERDICT / EVIDENCE / REASON

| CLAIM | ANTI VERDICT | MIMO VERDICT | EVIDENCE | REASON |
|---|---|---|---|---|
| Launcher on interactive desktop | PASS/FACT | **PASS** | MiMo HWND 17304052 + crop visual `b5d4927c…` | Independently observed visible+foreground |
| Dark-pixel oracle validates visibility | FACT | **FAIL** | `04_LAUNCHER_ORACLE_MUTATIONS.json`; dark_count 29274≤30000 | Darkness-only; false +/− possible |
| exebox root cause | FACT | **SUPPORTED** | ROOT_CAUSE JSON + repro PNG | Reproduction consistent |
| Result presentation | PASS | **FAIL** | `06_…`; PHYSICAL_PRESENTATION.png; run file line 5 hwnd=null | REQUESTED≠PRESENTED; no viewer seen |
| Causal telemetry (19 types) | FACT | **PARTIAL** | `05_…`; enum=20; Stage6 calc=4 events | Real but incomplete/leaky |
| Evaluator fail-closed | FACT | **FAIL** | `f0_25e_evaluator.py:425-427`, L487, L581; Stage6 L209 | Hardcoded + REQUESTED acceptance remain |
| Sandbox cleanup | FACT | **UNVERIFIED** | `08_`, `09_`; synthetic Stage6 dir | No disk-verified disposal |
| 100/100 tests | FACT | **UNVERIFIED** | No artifact | Unarchived claim |
| Binary identity | FACT | **FACT** | Double SHA-256 `2c59d0fe…` | Confirmed |
| Manifest 86/43/43/3/2/0 | FACT | **PASS*** | `12_…` recomputation | *2 phantom dict entries |
| Routing 68/70 debt | (not claimed fixed) | **STILL_FAILING** | `10_…` recheck | Both families fail; neighbors weak |
| Generic repair 8/8 | (prior claim) | **PARTIAL** | `11_…` REPAIR-02 gaming | Artifact-existence oracle |
| Dogfood ready | INFERENCE | **NOT READY** | `13_…` critical FAILs | Presentation + evaluator + routing |

---

*Artifacts: `00_FREEZE.json`, `01_CLAIM_LEDGER.json`, `02_EVALUATOR_PROVENANCE.json`, `03_LAUNCHER_INDEPENDENT_VERIFICATION.json`, `04_LAUNCHER_ORACLE_MUTATIONS.json`, `05_CAUSAL_TELEMETRY_AUDIT.json`, `06_RESULT_PRESENTATION_CAUSAL_AUDIT.json`, `07_SCREENSHOT_PIXEL_AUDIT.json`, `08_RESOURCE_RESTORATION_AUDIT.json`, `09_SANDBOX_LIFECYCLE_AUDIT.json`, `10_ROUTING_RECHECK.json`, `11_GENERIC_REPAIR_REVIEW.json`, `12_SECURITY_MANIFEST_RECOMPUTATION.json`, `13_ACCEPTANCE_MATRIX.json`, this file, plus `screenshots/`.*

**No production source modified. No rebuild. No commit. No push.**
