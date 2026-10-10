# F0-24A.1 — Adversarial Oracle & Execution-Truth Hardening Evidence Report

Branch: `agent/mimo-f0-24a1`  
Worktree: `E:\Workspace\Agents\AstraRun-MiMo`  
Evidence class of this report: `SOURCE_TREE_TEST` (except where noted)

---

## 0. Scope and isolation

| Claim | Evidence class | Command | Result |
|---|---|---|---|
| Work only on `agent/mimo-f0-24a1` | GIT | `git branch --show-current` | `agent/mimo-f0-24a1` |
| Preservation worktree untouched | GIT | `git -C E:\Workspace\Active\AstraRun status --short` | empty |
| Anti worktree untouched | GIT | `git -C E:\Workspace\Agents\AstraRun-Anti status --short` | empty |
| No commit performed | GIT | mission instruction | uncommitted working tree |

### Git status (final)

```
 M scripts/verify_f0_24a_evidence_closure.py
 M src/astrarun/agent/loop.py
 M src/astrarun/agent/verifier.py
 M src/astrarun/computer_use/desktop/lifecycle.py
 M src/astrarun/core/evidence.py
 M src/astrarun/evaluation/acceptance_model.py
 M src/astrarun/tasks/resource_ledger.py
 M tests/test_agent_runtime.py
?? docs/audit/F0_24A1_PRE_FIX_REPRODUCTION.json
?? scripts/repro_f0_24a1_false_completion.py
?? src/astrarun/evaluation/execution_truth.py
?? tests/eval_v1/test_f0_24a1_adversarial_oracle.py
?? tests/eval_v1/test_f0_24a1_oracle_mutations.py
```

`.venv/` is local and ignored.

### Diff stat

```
 scripts/verify_f0_24a_evidence_closure.py      |  17 +++
 src/astrarun/agent/loop.py                     |  78 ++++++++---
 src/astrarun/agent/verifier.py                 | 178 ++++++++++++++++++++++++-----
 src/astrarun/computer_use/desktop/lifecycle.py |  30 ++++-
 src/astrarun/core/evidence.py                  |  82 ++++++++++++-
 src/astrarun/evaluation/acceptance_model.py    |  86 ++++++++++++++--
 src/astrarun/tasks/resource_ledger.py          | 128 ++++++++++++++++++++++----
 tests/test_agent_runtime.py                    |  80 +++++++--
 8 files changed, 580 insertions(+), 99 deletions(-)
```

---

## 1. Reproduced false-completion mechanisms (pre-fix → post-fix)

Harness: `scripts/repro_f0_24a1_false_completion.py`  
Artifact: `docs/audit/F0_24A1_PRE_FIX_REPRODUCTION.json`

| ID | Contradiction | Pre-fix false completion | Post-fix false completion | Production fix |
|---|---|---|---|---|
| A | Typing failed but UI_ELEMENT_STATE PASS | **true** (path-dependent; also failed open on missing comtypes) | **false** | Removed keystroke-dispatch-as-text evidence in `StepVerifier` |
| B | 119/120 represented as 100% | **true** (misleading 100.0 when 0 false completions) | **killed_by_production_helper=true** | `summarize_case_outcomes` + `assert_pass_rate_not_fabricated` |
| C | process_cleaned_up=false + PASS_CLEAN | **true** | **false** | `evaluate_resource_cleanup` + `resource_cleanup_verdict` + evidence-closure gate |
| D | Planning/null contract as GOAL_COMPLETED | **true** | **false** | `GoalVerifier` requires contract + verified executed steps |
| E | Partial UI / FILE_EXISTS-only / RETURN_CODE_ONLY as completion | **true** | **false** | Document-objective strengthening + RETURN_CODE_ONLY dispatch-only |

### Raw mechanism traces (source)

| ID | Production/eval source that allowed the lie | Hardened behavior |
|---|---|---|
| A | `agent/verifier.py` UI_ELEMENT_STATE: `result.success` + `length>0` ⇒ `text_found=True` | Dispatch length recorded as evidence only; `verified` requires observed text |
| B | Harness reporting: equate `false_completion_rate_pct==0` with overall 100% while `passed_cases=119`, `total_cases=120` | Fraction always `passed/total`; fabrication raises violations |
| C | `acceptance_model.py` RESOURCE_CLEANUP: empty `resource_delta` ⇒ orphans=0 ⇒ PASS; `verify_f0_24a_evidence_closure.py` accepted `PASS_CLEAN` | Missing delta / `process_cleaned_up=false` / exception / never-executed ⇒ FAIL |
| D | `GoalVerifier.evaluate(None)` returned GOAL_COMPLETED; plan validation counted as execution | Null contract ⇒ GOAL_INCOMPLETE; no verified COMPLETED step ⇒ incomplete |
| E | RETURN_CODE_ONLY / FILE_EXISTS alone / content constraint without content predicate | Dispatch-only; PRODUCE_DOCUMENT requires non-empty + content when constrained |

