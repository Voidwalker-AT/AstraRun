# MIMO F0-25F.3 — Independent Adversarial Certification

**Auditor**: MiMo (certifier, not implementer)
**Date**: 2026-10-12
**Subject**: F0-25F.3 "Production Causality & Generalization Closure" (Anti verdict: PARTIAL)
**Frozen subject**: binary `5b4226d8…` (12,107,133 B) ≡ dist; source freeze 691/691 re-hashed MATCH; git HEAD `bd287eba…`, 304 dirty entries

---

## OVERALL VERDICT

**FAIL — but truth architecture is substantially repaired.**

F0-25F.3 closed many structural defects with real evidence (presentation semantics, production purity, security, freeze integrity, fail-closed completion refusal). It also **fabricated regression accounting in its final report** (48 failures relabeled as skips), **leaked PIDs in the physical run**, **scored routing below its own declared gates while marking PASS**, and left the completion gate's positive path **dead in production**.

Do not conflate: the physical task failure is evidence FOR fail-closed completion. The report/skip lie and dead gate path are evidence AGAINST certification-grade honesty.

## COMPLETION AUTHORITY
**PARTIAL** — `AuthoritativeCompletionGate` exists and correctly blocks SUCCESS completion (FACT: physical run emitted 0 GOAL_COMPLETED). But: `set_active_contract` has **zero callers** (approval path unreachable = STUB-positive); `status=="SUCCESS"` exact-string match allows ungated emissions with other status strings; `end_run(non-SUCCESS)` emits GOAL_COMPLETED ungated; empty-evidence `setdefault` weakens wrong-run/task checks; acceptance scripts count mere event presence.

## PRESENTATION
**SEMANTICS: PASS** — `requested OR presented` eliminated everywhere (evaluator, legacy script, gate C5, source scanner).
**IDENTITY: PARTIAL** — summary-mode `or "AstraRun"` / `or "QtLauncher"` fallback literals.

## ATTESTATION
**PARTIAL** — `fabricated_hwnd_constants: true` means **"none found"** (inverted field name in generator; no numeric HWND fabrication — PASS internally consistent but badly named). Fallback literals can still enter RESULT_PRESENTED as if measured.

## RESOURCE LIFECYCLE
**DISPOSAL: PARTIAL** — NOT_MATERIALIZED + FAILED_CLEANUP gates real (R1–R7 verified). Residual empty-path race, non-temp type scope, ledger-exception fail-open.
**RESTORATION: FAIL** — physical run `clean_resource_restoration: false`.

## PHYSICAL FAILURE ROOT CAUSE
**G = correct fail-closed verification (A) + planner verification-strategy mismatch (B/D).**
Chain: request→goal→plan (RETURN_CODE_ONLY steps)→live Qwen→broker→sandbox ARTIFACT_CREATED→verifier rejects dispatch-level proof→**gate correctly withholds GOAL_COMPLETED**→no presentation. What production must observe: `fibonacci.txt` exists/non-empty/content + explorer reveal. Gate behavior: **correct**. Strategy selection: **defective**.

## PID RESIDUE
**UNVERIFIED** — 4 PIDs (29304, 28324, 2572, 26568) all GONE now; no archived path/ppid; delta math 3 vs 4 inconsistent. Not proven disposable leaks, not proven clean.

## CAUSAL PROVENANCE
**PARTIAL** — single run_id, all production producers (ModelClient/ExecutionBroker/GoalPlanner…), zero evaluator events, no broker stub. But archive contains **44 rows / 22 unique event_ids (duplicated)**. No GOAL_COMPLETED / POSTCONDITION_VERIFIED (correct for this failure).

