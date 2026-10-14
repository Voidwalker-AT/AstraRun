# F0-25A.3 Causal Attribution Hardening — Final Verdict

**Date**: 2026-10-11  
**Phase**: F0-25A.3  
**Status**: COMPLETE / PASS  
**Branch**: `agent/anti-f0-24a1`  
**Worktree**: `E:\Workspace\Agents\AstraRun-Anti`  

---

## 1. Executive Answer to the Central Question

> **Question**: *"Can Astra distinguish something that merely appeared while it was acting from something its action actually caused?"*
>
> **Answer**: **YES**.
>
> **Direct Physical Evidence**:  
> In the live Windows physical adversarial concurrency test ([`docs/audit/F0_25A3_CONCURRENT_RESOURCE_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_CONCURRENT_RESOURCE_RESULTS.json)), Astra executed a governed launch of Character Map (`charmap.exe`, PID 10468). Simultaneously during the action observation window, an unrequested independent process (PID 15904) was spawned by the environment.  
> Both processes appeared in the post-action world delta (`NEW_TO_WORLD`).  
> 
> Astra's hardened causal engine evaluated:
> 1. `process:10468` (Character Map) $\rightarrow$ **`TASK_CREATED`** (`DIRECT_GOVERNED_LAUNCH`, disposition: `CLOSE`).
> 2. `process:15904` (Independent process) $\rightarrow$ **`EXTERNAL_CONCURRENT`** (`EXTERNAL_CONCURRENT`, disposition: `PRESERVE`).
>
> During Astra lifecycle cleanup:
> - Astra-created Character Map (PID 10468) was **terminated** (`alive_after_astra_cleanup = false`).
> - Unrelated concurrent process (PID 15904) **survived completely untouched** (`alive_after_astra_cleanup = true`).
> - Final world-state oracle verified `world_state_ok = true`, verdict `PASS`.

---

## 2. Reproduction of the F0-25A.2 Contradiction (Scenario A, Vivaldi PID 13304)

- **Artifact**: [`docs/audit/F0_25A3_FALSE_CAUSAL_ATTRIBUTION_REPRODUCTION.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_FALSE_CAUSAL_ATTRIBUTION_REPRODUCTION.json)
- **Defect Identified**: In F0-25A.2 ([`F0_25A2_NESTED_RESOURCE_RESULTS.json`](file:///E:/Workspace/Agents/AstraRun-MiMo/docs/audit/F0_25A2_NESTED_RESOURCE_RESULTS.json)), action `open_charmap_a` executed `charmap.exe` (PID 6332). During the 1.0s observation interval, an unrelated user browser worker process (`vivaldi.exe`, PID 13304) spawned concurrently.
- **Root Cause**: The reconciler implemented:
  $$\text{if } key \in \text{action\_delta\_new\_keys} \implies \text{TASK\_CREATED}$$
  Conflating temporal delta with causal ownership caused Vivaldi PID 13304 to be classified `TASK_CREATED` with evidence:
  `"identity process:13304 absent at pre-action frame and present after action; action=open_charmap_a"`, and targeted for termination (`cleanup_action = terminate_task_owned_process`).
- **Factual Reality**: Astra had zero interaction with Vivaldi; ExecutionBroker executed only `charmap.exe`.
- **Verdict**: Astra **did not** launch Vivaldi. Temporal correlation was incorrectly substituted for causal attribution.

---

## 3. Formalized Causal Provenance Architecture

- **Artifact**: [`docs/audit/F0_25A3_CAUSAL_PROVENANCE_MODEL.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_CAUSAL_PROVENANCE_MODEL.json)
- **Module**: [`src/astrarun/hermes/resource_lifecycle.py`](file:///e:/Workspace/Agents/AstraRun-Anti/src/astrarun/hermes/resource_lifecycle.py)
- **Classification Taxonomy**:
  1. `NEW_TO_WORLD`: Pure observational delta (`is_new_to_world = True`). Confers zero ownership.
  2. `TASK_CREATED`: Affirmatively created by governed Astra action (e.g. direct `Popen.pid` return).
  3. `TASK_DESCENDANT`: Proven child/descendant via OS process tree (`psutil.Process.ppid()` ancestry chain).
  4. `PRE_EXISTING_USER`: Present in pre-task baseline. Strictly preserved.
  5. `EXTERNAL_CONCURRENT`: Spawned during action window by user or OS. Strictly preserved.
  6. `UNKNOWN`: Unattributable entities. Strictly safe: **NEVER** closed, terminated, or deleted.
- **Resource Layer Separation**:
  $$\text{observed\_resources} \supset \text{new\_resources} \supset \text{causally\_attributed} \supset \text{task\_owned} \supset \text{disposable}$$
- **Safety Invariant**: Only `TASK_CREATED` and `TASK_DESCENDANT` resources with goal state `disposable` can receive `LifecycleDisposition.CLOSE`. `UNKNOWN`, `EXTERNAL_CONCURRENT`, and `PRE_EXISTING_USER` are strictly `LifecycleDisposition.PRESERVE`.

---

## 4. Machine-Readable Evidence Matrix

| Evidence Requirement | Machine-Readable Artifact | Physical / Test Method | Result |
| :--- | :--- | :--- | :--- |
| **False Attribution Reproduction** | [`F0_25A3_FALSE_CAUSAL_ATTRIBUTION_REPRODUCTION.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_FALSE_CAUSAL_ATTRIBUTION_REPRODUCTION.json) | Forensics on Scenario A Vivaldi PID 13304 | Defect isolated & proven |
| **Causal Provenance Model** | [`F0_25A3_CAUSAL_PROVENANCE_MODEL.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_CAUSAL_PROVENANCE_MODEL.json) | Formal taxonomy & affirmative rules A–H | Verified & implemented |
| **Adversarial Concurrency** | [`F0_25A3_CONCURRENT_RESOURCE_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_CONCURRENT_RESOURCE_RESULTS.json) | Live Windows Character Map + unrequested worker | Task app closed; Concurrent PID alive |
| **Child Process Ancestry** | [`F0_25A3_CHILD_PROCESS_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_CHILD_PROCESS_RESULTS.json) | Launcher spawning worker + independent sibling | Parent & Child closed; Sibling alive |
| **Structural Child Ownership** | [`F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json) | Dual identical `charmap.exe` instances + UIA docs | Window A doc closed; Window B doc alive |
| **Synthetic Evidence Audit** | [`F0_25A3_SYNTHETIC_EVIDENCE_AUDIT.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_SYNTHETIC_EVIDENCE_AUDIT.json) | Audit of `synth_child_e` in `scripts/f0_25a2_physical_scenarios.py` | Quarantined to `UNIT_SYNTHETIC` |
| **Completion Semantics Audit** | [`F0_25A3_COMPLETION_SEMANTICS_AUDIT.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_COMPLETION_SEMANTICS_AUDIT.json) | Audit of `completed=true, final_verified=false` contradiction | Reconciled single truth contract |
| **Mutation Test Suite** | [`F0_25A3_MUTATION_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_MUTATION_RESULTS.json) | 12 mutants violating causal invariants | **12 / 12 killed (100%)** |
| **Final World State** | [`F0_25A3_FINAL_WORLD_STATE.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_FINAL_WORLD_STATE.json) | Live OS process & window scan post-execution | 0 residual debris (`PASS`) |

---

## 5. Audit of All 12 Acceptance Criteria

1. **Temporal coincidence cannot create ownership**: **PASS**  
   Proven in [`F0_25A3_CAUSAL_PROVENANCE_MODEL.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_CAUSAL_PROVENANCE_MODEL.json) and verified via mutation test `test_oracle_kills_mutant_temporal_equals_ownership`.
2. **Unrelated concurrent resources survive Astra cleanup**: **PASS**  
   Physically verified on live Windows desktop in [`F0_25A3_CONCURRENT_RESOURCE_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_CONCURRENT_RESOURCE_RESULTS.json) (concurrent PID 15904 survived cleanup).
3. **Actual task resources are still identified**: **PASS**  
   Physically verified: Character Map PID 10468 affirmatively identified via direct launch PID and cleaned up.
4. **Actual task descendants are identified**: **PASS**  
   Physically verified in [`F0_25A3_CHILD_PROCESS_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_CHILD_PROCESS_RESULTS.json): Child PID 16484 traced via PPID ancestry and disposed with parent.
5. **Nested structural resources inherit only through proven causal parents**: **PASS**  
   Physically verified in [`F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json): Child under Window A inherited `TASK_CREATED`, child under Window B remained `EXTERNAL_CONCURRENT`.
6. **Unknown resources are never disposed**: **PASS**  
   Enforced in `src/astrarun/hermes/resource_lifecycle.py` and verified via mutation test `test_oracle_kills_mutant_unknown_disposal`.
7. **Synthetic evidence is not represented as physical evidence**: **PASS**  
   Forensically documented in [`F0_25A3_SYNTHETIC_EVIDENCE_AUDIT.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_SYNTHETIC_EVIDENCE_AUDIT.json). All physical tests executed exclusively with live Win32/OS entities.
8. **Completion truth is unambiguous**: **PASS**  
   Single authoritative completion contract formalized in [`F0_25A3_COMPLETION_SEMANTICS_AUDIT.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_COMPLETION_SEMANTICS_AUDIT.json). `completed` requires verified goal postconditions AND verified lifecycle cleanup.
9. **No title/brand ownership hacks exist**: **PASS**  
   Physically demonstrated using dual identical instances of `charmap.exe` in [`F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json) with zero string or title checks.
10. **Final physical world is clean**: **PASS**  
    Verified in [`F0_25A3_FINAL_WORLD_STATE.json`](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_FINAL_WORLD_STATE.json): 0 orphaned test processes or lingering windows.
11. **Previous F0-24A.1 oracle remains green**: **PASS**  
    43/43 F0-24A.1 oracle and mutation tests pass (`tests/eval_v1/test_f0_24a1_adversarial_oracle.py`, `tests/eval_v1/test_f0_24a1_oracle_mutations.py`).
12. **F0-25 causal intelligence remains functional**: **PASS**  
    All Hermes experiential memory tests pass (`tests/hermes/test_hermes_experiential_memory.py`), total 59/59 combined suite PASS.

---

## 6. Final Status & Directive Adherence

- **Status**: **COMPLETE / PASS**
- **Git State**: Zero unrequested commits; working tree clean and ready.
- **Directive**: STOP after F0-25A.3. Do not begin F0-25B.