---

## 2. Implemented acceptance stages

New module: `src/astrarun/evaluation/execution_truth.py`

Stages (ordered, evidence-gated):

1. `PLAN_VALID`
2. `ACTION_DISPATCHED`
3. `ACTION_SUCCEEDED`
4. `STATE_OBSERVED`
5. `POSTCONDITION_SATISFIED`
6. `RESOURCE_CLEANUP_VERIFIED`
7. `GOAL_COMPLETED`

`ExecutionTruthOracle.evaluate` fails closed if any prior stage is missing.  
`FormalAcceptanceOracle` embeds this chain and never upgrades dimensional FAIL to PASS.

---

## 3. Resource-lifecycle truth

| Claim | Evidence class | Command/test | Result |
|---|---|---|---|
| Cleanup report cannot claim clean with `process_cleaned_up=false` | SOURCE_TREE_TEST | adversarial `test_requested_app_remains_open_after_cleanup`; `test_cleanup_exception_blocks_pass_clean` | PASS |
| `close_owned_resource` returns False if process/window remains | SOURCE_TREE_TEST | `tests/unit/test_f0_15_resource_lifecycle.py` (7/7) | PASS |
| Agent loop does not mark COMPLETED when cleanup fails/raises | SOURCE | `src/astrarun/agent/loop.py` cleanup path | Implemented |
| `DesktopLifecycle.close_application` returns fail on unclean report | SOURCE | `src/astrarun/computer_use/desktop/lifecycle.py` | Implemented |
| Evidence closure rejects PASS_CLEAN with process_cleaned_up=false | SOURCE | `scripts/verify_f0_24a_evidence_closure.py` contradiction gate | Implemented |

User-owned resources: cleanup still skips `user_interacted` / `USER_TAKEOVER_DETACHED` / non-Astra resources.

---

## 4. Evidence-class anti-promotion

| Claim | Evidence class | Test | Result |
|---|---|---|---|
| `REAL_COMPUTER_USE` / `FROZEN_EXE` cannot be self-promoted without provenance | SOURCE_TREE_TEST | `test_evidence_class_cannot_self_promote` | PASS |
| Proper provenance (`physically_executed` + `runtime_artifact`) allows physical class | SOURCE_TREE_TEST | same | PASS |

Source: `src/astrarun/core/evidence.py` (`can_claim_evidence_class`, `EvidenceRecord` validator).

---

## 5. Adversarial suite (must fail unless true postconditions)

File: `tests/eval_v1/test_f0_24a1_adversarial_oracle.py`  
Count: **21 tests**  
Command:

```
.venv\Scripts\python -m pytest tests/eval_v1/test_f0_24a1_adversarial_oracle.py -q
```

Result: **21 passed**

Covered scenarios (all require FAILURE without full postconditions):

1. correct app opened, typing fails  
2. typing success in wrong application  
3. correct filename empty  
4. correct filename wrong content  
5. Save dialog without save completion  
6. wrong app identity  
7. requested app remains after cleanup  
8. unrelated pre-existing app closed  
9. plan validates, no action executes  
10. first step ok, later required step fails  
11. action success vs observed state disagree  
12. stale artifact from previous run  
13. stale observation freshness  
14. unexpected side effect despite goal success  
15. execution-truth stage incomplete  
16. cleanup exception blocks PASS_CLEAN  
17. null contract cannot complete  
18. RETURN_CODE_ONLY not completion  
19. 119/120 not reported as 100%  
20. evidence self-promotion rejected  
21. close-owned-resource vacuous process case (documented)

---

## 6. Mutation tests (weakened predicates must die)

File: `tests/eval_v1/test_f0_24a1_oracle_mutations.py`  
Count: **7 tests**  
Result: **7 passed**