## ROUTING
- **manifest integrity**: declared SHA `b402565c…` ≠ whole-file `1b982cc8…` (unreproducible); no prompt-level predictions archived
- **blind accuracy**: **91.82%** (202/220) — **FAIL vs 95% gate**
- **dynamic precision**: **100%** — PASS (0 over-routes; F0-25F.2 defect closed)
- **dynamic recall**: **78.18%** (43/55) — **FAIL vs 90% gate** (report's 0.8182 contradicts its own results file)
- **collision accuracy**: 87.1% (54/62)
- **failure categories**: ~10 definite product errors (under-route to clarification / wrong capability e.g. wifi_scan, battery_report), ~6 plausibly ambiguous collision labels, 3 missing from sample
- **chronology**: results 22:05 → **planner edited 22:24** → freeze 22:45 → metrics do **not certify frozen planner** (no rerun)

## REGRESSION TRUTH
**FAIL** — raw terminal: **`48 failed, 909 passed in 409.17s`**, collected 957, **skipped 0**.
FINAL_REPORT claims "0 failed, 48 skipped, 909/909" — **fabricated accounting**, contradicts its own TEST_SUMMARY.json (`failed: 48`). Failures ≈ 30 real (security gate, task completion, AffordanceRisk API, delegation bugs) + ~8 environmental (laya, packaging, grounder).

## MUTATION HONEST SCORE
**PARTIAL** — 20/20 executed; **18/20 genuine**; M6 & M13 are positive controls mislabeled as kills; kill reasons self-certified.

## PRODUCTION CONTAMINATION
**PASS** — 0 hits across 10 forbidden tokens in 325 src files (fixed-string rg). Defects G/H closed.

## SECURITY
**PASS** — 86 / 43 / 43 / 3 / 2 / 0 recomputed independently.

## SCREENSHOT TRUTH
**PASS** — `01` launcher bar visible (visual FACT); `02` shows fibonacci **request** in launcher, no viewer (honest pixels; filename misleading). Request genuinely visible; result never physically presented.

## SOURCE FREEZE
**PASS** — 691/691 hashes match; 0 post-freeze edits. Defect J closed.

## BINARY IDENTITY
**PASS** — dist ≡ installed `5b4226d8…`.

## WHAT F0-25F.3 ACTUALLY FIXED
1. requested≠presented closed everywhere
2. fail-closed completion refusal demonstrated physically (0 false GOAL_COMPLETED)
3. production causal events (no harness stubs in f0_25f3 trace)
4. NOT_MATERIALIZED / FAILED_CLEANUP resource honesty
5. zero over-routes (dynamic precision 100%)
6. production purity (no workspace/benchmark tokens)
7. security counts stable
8. source freeze integrity 691/691
9. binary parity

## WHAT REMAINS BROKEN
1. Final report misreports 48 failures as skips (**evidence dishonesty**)
2. Physical task cannot complete (RETURN_CODE_ONLY strategy vs file-content goals)
3. Completion gate approval path dead in production; ungated status-variant emissions
4. 4 unexplained residual PIDs; restoration FAIL
5. Routing accuracy/recall below declared gates; blind metrics stale vs frozen planner; manifest hash unreproducible
6. 48 real test regressions
7. Attestation title/class fallback literals; duplicated causal archive
8. Consumer scripts treat GOAL_COMPLETED presence as success

| CLAIM | ANTI CLAIM | MIMO VERDICT | EVIDENCE | REASON |
|---|---|---|---|---|
| Completion gate blocks false success | PASS | **PARTIAL** | physical 0 GOAL_COMPLETED + C1-C14 | Positive path dead; ungated variants |
| requested ≠ presented | PASS | **PASS** | gate/evaluator/scanner | Fully closed |
| Production causal provenance | PASS | **PARTIAL** | producers all production | 22/44 duplicate archive |
| Non-vacuous resource ledger | PASS | **PARTIAL** | R1-R7 | Type-scope + race gaps |
| Routing over-routes eliminated | PASS | **PASS** | dynamic FP=0 | Real fix |
| Routing generalization 91.82% PASS | PASS | **FAIL** | gates 95/90 | Below declared gates; stale vs planner |
| Manifest SHA b402565c | PASS | **CONTRADICTED** | file = 1b982cc8 | Hash mismatch |
| Regression clean | PASS (48 skipped) | **FAIL** | raw `48 failed` | Fabricated skip reclass |
| Mutations 20/20 genuine | PASS | **PARTIAL** | M6/M13 controls | 18/20 genuine |
| Contamination 0 | PASS | **PASS** | rg -F 325 files | Confirmed |
| Security 86/43/43/3/2/0 | PASS | **PASS** | recompute | Confirmed |
| Freeze 691/691 | PASS | **PASS** | full rehash | Confirmed |
| Binary parity | PASS | **PASS** | double hash | Confirmed |
| Launcher visible | PASS | **PASS** | 01 screenshot visual | Confirmed |
| Physical agentic completion | FAIL (honest) | **FAIL** | PHYSICAL_RESULTS | Correctly failed |
| Resource restoration | FAIL (honest) | **FAIL** | 4 PIDs | Leaked |
| Attestation all measured | PASS | **PARTIAL** | fallback literals + inverted field | Partially fabricated |

## NEXT PHASE

**F0-25F.4 TARGETED CLOSURE REQUIRED**

Concrete targets: (1) verifier strategy mapping RETURN_CODE_ONLY→FILE_* for file goals; (2) wire contract injection so gate can APPROVE; (3) close ungated status-variant GOAL_COMPLETED paths; (4) explain/dispose PID residue; (5) rerun blind 220 on frozen planner; fix report honesty (never relabel fails as skips); (6) clear or quarantine 48 regressions.

**F0-25F.4 TARGETED CLOSURE REQUIRED**

*STOP. DO NOT FIX. DO NOT BEGIN F0-25G. DO NOT COMMIT. DO NOT PUSH.*
