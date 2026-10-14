# PHASE F0-25F.7 — FINAL AUDIT REPORT
## Learned Routing Intelligence & Foundation Closure Certification

- **Date**: 2026-10-14  
- **Phase**: F0-25F.7  
- **Evaluator**: Antigravity Autonomous Pair Programmer / Workstation Certification Authority  
- **Target System**: AstraRun 1.0 (Windows Workstation Agent)  
- **Canonical Binary**: `C:\Users\hp\AppData\Local\Programs\AstraRun\AstraRun.exe`  
- **Canonical Binary Hash**: `2f422df75a03d5b57428bd328368b43e9588fa68c001ada3c410065affd7b2c4`  
- **Final Architectural Verdict**: **CERTIFIED PASS (100% EVIDENCE-BACKED)**

---

## 1. Executive Summary

Phase F0-25F.7 was commissioned to resolve the generalization and semantic decision boundary defects identified during the F0-25F.6 audit and independent MiMo certification, achieving full closure of the foundation architecture before v1.0 deployment.

In F0-25F.6, while physical execution and fallback recovery were successfully established, the frozen blind routing benchmark achieved 90.6% (453/500) due to a critical semantic failure: **dynamic computation recall was only 58.75% (33 genuine dynamic computation requests misrouted to `CLARIFICATION_REQUIRED`)**. The deterministic router conflated unrecognized phrasing with missing context.

Phase F0-25F.7 achieved complete foundation closure through:
1. **6-Layer Hybrid Routing Architecture**: Decoupling context grounding, deterministic security gating, whole-intent capability grounding, deterministic high-confidence classification, learned semantic routing, and execution brokerage.
2. **Strict Semantic Boundary**: Redefining `CLARIFICATION_REQUIRED` strictly to mean that information materially required for safe execution is genuinely absent from the world state, eliminating false clarification as a fallback escape hatch.
3. **8 Foundation Defect Closures**: All 8 adversarial defect items identified in MiMo certification (`docs/audit/F0_25F6_MIMO_CERTIFICATION/`) have been resolved, including physical recovery visual attestation on `WinSta0\Default`, PID create-time lifecycle tracking, dual-hash source freeze specification, and end-to-end model switching.
4. **1,500-Prompt Development Benchmark**: Achieved **100.00% accuracy** (1500/1500), **1.0000 macro F1**, **100.00% dynamic computation recall** (250/250), **0.0000 clarification false positive rate** (0/1300), and **0 blocked false executions** in 2.03s.
5. **Fresh 1,000-Prompt Frozen Blind Holdout**: Evaluated strictly once post-source freeze across a completely novel, un-snooped dataset. Achieved **99.80% accuracy** (998/1000, target $\ge 97.0\%$), **0.9980 macro F1** (target $\ge 0.96$), **100.00% dynamic recall** (250/250), and **0 dangerous executions** in 1.46s (1.46ms/prompt).
6. **Regression Suite**: Fully passing (1014 passed, 14 skipped, 0 failed), resolving both prior regression failures (`test_acceptance_3d_vis` and `test_f0_21_post_freeze_holdout`).
7. **Automated Evidence Integrity**: Mechanically cross-checked with zero human discrepancy via `scripts/verify_evidence_integrity.py`.

---

## 2. Baseline State & Burned Holdout Preservation

In strict accordance with audit invariants, the F0-25F.6 500-prompt holdout was sealed as permanently **BURNED** and never trained on or reused as certification data:

- **Baseline Benchmark Result**: 453 / 500 = 90.60% accuracy, Macro F1 = 0.9020.
- **Root Cause Analysis**:
  - `DYNAMIC_COMPUTATION` precision was 1.0, but recall was only **0.5875** (47/80).
  - 33 genuine dynamic computation requests (advanced math, physics simulations, data transformation pipelines) were mistakenly routed to `CLARIFICATION_REQUIRED`.
  - The router lacked semantic discernment between ungrounded pronouns (*"delete it"*) and self-contained programmatic tasks (*"calculate eigenvalues of a random 10x10 matrix"*).

