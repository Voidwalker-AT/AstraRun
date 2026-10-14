# MIMO Independent Review — F0-25D.1

**Repo**: `E:\Workspace\Agents\AstraRun-Anti`  
**Branch/HEAD**: `agent/anti-f0-24a1` @ `bd287eba38e6743565fdf6da21cb629023573c6b`  
**Reviewer**: MiMo (adversarial, no code changes)  
**Overall verdict**: **FAIL**

---

## 1. What is FACTUALLY TRUE

| Claim | Classification | Evidence |
|---|---|---|
| Built vs installed `AstraRun.exe` SHA-256 match | **FACT** | Independent `Get-FileHash`: both `9b1b5add…344f`, size 12,054,911 |
| Installer hash matches report | **FACT** | `cd473858…c921` |
| Three deliverables exist under `E:\AstraDogfood\word_frequency` | **FACT** | `main.py` 1486B, `sample_input.txt` 68B, `word_frequencies.json` 204B |
| Harness does **not** author `main.py` before the run | **FACT** | `run_f0_25d1_dogfood.py` never writes main.py |
| Harness **does** wipe/recreate target dir at start | **FACT** | lines 179–186 |
| Harness **re-runs** `main.py` after Astra | **FACT** | lines 546–552; rewrites sample_input/json |
| `math_verified` is not a real frequency equality check | **FACT** | lines 536–537: `isinstance(json, (dict,list)) and txt_verified` |
| UI audit / most acceptance dims hardcoded PASS | **FACT** | lines 588–603, 648–724 |
| All 12 screenshots are Antigravity IDE, not Astra UI | **FACT** | Pixel inspection of every PNG |
| Manifest foreground_process = Antigravity.exe | **FACT** | `F0_25D1_SCREENSHOT_MANIFEST.json` |
| Production mentions `sample_input.txt` / `word_frequencies.json` as prompt examples | **FACT** | `cognition/service.py:421-422` |
| 68/70 routing holdout | **FACT (Anti artifact)** | `C1_8_POST_FREEZE_ROUTING_EVIDENCE.json`; failures: quadratic roots → composite_dag; login summary → system_summary |

---

## 2. Critical contradictions

1. **Screenshots vs labels (CRITICAL)**  
   Anti: “Launcher open / request entered / program execution / final summary.”  
   Actual: identical Antigravity window; text “F0-25D IS AN HONEST FAILURE”; task bar shows `run_f0_25d1_dogfood.py` running.  
   Manifest itself records `foreground_process: Antigravity.exe` while descriptions claim launcher visibility.

2. **EDITOR_INTERACTION = PASS (CRITICAL misclassification)**  
   No Notepad/Notepad++/VS Code editing of the deliverable is shown. Direct file synthesis ≠ editor interaction → should be **NOT_APPLICABLE**.

3. **TERMINAL_EXECUTION = PASS (MAJOR)**  
   No visible console. Harness `subprocess.run` is evaluator verification, not user-visible terminal execution.  
   Split: `COMPUTATION_EXECUTED_ON_HOST` partial-yes; `VISIBLE_TERMINAL_EXECUTION` not observed.

4. **USER_OBSERVABILITY = FAIL**  
   A human watching the desktop would not understand Astra’s plan/tool/progress from these frames.

5. **Artifact verification contamination (MAJOR)**  
   Independent re-execution of `main.py` regenerates `sample_input.txt` and JSON. `math_verified` does not compare tokens (`Hello`/`world!` vs lowercase ground truth).

---

## 3. Harness action table (summary)

| Action | By | Mutating |
|---|---|---|
| Wipe/recreate target dir | HARNESS | yes |
| Launch installed exe + IPC submit | HARNESS | no |
| Create deliverables | NOT harness (pre-run) | — |
| Re-run main.py for verification | HARNESS | yes (rewrites outputs) |
| Hardcode UI/acceptance PASS | HARNESS | no (fake labels) |
| Screenshots on timer/file existence | HARNESS | no |