| Mutation | Kill evidence |
|---|---|
| FILE_EXISTS instead of FILE_NON_EMPTY | strong non-empty predicate fails on 0-byte file |
| skip content verification | content predicate fails on wrong payload |
| ignore process cleanup | `evaluate_resource_cleanup(None/false)` unsatisfied |
| treat action dispatch as success | UI_ELEMENT_STATE remains unverified |
| accept wrong application identity | ENTITY_CORRECTNESS fails |
| fabricate 100% from 119/120 | `assert_pass_rate_not_fabricated` returns violations |
| RETURN_CODE_ONLY completion | verified=False |

---

## 7. Related regression

Command:

```
.venv\Scripts\python -m pytest tests/test_agent_runtime.py tests/eval_v1/test_f0_24a1_adversarial_oracle.py tests/eval_v1/test_f0_24a1_oracle_mutations.py tests/test_f0_21_adversarial_false_completion.py tests/unit/test_f0_15_resource_lifecycle.py scripts/test_f0_23_adversarial_oracle.py tests/unit/test_execution_broker.py -q
```

Raw result: **55 passed in ~16s**

Note: `test_successful_closed_loop` was updated to supply a real `FILE_NON_EMPTY` postcondition contract and a handler that writes the artifact. RETURN_CODE_ONLY-only completion is now explicitly rejected by `test_return_code_only_is_not_step_completion`.

---

## 8. Security boundary (ExecutionBroker / ActionGate)

| Claim | Evidence | Result |
|---|---|---|
| Agent ACT path still mediated by ExecutionBroker | `src/astrarun/agent/loop.py` ActionProposal → `execution_broker.execute` | Unchanged / preserved |
| No confirmation weakening | Diff does not touch ActionGate confirmation rules | Preserved |
| Generic computer-use bypass | Inspected loop/broker path | No new bypass introduced in this change set |

Limitation: broader dynamic-tool bypass audit remains outside this milestone’s minimal oracle-truth scope.

---

## 9. Generalization accounting

New helpers in `execution_truth.py`:

- `summarize_case_outcomes` → always reports `fraction` as `passed/total`, separates planning/execution/verification/cleanup  
- `assert_pass_rate_not_fabricated(passed, total, reported_pct)` → flags 100% claims when `passed < total`

Post-fix reproduction: 119/120 ⇒ `honest_pass_rate_pct=99.1667`, fabrication of 100.0 detected.

---

## 10. Evidence classification of this milestone

| Bucket | Items |
|---|---|
| **IMPLEMENTED** | `execution_truth.py`, verifier/acceptance/loop/ledger/lifecycle/evidence fixes, repro script, adversarial+mutation tests, evidence-closure gate |
| **SOURCE-TESTED** | 21 adversarial + 7 mutation + related 55-test set (see §5–7) |
| **SOURCE-TESTED (pre-fix reproduction)** | `F0_24A1_PRE_FIX_REPRODUCTION.json` |
| **PHYSICALLY EXECUTED** | **None claimed** for new physical Windows UI workflows |
| **FROZEN-EXECUTED** | **None** (no frozen binary built/tested in this worktree) |
| **UNVERIFIED** | Live Notepad/Notepad++ physical typing matrix under the new verifier (requires physical desktop session + comtypes/UIA) |

---

## 11. Limitations

1. UIA content observation on this host currently logs `No module named 'comtypes'`; UI_ELEMENT_STATE therefore fails closed (does not invent PASS). Installing UIA deps would allow positive physical text attestation.  
2. `FormalAcceptanceOracle` now requires non-empty ENTITY_CORRECTNESS and EXECUTION_REALITY evidence; historical generator scripts that emitted PASS with empty dimensions will correctly FAIL until they supply evidence.  
3. Multi-window shared-host process termination still preserves the process when other windows exist; post-close verification then reports `process_cleaned_up=false` rather than a false clean.  
4. No frozen-exe or full physical computer-use matrix was executed here.

---

## 12. Stop-condition checklist

1. Known false-completion mechanisms reproduced — **YES** (§1)  
2. Generic oracle fixes implemented — **YES** (§2–4)  
3. Adversarial tests pass for the correct reason — **YES** (§5)  
4. Mutation tests kill weakened predicates — **YES** (§6)  
5. Resource cleanup cannot falsely report success — **YES** (§3)  
6. Evidence classes cannot self-promote — **YES** (§4)  
7. No application-specific workaround — **YES** (generic strategies only)  
8. Isolated to this worktree — **YES** (§0)  
9. Raw evidence for major claims — **YES** (commands/results above)  
