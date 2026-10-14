# PHASE F0-25B.1 — SEMANTIC EVIDENCE CLOSURE: FINAL VERDICT

> **Scope**: `E:\Workspace\Agents\AstraRun-Anti`  
> **Phase**: `F0-25B.1`  
> **Status**: **PASS (CLOSED)**  
> **Target Environment**: Notepad++ (Win32 Scintilla Host)  
> **Authoritative Invariant**: *Model hypotheses must map to machine-checkable typed predicates, physical observations must match expected predicate schemas, and unverified transitions must never be promoted to Hermes knowledge or training candidate corpora.*  

---

## 1. Executive Summary & Forensic Root Cause Closure

Phase F0-25B successfully demonstrated local-model autonomous application learning and persistent Hermes knowledge graph retention. However, an independent forensic audit exposed three critical semantic verification contradictions:

1. **`SELECT_ALL` Tautology**: The test verifier checked `lambda pre, post: post["hwnd"] == pre["hwnd"]`. The state extraction observed no selection change (`pre_state_hash == post_state_hash`), yet the affordance was recorded as `VERIFIED` with `observed_delta: {length_changed: false}`.
2. **`NEW_DOCUMENT_TAB` Field Mismatch**: While tab counts physically increased, the persisted transition schema uniformly recorded `observed_delta: {length_changed: true}` from a hardcoded fallback line.
3. **`SEARCH_FIND_SURFACE` Field Mismatch**: While a Find dialog appeared, the persisted transition schema uniformly recorded `observed_delta: {length_changed: true}` rather than the dialog's HWND, PID, and class evidence.
4. **Hypothesis Polarity Contradiction (Cycle 5)**: The natural language hypothesis stated that an invalid action would result in *no state transition*, but the machine expectation requested `state_transition = true`.

In Phase F0-25B.1, all four defects have been completely resolved, verified with physical experiments, and enforced by an independent training-candidate quality gate.

---

## 2. Deliverables Checklist & Evidence Index

