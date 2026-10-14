# MIMO AU-0 — Independent Forensic Verification of Argon Findings

**Specimen**: `4a5b409d3a02586f4d3249fc7839601439900de8` (`review/f0-25f7-argon`) — HEAD verified equal
**Auditor**: MiMo · **Date**: 2026-10-14 · Read-only source forensics

---

## Verdict summary

| # | Finding | Verdict | Severity |
|---|---|---|---|
| 1 | Split-brain launcher vs AgentExecutionEngine | **CONFIRMED** | CRITICAL |
| 2 | LearnedSemanticRouter not learned + ModelRole NameError | **CONFIRMED** | HIGH |
| 3 | Blind 300/1000 exact-dup; hash validation cosmetic | **CONFIRMED** | CRITICAL |
| 4 | Hermes no planning influence; gates unwired | **CONFIRMED** | HIGH |
| 5 | Hermes literal pre_/post_ hashes; broker=verified | **CONFIRMED** | CRITICAL |
| 6 | Notepad++ learning harness-scripted | **CONFIRMED** | CRITICAL |
| 7 | Close kills unsaved (~1.5s claim wrong; behavior confirmed) | **PARTIALLY_CONFIRMED** | HIGH |
| 8 | PID discarded; any-new-window claim | **CONFIRMED** | CRITICAL |
| 9 | Confirmation card `action` / `{}` | **CONFIRMED** | CRITICAL |
| 10 | CONFIRM → REPLAN (invariant unreachable) | **CONFIRMED** | CRITICAL |
| 11 | executor_override | **PARTIALLY_CONFIRMED** | MEDIUM |
| 12 | Completion split UI vs gate | **CONFIRMED** | CRITICAL |
| 13 | Dead/unwired architecture | **CONFIRMED** | HIGH |
| 14 | Test/mock contamination | **PARTIALLY_CONFIRMED** | MEDIUM |
| 15 | Model fallback theater | **CONFIRMED** | HIGH |
| 16 | Perception stacks | **PARTIALLY_CONFIRMED** | MEDIUM |

**Tally**: 12 CONFIRMED · 4 PARTIAL · 0 CONTRADICTED · 0 UNVERIFIED

## Highlights (production evidence)

- **Split-brain**: only `app.py:846-856` (battery/wifi/non-builtin) reaches `AgentExecutionEngine`; open/close/file/window/multi-step use DeterministicRouter+TaskManager+WorkflowCompiler.
- **Router**: `learned_router.py` = regex + fixed confidences; `ModelRole` used at `planner.py:835` **never imported** → NameError on Tier-2 agent path.
- **Benchmark**: Dev 1500 ∩ Blind 1000 = **300 exact duplicates (30%)**; `verify_manifest_hash` computes SHA but never compares.
- **Hermes**: plan created before exploration; `hermes_exploration_outcome` unread; `TrainingQualityGate`/`TaskResourceReconciler` zero production callers; `transition_verified=broker.success` with literal `pre_/post_` hashes; 4 FPs → confidence VERIFIED.
- **Notepad++**: fixed experiment list, hardcoded WM_COMMAND IDs, harness replaces invalid model JSON, warm dispatch ignores model.
- **Close**: 2.0s→0.6s→3.0s→kill ladder (not 1.5s); prefers Don't Save; `UNSAVED_USER_CONTENT` unused; kill proceeds if dialog on other HWND.
- **PID**: `CreateProcessW` PID discarded; fallback claims **any** new titled window (`astra_created=True`).
- **Confirm**: UI `tool_name="action"`, `args={}`; resubmit → `SECURITY_DENY`; agent path drops token and REPLANs (`CONFIRM_REMAINS_CONFIRM` never fires).
- **executor_override**: registry-check bypass yes; default risk **HIGH** (not LOW); unknown still `UNKNOWN_CONSEQUENTIAL` deny; **no production callers**.
- **Completion**: `res.success=True` returned to UI while gate emits `RUN_TERMINATED completed=False`.

## Final decision

**ARGON CRITICAL FINDINGS SUBSTANTIALLY CONFIRMED — PROCEED TO AU-1 ARCHITECTURAL UNIFICATION**

Artifacts: `00_SPECIMEN.json` … `17_ARGON_FINDINGS_MATRIX.json` under `docs/audit/AU0_MIMO_ARGON_FORENSICS/`.
