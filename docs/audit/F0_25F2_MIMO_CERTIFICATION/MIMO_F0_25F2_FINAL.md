# MIMO F0-25F.2 — Independent Pre-Dogfood Certification

**Auditor**: MiMo (independent adversarial certification authority)
**Date**: 2026-10-12
**Subject**: F0-25F.1 "SEMANTIC TRUTH CLOSURE = PASS"
**Frozen subject**: branch `agent/anti-f0-24a1` @ `bd287eba…`, 242 dirty entries (pre-existing + F0-25F.1 uncommitted work); binary `444b6679…` (12,090,828 B) built ≡ installed (FACT)
**Mode**: no production edits; no rebuild; no commit; existing tests executed as permitted

---

## OVERALL VERDICT

**FAIL — NOT READY FOR F0-25G HUMAN BLIND DOGFOOD**

F0-25F.1 made substantial, independently confirmed repairs (presentation emission gate, disposal FAILED_CLEANUP, known routing failures fixed, honest screenshots, security manifest parity). It did **not** close the certification bar: production can still emit `GOAL_COMPLETED` without postconditions, unseen routing over-routes 26/105 prompts (including critical negatives), production code contains REPAIR-02 fixture contamination, and the celebrated factorial causal trace is **harness-fabricated** (stubbed broker, hardcoded “model” code).

## CONFIRMED REPAIRS
- `RESULT_PRESENTED` sole emitter gated on `target_observed && verified_hwnd` (`result_presentation.py:366`)
- Evaluator rejects REQUESTED-only presentation (`f0_25e_evaluator.py:424-430`)
- Old except-success presentation path removed
- Sandbox `CLOSED` gated on physical absence; `FAILED_CLEANUP` on residue (`resource_ledger.py:774-780`)
- REPAIR-02 semantic fail-closed (honest 7/8)
- Known routing failures (quadratic, login-summary) now `execute_dynamic_tool/LOCAL_MODEL`
- Security phantoms removed; 86/43/43/3/2/0 recomputed
- Binary identity `444b6679…` double-hashed
- Screenshots honest: launcher bar + factorial viewer with real content (visual FACT)
- Independent MiMo presentation run: non-hollow PRESENTED, correct event ordering, Explorer shows token file

## FAILED CLAIMS
| Claim | Reality |
|---|---|
| GOAL_COMPLETED only after postconditions | `telemetry.end_run` unconditional |
| 70/70 unseen holdout generalizes | Contaminated + 26 over-routes on MiMo 105 |
| routing fixed in laya.py | routing/ unchanged; fix in planner.py |
| 8-state presentation lifecycle | One boolean guard; 7 intermediate states not events |
| non-empty title required | Not in code/evaluator |
| 20/20 mutations prove integrity | ~11 genuine; several wrong-reason/gameable |
| Stage-13 causal chain production-faithful | Harness emits events; broker `executor_override` stub |
| source freeze covers final code | result_presentation.py & resource_ledger.py edited after freeze |
| production generic | REPAIR-02 strings in repair prompt; workspace paths in paths.py |

## UNVERIFIED CLAIMS
- Full 106-test regression (MiMo subset 35/35 only)
- Fresh independent MODEL+BROKER+ACTION end-to-end factorial-equivalent (not re-run)
- F0-25F.1 model_id authenticity (harness-stamped)

## NEW DEFECTS (this certification)
1. **Stage-13 causal fabrication** — verify script emits goal/plan/model/postcondition/completion events; broker stubbed
2. **Routing holdout contamination** — planner edited between manifest runs; all-positive set
3. **26 over-routes** on unseen set including “summarize hamlet plot”, “solve crossword”
4. **Summary-mode fabricated attestation** (`verified_title="AstraRun"` literals)
5. **Legacy stage-6 script still ORs REQUESTED with PRESENTED**
6. **Production REPAIR-02 prompt contamination**
7. **Workspace-specific venv/GGUF paths in production paths.py**
8. **Python path warning** embedded in “success” evidence (CPython getpath under restricted token)