| Deliverable | Description | Status | Reference Artifact |
| :--- | :--- | :--- | :--- |
| **Contradiction Reproduction** | Full forensic audit of the 3 semantic discrepancies in F0-25B | **DONE** | [`F0_25B1_PRE_FIX_CONTRADICTIONS.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_PRE_FIX_CONTRADICTIONS.json) |
| **Hung-Probe Postmortem** | Termination, root-cause analysis, and fail-closed timeout protection | **DONE** | [`F0_25B1_HUNG_PROBE_POSTMORTEM.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_HUNG_PROBE_POSTMORTEM.json) |
| **Generic Selection Observer** | Multi-tier adapter (UIA TextPattern -> Win32 Edit -> Scintilla) | **DONE** | [`src/astrarun/computer_use/ui/editable_surface.py`](file:///E:/Workspace/Agents/AstraRun-Anti/src/astrarun/computer_use/ui/editable_surface.py#L498-L745) |
| **Selection Physical Verification** | Live physical proof of pre-check, Ctrl+A selection, and negative mutation | **DONE** | [`F0_25B1_SELECTION_OBSERVER_RESULTS.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_SELECTION_OBSERVER_RESULTS.json) |
| **Experiment Contract Model** | Machine-checkable contract with typed supported/refuted predicates | **DONE** | [`F0_25B1_HYPOTHESIS_CONSISTENCY.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_HYPOTHESIS_CONSISTENCY.json) |
| **Predicate-Typed Model** | Typed postcondition schemas for all 5 affordance categories | **DONE** | [`F0_25B1_PREDICATE_MODEL.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_PREDICATE_MODEL.json) |
| **Affordance Reverification** | Live physical re-run of 5 cycles with clean Hermes graph generation | **DONE** | [`F0_25B1_AFFORDANCE_REVERIFICATION.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_AFFORDANCE_REVERIFICATION.json) |
| **Quality Gate Mutations** | 10 adversarial mutants tested and 100% killed | **DONE** | [`F0_25B1_TRAINING_GATE_MUTATIONS.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_TRAINING_GATE_MUTATIONS.json) |
| **Data Reclassification** | Honest audit splitting candidates into passed vs quarantined | **DONE** | [`F0_25B1_REEVALUATED_TRAINING_CANDIDATES.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_REEVALUATED_TRAINING_CANDIDATES.json) |
| **Quarantined Trajectories** | 6 flawed F0-25B trajectories quarantined | **DONE** | [`F0_25B1_QUARANTINED_TRAJECTORIES.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_QUARANTINED_TRAJECTORIES.json) |
| **Memory Transfer Claim** | Rectified scientific comparison (probe reduction vs higher latency) | **DONE** | [`F0_25B1_MEMORY_TRANSFER_COMPARISON.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_MEMORY_TRANSFER_COMPARISON.json) |
| **Contamination Precision** | Explicit delineation of generic platform priors vs target cold start | **DONE** | [`F0_25B1_CONTAMINATION_PRECISION.json`](file:///E:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25B1_CONTAMINATION_PRECISION.json) |

---

## 3. Physical Reverification of Learned Affordances

All 4 learned Notepad++ affordances and the negative invariance experiment were re-run live against a clean Notepad++ process tree (PID 18392) using [`scripts/run_f0_25b1_affordance_reverification.py`](file:///E:/Workspace/Agents/AstraRun-Anti/scripts/run_f0_25b1_affordance_reverification.py).

| Cycle | Affordance | Predicate Type | Raw Evidence Reference | Observed Measurement | Gate Status |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **1** | `EDIT_TEXT` | `TEXT_BUFFER_DELTA` | `scintilla_wm_char_len_41` | Buffer length delta: +39 chars; is_dirty: True | **PASS** |
| **2** | `SELECT_ALL` | `SELECTION_RANGE_SPAN` | `scintilla_0x770cd4_start_0_end_39_doclen_39` | Selected: 39 chars; Doc: 39 chars; Start: 0; End: 39 | **PASS** |
| **3** | `NEW_DOCUMENT_TAB` | `DOCUMENT_TAB_COUNT` | `win32_wm_command_41001_file_new` | Pre-tabs: 1, Post-tabs: 2, Delta: +1 | **PASS** |
| **4** | `SEARCH_FIND_SURFACE` | `DIALOG_SURFACE_PRESENCE` | `win32_dialog_hwnd_0xe60c5e` | Dialog HWND: 0xe60c5e, Class: `#32770`, PID: 18392 | **PASS** |
| **5** | `UNMAPPED_BUTTON_CLICK` | `STATE_INVARIANCE` | `invariance_state_transition_False` | State transition occurred: False; Hypothesis: SUPPORTED | **PASS** |

Target PID 18392 cleanly exited upon conclusion; 0 lingering processes or HWNDs remained.

---

## 4. Adversarial Mutation Suite Results

The independent [`TrainingQualityGate`](file:///E:/Workspace/Agents/AstraRun-Anti/src/astrarun/hermes/training_gate.py) was tested against 10 adversarial failure modes in [`tests/hermes/test_training_gate_mutations.py`](file:///E:/Workspace/Agents/AstraRun-Anti/tests/hermes/test_training_gate_mutations.py):

* **Mutant 1** (Ctrl+A dispatched but selection range 0): **KILLED** (`TAUTOLOGICAL_SELECTION`)
* **Mutant 2** (Ctrl+N dispatched but tab count delta 0): **KILLED** (`TAB_COUNT_UNCHANGED`)
* **Mutant 3** (Ctrl+F dispatched but dialog not found): **KILLED** (`UNATTACHED_OR_WRONG_DIALOG`)
* **Mutant 4** (Unrelated dialog from wrong PID): **KILLED** (`UNATTACHED_OR_WRONG_DIALOG`)
* **Mutant 5** (Unrelated tab closure delta): **KILLED** (`TAB_COUNT_UNCHANGED`)
* **Mutant 6** (Irrelevant hash mutation without tab fields): **KILLED** (`PREDICATE_TYPE_MISMATCH`)
* **Mutant 7** (Hypothesis says false while predicate expects true): **KILLED** (`POLARITY_CONTRADICTION`)
* **Mutant 8** (Selection expected but observed delta has length_changed): **KILLED** (`PREDICATE_TYPE_MISMATCH`)
* **Mutant 9** (transition_verified forced true while evaluation failed): **KILLED** (`FORCED_VERIFICATION`)
* **Mutant 10** (Candidate claims VERIFIED Hermes knowledge with missing evidence): **KILLED** (`INVALID_HERMES_PROVENANCE`)

**Mutation Kill Rate: 10/10 (100.0%)**.

---

## 5. Candidate Reclassification Breakdown

Legacy F0-25B candidate data was audited against the new quality gate:

* **Legacy Passed**: 1 candidate (`traj_cold_001` - EDIT_TEXT).
* **Legacy Quarantined**: 6 candidates:
  * `traj_cold_002` (Quarantined: Selection was unobservable, `pre_state_hash == post_state_hash`).
  * `traj_cold_003` (Quarantined: Hermes transition schema mismatch; observed delta lacked tab count).
  * `traj_cold_004` (Quarantined: Hermes transition schema mismatch; observed delta lacked dialog identity).
  * `traj_warm_001` (Quarantined: Lacked raw empirical delta reference).
  * `traj_warm_002` (Quarantined: Lacked raw empirical delta reference).
  * `traj_adapt_001` (Quarantined: Lacked raw empirical delta reference).
* **F0-25B.1 Re-verified Candidates Promoted**: 4 candidates (`traj_f025b1_reverif_001` through `004`).
* **Total Clean Training Candidates in Corpus**: **5**.

---

## 6. Scientific Claim Rectifications

1. **Warm vs. Control Transfer**:
   * *What was proven*: Hermes memory retrieval eliminated exploratory probes (from 1 down to 0) and directly shifted model decision mode to `ACT`.
   * *What was refuted*: Lower wall-clock latency is **NOT** claimed. Warm execution took 7.53s vs. 2.75s for control, due to prompt token expansion from memory graph grounding.
2. **Contamination Scope**:
   * *Authoritative wording*: **"Zero Notepad++-scoped procedural Hermes knowledge at cold start."**
   * *Disaggregation*: AstraRun possesses generic desktop editing primitives (shortcuts, Save-As dialog finders, Scintilla message adapters). However, the model prompt received zero application-specific shortcuts or recipes, and Hermes started with zero Notepad++ entities or affordances.

---

## 7. Pass Condition & Final Question

All nine pass conditions from Section 11 are satisfied:
1. Every verified affordance has predicate-specific physical evidence.
2. Expected and observed predicates match semantically.
3. Hypothesis polarity is machine-consistent.
4. Hermes cannot promote mismatched evidence.
5. The training gate independently catches all semantic contradictions.
6. Existing trajectories have been honestly reclassified and quarantined where deficient.
7. Warm vs. control claims accurately reflect measured latency numbers.
8. The cold-start contamination claim distinguishes generic platform capabilities from target-scoped memory.
9. All 30 unit and regression tests (including causal ownership and resource reconciler invariants) pass.

### Final Question Answer:
> **"Can these trajectories now safely become candidates for future weight training?"**

**YES** — For the 5 strictly re-evaluated and reverified trajectories possessing verified physical predicate evidence. The 6 unverified legacy trajectories remain quarantined.
