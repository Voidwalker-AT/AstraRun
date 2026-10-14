# F0-25A.3R — Final Evidence Repair & Causal Attribution Audit Verdict

**Phase**: `F0-25A.3R` (Final Evidence Repair Only)  
**Authoritative Baseline**: `agent/anti-f0-24a1`  
**Execution Worktree**: `E:\Workspace\Agents\AstraRun-Anti`  
**Date**: October 11, 2026  
**Status**: COMPLETE / VERIFIED  

---

## 1. Executive Summary

Phase `F0-25A.3R` was convened with a strict, single objective: **close the two remaining evidence integrity defects in AstraRun's causal attribution subsystem without redesigning architecture, touching unrelated code, committing, or packaging**:

1. **Structural Child Physical Authenticity**: Forensically trace `document:6226884:doc_task_child_6226884`, reclassify synthetic harness tests as `SOURCE_INTEGRATION`, and execute a genuine physical structural-child test using live Microsoft UI Automation COM enumeration (`IUIAutomation::ElementFromHandle`).
2. **World Restoration Oracle Semantics**: Forensically audit why `total_active_windows = 0` was reported in `F0_25A3_FINAL_WORLD_STATE.json`, retire the naive "desktop is empty" assumption, and replace it with an ownership-relative world restoration contract:
   $$\text{world\_restored} = (\text{task\_owned\_remaining} == 0) \land (\text{harness\_owned\_remaining} == 0) \land (\text{baseline\_missing} == 0) \land (\text{external\_concurrent\_modified} == 0) \land (\text{unknown\_modified} == 0)$$
3. **Regression Integrity**: Verify that all 59/59 causal attribution, experiential memory, and adversarial execution oracle tests remain strictly green without weakening any oracle.

---

## 2. Investigation 1: Structural Child Physical Authenticity