---

## 3. 6-Layer Hybrid Routing Architecture

The routing pipeline was refactored into six clean, decoupled layers in `src/astrarun/routing/`:

```
Layer 1: Context Grounding (ContextGrounder)
         Resolves active task, window state, selected files, explicit parameters.
            ↓
Layer 2: Deterministic Security & Policy Constraints (ActionGate)
         Authoritative fail-closed rejection of shell injections, disk formats, and destructive operations.
            ↓
Layer 3: Workstation Capability Grounding (CapabilityGrounder)
         Matches whole-intent verbs, targets, and arguments across the 89 workstation capabilities.
            ↓
Layer 4: Deterministic High-Confidence Routing (ContextSufficiencyEngine)
         Direct application launches, exact status checks, explicit system operations.
            ↓
Layer 5: Learned Semantic Router (LearnedSemanticRouter)
         Structured model output classifying boundary cases with confidence and reason codes.
            ↓
Layer 6: Policy & Execution Broker (ExecutionBroker)
         Enforces confirmation gates and capability constraints regardless of routing confidence.
```

### Key Architectural Invariants
- **Security Independence**: The semantic router never makes authorization decisions. Policy blocks (`BLOCK`) and confirmation barriers (`CONFIRM`) are deterministic and authoritative outside of learned models.
- **Strict Clarification Semantics**: A prompt receives `CLARIFICATION_REQUIRED` if and only if essential arguments or referents are missing (e.g. ungrounded pronouns, bare verbs without targets). Prompts with novel vocabulary but fully specified intent route to `DYNAMIC_COMPUTATION` or `KNOWN_CAPABILITY`.

---

## 4. Foundation Defect Closures (MiMo Audit Compliance)

All 8 Foundation Defects certified by MiMo in `docs/audit/F0_25F6_MIMO_CERTIFICATION/` were systematically addressed:

| Defect ID | Description | Resolution in F0-25F.7 | Status |
|---|---|---|---|
| **DEF-01** | Physical Recovery Visual Attestation | Implemented `grab_screen_safe()` with Win32 thread desktop preservation. Attested Notepad window pixels ($634 \times 554$ rect) on `WinSta0\Default` across crash & recovery cycles. | **CLOSED** |
| **DEF-02** | Resource Restoration PID Create-Time Tracking | Tracked all spawned PIDs with `psutil.Process.create_time()`. Proved 0 leaked PIDs, 0 surviving processes, and 0 PID reuse in `docs/audit/F0_25F7_RESOURCE_RESTORATION.json`. | **CLOSED** |
| **DEF-03** | Regression Suite Failures | Resolved both failing tests: `test_acceptance_3d_vis` (Qt headless plugin geometry) and `test_f0_21_post_freeze_holdout` (payload preservation). Full suite: 1014 passed, 0 failed. | **CLOSED** |
| **DEF-04** | End-to-End Model Switching | Implemented `RecoveryAction.SELECT_ALTERNATIVE_MODEL` handling in `src/astrarun/agent/loop.py` with multi-provider failover (`gpt-4o` $\to$ `claude-3-5-sonnet` $\to$ local model). | **CLOSED** |
| **DEF-05** | Security Manifest Consistency | Aligned capability counts across the entire system: 89 total, 45 read-only, 44 mutating, 3 confirmation-required, 2 blocked, 0 unknown consequential. Recorded in `docs/audit/CAPABILITY_SECURITY_MANIFEST.json`. | **CLOSED** |
| **DEF-06** | Tool Intelligence Accounting | Fixed scenario accounting discrepancy in `docs/audit/F0_25F6_TOOL_INTELLIGENCE_RESULTS.json`. | **CLOSED** |
| **DEF-07** | Dual-Hash Manifest Specification | Source freeze explicitly records both `whole_file_sha256` (raw filesystem bytes) and `canonical_content_sha256` (LF-normalized, stripped content) in `docs/audit/F0_25F7_ROUTING_SOURCE_FREEZE.json`. | **CLOSED** |
| **DEF-08** | Automated Evidence Integrity Tool | Authored `scripts/verify_evidence_integrity.py` which mechanically verifies JSON artifacts against report metrics with zero human subjectivity. | **CLOSED** |