## PYTHON PATH ANOMALY VERDICT
**REAL WARNING, NON-FATAL, EVIDENCE-CONTAMINATING** — emitted by `python313.dll` getpath, not Astra; execution continued via governed sandbox; oracles ignore warning lines.

## PRESENTATION VERDICT
**PRODUCT: PASS** (independent Explorer + factorial screenshot)  
**ORACLE: PARTIAL** (core gate real; residual bypasses)

## RESOURCE VERDICT
**DISPOSAL: PARTIAL** · **RESTORATION: PARTIAL**

## TELEMETRY VERDICT
**PARTIAL** — presentation chain honest; factorial chain not production-faithful; GOAL_COMPLETED ungated

## ROUTING
- historical 70: **70/70 recorded (tainted); both known failures FIXED (MiMo recheck)**
- Anti 60: **sample 10/10 dynamic (set all-positive / contaminated)**
- MiMo unseen 105: **dynamic 18/20; OVER-ROUTE 26 → FAIL generalization**

## GENERIC REPAIR HONEST SCORE
**7/8 with REPAIR-02 correctly failed** (strict semantic honesty ~5–6 due to residual weak oracles)

## MUTATION SCORE
**20/20 executed** · **~11/20 fully genuine**

## SECURITY RESULT
**PASS** — 86/43/43/3/2/0; phantoms gone

## REGRESSION RESULT
**PARTIAL** — 35/35 subset; 106 claim UNVERIFIED

## HARDCODING RESULT
**FAIL** — production fixture prompt + workspace paths + fabricated summary attestation

## DOGFOOD READINESS
**NOT READY**

| CLAIM | ANTI F0-25F.1 | MIMO F0-25F.2 | EVIDENCE | REASON |
|---|---|---|---|---|
| RESULT_PRESENTED gated | PASS | **PARTIAL** | L366 + legacy OR residual | Core gate real; identity incomplete |
| REQUESTED≠PRESENTED | PASS | **PARTIAL** | evaluator fixed; stage6 OR remains | Incomplete closure |
| hollow PRESENTED forbidden | PASS | **PARTIAL** | null hwnd closed; title hollow | Title unchecked |
| darkness purged | PASS | **PARTIAL** | contrast oracle weak | Any structured dark surface |
| disposal FAILED_CLEANUP | PASS | **PARTIAL** | L774-780 real; empty-path gap | Vacuous CLOSED possible |
| routing 70/70 | PASS | **PARTIAL/FAIL** | contaminated + 26 over-routes | Overfit |
| repair 7/8 semantic | PASS | **PARTIAL** | REPAIR-02 fail-closed real | Residual weak oracles |
| mutations 20/20 | PASS | **PARTIAL** | ~11 genuine | Wrong-reason kills |
| security 86/43/43/3/2/0 | PASS | **PASS** | MiMo recompute | Exact match |
| binary 444b6679 | PASS | **PASS** | double hash | Confirmed |
| physical presentation | PASS | **PASS** | screenshot + MiMo run | Visual FACT |
| causal chain production | PASS | **FAIL** | harness stub/fabrication | Not production-faithful |
| GOAL_COMPLETED gated | PASS | **FAIL** | end_run unconditional | No production gate |
| freeze covers source | PASS | **FAIL** | stale hashes | Edited after freeze |
| production generic | PASS | **FAIL** | REPAIR-02 prompt; paths | Contamination |
| dogfood ready | PASS (implied) | **NOT READY** | critical FAILs/UNVERIFIEDs | Certification bar unmet |

---

**NOT READY FOR F0-25G HUMAN BLIND DOGFOOD**

*Artifacts: `00_FREEZE.json` … `16_ACCEPTANCE_MATRIX.json`, `09A_MIMO_UNSEEN_ROUTING_HOLDOUT.json`, `13_TEST_RESULTS.txt`, `13_TEST_SUMMARY.json`, `screenshots/`.*