Harness **does not** complete the software task for Astra by writing main.py itself. That is good. It **does** manufacture milestone evidence and re-executes the deliverable.

---

## 4. main.py quality (TASK SATISFIED vs HIGH-QUALITY)

- Uses `text.split()` only: no lowercase, no punctuation strip → `"Hello"` ≠ `"hello"`, `"world!"` retained.
- Creates its own sample input and JSON (self-contained) — matches F0-25D.1 prompt “make a small sample input yourself.”
- Deterministic for that input; stdlib only; runs exit 0 when independently executed.
- **TASK SATISFIED (weakly)** for “counts word frequencies of a sample file” as written.  
- **NOT HIGH-QUALITY** word-frequency semantics (case/punctuation).

---

## 5. Acceptance re-score (not inherited)

| Dimension | MIMO |
|---|---|
| GOAL_CORRECTNESS | PARTIAL |
| PLANNING_SEMANTICS | UNVERIFIED |
| OPTIONAL_PERMISSION_HANDLING | UNVERIFIED |
| RECOVERY | UNVERIFIED |
| TOOL_DECISION_EXECUTION_ALIGNMENT | UNVERIFIED |
| PHYSICAL_DESKTOP_EXECUTION | PARTIAL |
| ASTRA_LAUNCHER_UI | **FAIL** |
| PROGRESS_UI | **FAIL** |
| VISUAL_DESKTOP_ALIGNMENT | **FAIL** |
| EXTERNAL_CONSULTATION_TRUTH | PARTIAL |
| EDITOR_INTERACTION | **NOT_APPLICABLE** |
| TERMINAL_EXECUTION | **NOT_APPLICABLE** (visible) / PARTIAL (host compute) |
| OUTPUT_PRESENTATION | PARTIAL |
| RESOURCE_RESTORATION | PARTIAL |
| USER_OBSERVABILITY | **FAIL** |

---

## 6. Accept F0-25D.1?

**No.** Do not accept as “real visible dogfood PASS.”

Acceptable reduced claim (if carefully worded):  
*Installed binary hash-matches build; a Python word-frequency script appeared under the requested path during an observer harness run; independent execution exits 0.*  

Not acceptable: 15/15 PASS, visible launcher dogfood, editor interaction, visible terminal, 12-milestone visual proof.

---

## 7. Ready for true user dogfood?

**No.** Human-facing UI observability and honest evidence capture are not demonstrated. Product may compute in background; users cannot currently trust visual/progress claims from this package.

---

## 8. Recommended next engineering phase

1. **Evidence honesty phase**: harness must capture Astra **foreground** UI (or declare background-only), refuse milestone labels that fail pixel/OS checks, and ban hardcoded UI PASS.  
2. **Verification integrity**: never re-run deliverable as if Astra ran it; compare hashes before/after; implement real content equality oracles.  
3. **Semantic routing**: fix 2 holdout failures (math→dynamic_tool; auth summary file→dynamic_tool) and expand neighbor prompts.  
4. **Observability**: ensure launcher progress is visible on the interactive desktop during tasks.  
5. Then re-run dogfood with observer-only harness that cannot invent milestones.

---

## Artifacts

- `MIMO_REVIEW_FINAL.md` (this file)
- `MIMO_REVIEW_ACCEPTANCE_MATRIX.json`
- `MIMO_REVIEW_SCREENSHOT_AUDIT.json`
- `MIMO_REVIEW_HARNESS_PROVENANCE.json`
- `MIMO_REVIEW_ARTIFACT_PROVENANCE.json`
- `MIMO_REVIEW_ROUTING_HOLDOUT.json`
- `MIMO_REVIEW_CONTRADICTIONS.json`
- `MIMO_REVIEW_SECURITY_CHECK.json` (build parity + caps note)

**No production source modified. No commit. No push.**

MIMO REVIEW COMPLETE