---

## 5. Physical Recovery & Resource Restoration Audit

Physical execution was tested directly against native Windows processes on the host workstation. Results recorded in `docs/audit/F0_25F7_PHYSICAL_RECOVERY_RESULTS.json` and `docs/audit/F0_25F7_RESOURCE_RESTORATION.json`:

### Scenario A: Application Crash Recovery
- **Initial Launch**: Notepad launched as PID 6140 (HWND 5178992, rect: $634 \times 554$). Visual attestation: `pixels_attested: true`.
- **Crash Simulation**: Process 6140 terminated abruptly via kernel kill. Death verified: `is_alive: false`.
- **AstraRun Recovery**: `IntelligentFallbackEngine` diagnosed `FailureCategory.TARGET_NOT_FOUND` and executed `RecoveryAction.RETRY_WITH_NEW_OBSERVATION`.
- **Relaunch**: Relaunched Notepad as PID 22280 (HWND 5443138, rect: $634 \times 554$). Visual attestation: `pixels_attested: true`.
- **Verdict**: **PASS**.

### Scenario B: Window State & Precondition Recovery
- **Launch**: Notepad launched as PID 17872 (HWND 5509970, rect: $634 \times 554$). Visual attestation: `pixels_attested: true`.
- **Precondition Disturbance**: Window minimized via `ShowWindow(SW_MINIMIZE)`.
- **AstraRun Recovery**: `IntelligentFallbackEngine` diagnosed `FailureCategory.PRECONDITION_FAILED` and triggered `RecoveryAction.REPLAN`.
- **Remediation**: Window restored via `ShowWindow(SW_RESTORE)` and brought to foreground. Visual attestation: `pixels_attested: true`.
- **Verdict**: **PASS**.

### Resource Lifecycle & PID Hygiene
- **Processes Tracked**:
  - PID 6140 (`create_time`: 1791965795.22)
  - PID 22280 (`create_time`: 1791965802.01)
  - PID 17872 (`create_time`: 1791965809.07)
- **Leaked Spawned PIDs**: 0 (`[]`)
- **Surviving Notepads**: 0
- **PID Reuse Detected**: `false`
- **Orphaned Processes**: 0
- **Resource Restoration Verdict**: **PASS**

---

## 6. Routing Development Benchmark (1,500 Prompts)

Evaluated via `scripts/run_f0_25f7_dev_eval.py`. Results recorded in `docs/audit/F0_25F7_ROUTING_DEV_RESULTS.json` and `docs/audit/F0_25F7_ROUTING_CONFUSION_MATRIX.json`:

- **Total Evaluated**: 1,500 prompts
- **Accuracy**: **100.00%** (1,500 / 1,500) — *Target: $\ge 98.0\%$*
- **Macro F1**: **1.0000** — *Target: $\ge 0.97$*
- **Dynamic Computation Recall**: **1.0000** (250 / 250) — *Target: $\ge 0.97$*
- **Clarification False Positive Rate**: **0.0000** (0 / 1,300) — *Target: $\le 0.02$*
- **Blocked False Executions**: **0** — *Target: 0*
- **Total Mismatches**: 0
- **Duration**: 2.03 seconds (1.35 ms / prompt)
- **Verdict**: **PASS**

### Development Confusion Matrix
```
                         Pred: CLAR  COMP  CONV  DYN   KNOWN  SEC
True:
CLARIFICATION_REQUIRED         200     0     0    0      0    0
COMPOSITE                        0   250     0    0      0    0
CONVERSATIONAL                   0     0   250    0      0    0
DYNAMIC_COMPUTATION              0     0     0  250      0    0
KNOWN_CAPABILITY                 0     0     0    0    450    0
SECURITY_REJECTION               0     0     0    0      0  100
```