### 2.1 Forensics of `document:6226884:doc_task_child_6226884`
- **Origin**: Traced directly to [scripts/run_f0_25a3_structural_ownership.py](file:///e:/Workspace/Agents/AstraRun-Anti/scripts/run_f0_25a3_structural_ownership.py#L87-L95):
  ```python
  doc_a_identity = ResourceIdentity(
      kind="document",
      pid=pid_a,
      hwnd=hwnd_a,
      parent_hwnd=hwnd_a,
      parent_pid=pid_a,
      uia_id=f"doc_task_child_{hwnd_a}",
      process_name="charmap.exe",
  )
  ```
- **Finding**: The `ResourceIdentity` object and UIA identifier string were manually constructed by the Python test harness rather than discovered through Windows UI Automation COM traversal.
- **Action**: [docs/audit/F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json) was reclassified from `PHYSICAL` to `SOURCE_INTEGRATION`. Synthetic test fixtures are strictly quarantined and never represented as physical runtime proof.

### 2.2 Live Windows UI Automation Physical Test
- **Implementation**: [scripts/run_f0_25a3r_real_uia_test.py](file:///e:/Workspace/Agents/AstraRun-Anti/scripts/run_f0_25a3r_real_uia_test.py).
- **Execution**: Governed launch of Task Window A (`charmap.exe`, PID 14232, Dialog HWND 20186768) alongside concurrent unrequested launch of External Window B (`charmap.exe`, PID 11128, Dialog HWND 7997278).
- **Live COM Enumeration**: Used `IUIAutomation::ElementFromHandle` to enumerate raw child controls on both live Win32 windows:
  * **Task Element A**:
    - `identity_source`: `"LIVE_WINDOWS_UIA"`
    - `owning_pid`: `14232`
    - `parent_hwnd`: `20186768`
    - `automation_id`: `"104"`
    - `control_type_id`: `50004` (`EDIT`)
    - `class_name`: `"RICHEDIT50W"`
    - `name_metadata`: `"Characters to copy :"`
    - `runtime_id`: `[42, 3344534]`
    - `bounds`: `[148, 398, 154, 26]`
    - `classified_ownership`: `TASK_CREATED` (`STRUCTURAL_CHILD`)
    - `disposition`: `CLOSE`
    - `cleanup_outcome`: `VERIFIED` (`parent_surface_closed`, alive after cleanup: `false`)
  * **External Element B**:
    - `identity_source`: `"LIVE_WINDOWS_UIA"`
    - `owning_pid`: `11128`
    - `parent_hwnd`: `7997278`
    - `automation_id`: `"104"`
    - `control_type_id`: `50004` (`EDIT`)
    - `class_name`: `"RICHEDIT50W"`
    - `name_metadata`: `"Characters to copy :"`
    - `runtime_id`: `[42, 7932262]`
    - `bounds`: `[148, 398, 154, 26]`
    - `classified_ownership`: `EXTERNAL_CONCURRENT` (`EXTERNAL_CONCURRENT`)
    - `disposition`: `PRESERVE`
    - `alive_after_astra_cleanup`: `true` (survived Astra cleanup untouched)
    - `harness_post_assertion_cleanup`: Disposed by harness (`HARNESS_OWNED`)
- **Evidence Artifact**: [docs/audit/F0_25A3R_REAL_UIA_STRUCTURAL_CHILD.json](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3R_REAL_UIA_STRUCTURAL_CHILD.json). Verdict: **PASS**.

---

## 3. Investigation 2: World Restoration Oracle Semantics

### 3.1 Forensics of `total_active_windows = 0`
- **Root Cause**: Win32 desktop station isolation.
  * Agent thread station: `WinSta0`
  * Agent thread desktop: `exebox-*` (e.g. `exebox-UPZPTPJLUFY43ZPXUTC2LCPD65`)
  * Per Microsoft Win32 API specifications, `EnumWindows` enumerates top-level windows belonging **strictly to the desktop associated with the calling thread**. It does not enumerate windows on other desktops.
  * In the agent's isolated execution sandbox desktop, there are zero pre-existing shell or explorer windows. The only windows that exist are those launched by processes within that desktop session.
  * When test-launched windows terminate, the window count on that desktop naturally returns to 0.
  * Concluding that the system is broken because window count is 0 is false; but reporting `desktop_clean: true` merely because window count is 0 is equally misleading.

### 3.2 Ownership-Relative Restoration Contract
The oracle now judges restoration relative to task and harness ownership:
$$\text{world\_restored} = (\text{task\_owned\_remaining} == 0) \land (\text{harness\_owned\_remaining} == 0) \land (\text{baseline\_missing} == 0) \land (\text{external\_concurrent\_modified} == 0) \land (\text{unknown\_modified} == 0)$$

- **Empirical Execution**: [scripts/verify_f0_25a3r_world_restoration.py](file:///e:/Workspace/Agents/AstraRun-Anti/scripts/verify_f0_25a3r_world_restoration.py).
- **Measured Metrics**:
  * `baseline_process_count`: 277
  * `baseline_window_count`: 0
  * `final_process_count`: 277
  * `final_window_count`: 0
  * `task_owned_identities_expected_disposed`: 9
  * `task_owned_identities_remaining`: 0
  * `harness_owned_identities_expected_disposed`: 1
  * `harness_owned_identities_remaining`: 0
  * `pre_existing_user_identities_unexpectedly_missing`: 0 (out of 98 tracked protected system and user processes)
  * `external_concurrent_identities_modified_or_disposed_by_astra`: 0
  * `unknown_identities_modified_or_disposed_by_astra`: 0
  * `world_restored`: `true`
  * `oracle_verdict`: `"PASS"`
- **Evidence Artifact**: [docs/audit/F0_25A3R_WORLD_RESTORATION.json](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3R_WORLD_RESTORATION.json).

---

## 4. Regression Matrix

Full automated test suite executed against local `.venv`:

| Test Suite | Tests Run | Result | Evidence Focus |
| :--- | :---: | :---: | :--- |
| `tests/hermes/test_f0_25a3_causal_mutations.py` | 9 | **PASS** | Kills mutants for temporal bias, same-title bias, unknown disposal, and missing provenance |
| `tests/hermes/test_hermes_experiential_memory.py` | 7 | **PASS** | Bayesian confidence, contradiction invalidation, epistemic uncertainty, poisoning rejection |
| `tests/eval_v1/test_f0_24a1_adversarial_oracle.py` | 36 | **PASS** | Fail-closed execution truth, content verification, postconditions, lifecycle accounting |
| `tests/eval_v1/test_f0_24a1_oracle_mutations.py` | 7 | **PASS** | Kills completion oracle bypasses, dispatch-as-success, return-code-only mutants |
| **Total** | **59** | **59/59 PASS** | **100% Green, Zero Weakened Criteria** |

---

## 5. Acceptance Checklist

- [x] **Structural physical evidence comes from authentic live UIA**: Proven via `IUIAutomation` COM traversal in `docs/audit/F0_25A3R_REAL_UIA_STRUCTURAL_CHILD.json` (`identity_source = "LIVE_WINDOWS_UIA"`).
- [x] **No synthetic ResourceIdentity is represented as PHYSICAL**: Proven via reclassification of `F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json` to `SOURCE_INTEGRATION`.
- [x] **World restoration is ownership-relative rather than "desktop empty"**: Proven via contract definition and execution in `docs/audit/F0_25A3R_WORLD_RESTORATION.json`.
- [x] **Task-owned residue = 0**: Verified (`task_owned_identities_remaining = 0`).
- [x] **Astra modified/disposed zero PRE_EXISTING_USER resources**: Verified (`pre_existing_user_identities_unexpectedly_missing = 0`).
- [x] **Astra modified/disposed zero EXTERNAL_CONCURRENT resources**: Verified (`external_concurrent_identities_modified_or_disposed_by_astra = 0`).
- [x] **Astra modified/disposed zero UNKNOWN resources**: Verified (`unknown_identities_modified_or_disposed_by_astra = 0`).
- [x] **Previous F0-25A.3 causal tests remain green**: 59/59 unit and mutation tests pass.

---

## 6. Final Authoritative Answer

**Is F0-25A now trustworthy enough to begin autonomous Notepad++ learning?**

### **YES**

**Evidence**:
1. **Physical UIA Grounding**: AstraRun possesses authentic Windows UI Automation COM discovery (`IUIAutomation::ElementFromHandle`) that extracts real Win32 controls (`automation_id="104"`, `class_name="RICHEDIT50W"`, `runtime_id=[42, 3344534]`, `bounds=[148, 398, 154, 26]`) without relying on synthetic mocks or window title heuristics ([F0_25A3R_REAL_UIA_STRUCTURAL_CHILD.json](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3R_REAL_UIA_STRUCTURAL_CHILD.json)).
2. **Causal Invariance Under Concurrency**: When identical applications (`charmap.exe` vs `charmap.exe`) run side-by-side with identical window titles, AstraRun attributes ownership strictly through affirmative launch handles and parent-child structural lineage. External and concurrent resources are classified `EXTERNAL_CONCURRENT` and protected from disposal ([F0_25A3R_REAL_UIA_STRUCTURAL_CHILD.json](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3R_REAL_UIA_STRUCTURAL_CHILD.json#L56-L107)).
3. **Mathematically Sound World Restoration**: The completion oracle evaluates ownership-relative restoration ($\text{task\_residue} = 0$, $\text{harness\_residue} = 0$, $\text{baseline\_missing} = 0$, $\text{external\_modified} = 0$, $\text{unknown\_modified} = 0$) rather than fragile global desktop emptiness, accurately accounting for Windows desktop station isolation ([F0_25A3R_WORLD_RESTORATION.json](file:///e:/Workspace/Agents/AstraRun-Anti/docs/audit/F0_25A3R_WORLD_RESTORATION.json#L6-L49)).
4. **Empirical Verification Baseline**: 59/59 regression and adversarial mutation tests pass. Zero synthetic identities are claimed as physical. Zero baseline, external, or unknown resources are touched.