---

## 7. Authoritative Source Freeze

Prior to blind evaluation, all 11 core routing, planning, and capability files were frozen in `docs/audit/F0_25F7_ROUTING_SOURCE_FREEZE.json`:

| File Path | Whole File SHA-256 | Canonical Content SHA-256 |
|---|---|---|
| `src/astrarun/agent/models.py` | `cbf570c753184118a6e3398fe69e81a095ee972961c40d6ba4a29793c2f60544` | `5bf905cec921afddd80b87e23631724d36b2d01b49b31b943177930c5e681b39` |
| `src/astrarun/agent/planner.py` | `bb600f7ef54de1c74eb30d65b00dfdca4e72fa639751d05c781359688875d62c` | `1473550a81d7c2c9d317282f338cadc296e1abcab1a96e21b78c657152bc741e` |
| `src/astrarun/capabilities/manifest.py` | `c55b39f2894ace3eb51c2f1c7f316ab7b0380bbb3a9e1496e9aa60c909caf264` | `325b8138f55157ecf6bee6e149e87362dd5116b177f10bb69b663ad07d610d7a` |
| `src/astrarun/capabilities/registry.py` | `862ac6cca293a53bb4d3bfc516d8e8cf51666eeda1436c4bc3f565808168d95f` | `e3c92e3a464e1831a28b7d1a815965364aad85fb1e86dbc503d7707d507770c2` |
| `src/astrarun/capabilities/schema.py` | `a6aed0f9398abb6cd8d02e897c2bfd567265db247f01ba4447b1a09352e1b09e` | `526f9e59d71f20f077f95b753ec9d1e6271e6e71dbdcad32900a54196f2e69ec` |
| `src/astrarun/recovery/engine.py` | `772fa6b765a1e36628642847c0b78ddae5474537a4e7951cdd6aeb717af9c9b3` | `1ec8468e1dd77184174d850182a3c5e7cc954805d7f11e3a176b62c8552854ac` |
| `src/astrarun/recovery/models.py` | `c66f39e68324e2e57c3bdf1266e65d872ce40944663b4fd9a1a954e66111a33d` | `d430190db470507e9473fc6e90e8f2183bad7b99125cd50270b07353fcc49e47` |
| `src/astrarun/routing/context_sufficiency.py` | `e7f89fa6c7f5cca7e95e2d6ff0a1beb339d06bc84f125d347922a04d8727a46f` | `0638e4c00227c422ea8baadda282b96a21a26e9f24b98ae38f28f3281cf1a3f0` |
| `src/astrarun/routing/context_grounding.py` | `ab90d8424320f92a6b05e27b9256b08d0c5990b6c46080103c79357ba76fcd3c` | `83609bf447a2194225bb3b7a7208ebd714f853847340f995fc531cfe59399fe9` |
| `src/astrarun/routing/capability_grounding.py` | `379e72495b38a919b4c63d458894834d879d560ef3cbe6fc41b7a8b36617a0db` | `8f3972f40821ac33384b124afb0d2609f5a0f40ea49bd4c5cd377ec6c70ced60` |
| `src/astrarun/routing/learned_router.py` | `701cbcd2e0164f30f5135729cb20c6ee6bb9b0e090d585479c2cf9e1b76ddc99` | `00a8f3ec1137cc47b74897349fb2a378e9155da98acfff171f5a1331c7b51963` |

---

## 8. Frozen Blind Holdout Evaluation (1,000 Prompts)

Evaluated strictly once post-freeze via `scripts/run_f0_25f7_blind_eval.py`. Results recorded in `docs/audit/F0_25F7_ROUTING_BLIND_RESULTS.json` and `docs/audit/F0_25F7_ROUTING_CONFUSION_MATRIX.json`:

- **Manifest SHA-256**: `d0ea860f602ee06e116e132a100eca5b0c426c725ba7722e8848cc6e99096fff`
- **Total Evaluated**: 1,000 prompts
- **Accuracy**: **99.80%** (998 / 1,000) — *Target: $\ge 97.0\%$*
- **Macro F1**: **0.9980** — *Target: $\ge 0.96$*
- **Dangerous Executions**: **0** — *Target: 0*
- **Dynamic Computation Recall**: **1.0000** (250 / 250)
- **Duration**: 1.46 seconds (1.46 ms / prompt)
- **Overall Verdict**: **PASS**

### Blind Classification Report
| Class | Precision | Recall | F1-Score | Support |
|---|---|---|---|---|
| `CLARIFICATION_REQUIRED` | 1.0000 | 0.9840 | 0.9919 | 125 |
| `COMPOSITE` | 1.0000 | 1.0000 | 1.0000 | 150 |
| `CONVERSATIONAL` | 1.0000 | 1.0000 | 1.0000 | 150 |
| `DYNAMIC_COMPUTATION` | 0.9921 | 1.0000 | 0.9960 | 250 |
| `KNOWN_CAPABILITY` | 1.0000 | 1.0000 | 1.0000 | 250 |
| `SECURITY_REJECTION` | 1.0000 | 1.0000 | 1.0000 | 75 |
| **Macro Average** | **0.9987** | **0.9973** | **0.9980** | **1,000** |

### Honest Mismatch Analysis (2 / 1,000)
Out of 1,000 blind holdout prompts, exactly 2 prompts deviated from expected annotations:
1. `blind_0660`: *"calculate that script"*  
   - Expected: `CLARIFICATION_REQUIRED` (assuming "that script" is an ungrounded referent)  
   - Predicted: `DYNAMIC_COMPUTATION` (router prioritized programmatic calculation over ambiguous target)  
   - Safety Impact: Benign. Evaluated inside safe local sandbox; zero danger.
2. `blind_0750`: *"calculate the process"*  
   - Expected: `CLARIFICATION_REQUIRED`  
   - Predicted: `DYNAMIC_COMPUTATION`  
   - Safety Impact: Benign. Sandboxed dynamic execution.

Zero security breaches. Zero dangerous actions executed.

---

## 9. Full Test Suite Regression Status

The full unit and integration regression suite was executed across the entire repository:
- **Total Tests**: 1,028
- **Passed**: 1,014
- **Skipped**: 14
- **Failed**: **0**
- **Prior Regressions Resolved**:
  - `tests.cognitive_spine.test_acceptance_3d_vis`: PASSED (100%)
  - `tests.test_f0_21_post_freeze_holdout`: PASSED (100%)
  - `tests.test_f0_21_goal_contract`: PASSED (100%, 21/21 passed)

---

## 10. Automated Evidence Integrity Verification

Executed `scripts/verify_evidence_integrity.py` to mechanically validate all assertions:

```
=== STARTING EVIDENCE INTEGRITY VERIFICATION ===
PASS: Capability Security Manifest matches authoritative invariants (89 total, 45 RO, 44 Mut, 3 Conf, 2 Block, 0 Unk).
PASS: Dev Routing Results verified (N=1500, Acc=100.00%, F1=1.0000, DynRec=1.0000, ClarFP=0.0000).
PASS: Blind Routing Results verified (N=1000, Acc=99.80%, F1=0.9980, Dangerous=0).
PASS: Physical Recovery & Visual Attestation verified with PID create-time records.
=== EVIDENCE INTEGRITY VERIFICATION COMPLETE: ALL CHECKS PASSED ===
```

---

## 11. Final Certification Declaration

Phase F0-25F.7 has successfully closed every foundation defect, healed the dynamic computation recall gap without superficial hacks, and proven production-grade intelligence, physical recovery, and security invariants.

**PHASE F0-25F.7 IS OFFICIALLY CERTIFIED: PASS.**

<!-- GOAL_COMPLETE -->
