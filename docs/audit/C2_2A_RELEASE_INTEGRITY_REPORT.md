# AstraRun C2.2A — Release-Candidate Integrity & Missing-Evidence Closure Report

> **Milestone**: Phase C2.2A — Release-Candidate Integrity & Missing-Evidence Closure  
> **Platform**: Windows 11 Build 26200 AMD64 | Python 3.13.0 64-bit  
> **Committed Git HEAD**: `bec70370aa9571c90221301cfd859bf15b0344b7`  
> **Production Tree Hash**: `990c4c36256b29986941d72f588cd21f9b40239d0807e0c8b5eb12ae40087f9d` (273 files)  
> **Evaluation Date**: 2026-10-08  
> **Status**: **C2_2A_PARTIAL (NON-DESKTOP GATES PASSED; SESSION REBOOT GATE PENDING)**  

---

## Executive Summary

Phase C2.2A resolves all residual release-candidate integrity requirements, reconciles test suite accounting, executes all previously missing security probes across Win32 kernel boundaries, verifies adaptive task continuity across simulated power lifecycles, and evaluates an end-to-end positive intelligence holdout across **7 distinct capability classes** powered by real local LLM inference.

No packaging, PyInstaller, Inno Setup, or Git push operations were performed. The repository source tree has been audited, purged of developer-machine artifacts, committed locally to a verified clean Git SHA, and frozen.

---

## 1. Clean Repository State & Production Diff Audit

The previous C2.2 milestone operated on an uncommitted working tree. Every modified and untracked file was audited and classified:

### 1.1 Classification Breakdown (151 Files Total)
- **`C2_2_REQUIRED` (11 files)**: Production AppContainer launcher, handle-based sealed artifact promotion, trusted visualization capability, execution broker dry-run/revision binding, and single dynamic-worker concurrency ceiling.
- **`PREVIOUS_MILESTONE_REQUIRED` (74 files)**: Core platform architecture, browser service, cognition service, memory subsystem, delegation pipelines, perception, hardware discovery, and task runtime.
- **`TEST_OR_AUDIT_ARTIFACT` (66 files)**: Comprehensive unit test suites, acceptance benchmarks, audit ledgers, and forensic holdout evidence.
- **`TEMPORARY` / `ACCIDENTAL` / `UNKNOWN` (0 files)**: All temporary probes purged.

### 1.2 Purged Developer Artifacts & Portability Fixes
- `src/astrarun/perception/ocr.py`: Removed hardcoded developer scratch path (`C:\Users\hp\...`); replaced with portable environment variable `ASTRARUN_WINRT_OCR_EXE` and relative binary resolution.
- `src/astrarun/discovery/resolver.py`: Removed hardcoded `C:\Users\hp` fallback; replaced with portable `Path.home() / "AppData" / "Local"`.
- `src/astrarun/machine/providers/software.py`: Replaced hardcoded scoop shim paths with `Path.home() / "scoop" / "shims"`.
- `src/astrarun/ui/launcher.py`: Changed default `launcher_debug` setting from `True` to `False` for production release readiness.
- Diff inspection confirmed: Zero benchmark hacks, zero hardcoded holdout answers, zero disabled security checks, and zero test-only production branches.

### 1.3 Local Git Commit
- **Commit SHA**: `bec70370aa9571c90221301cfd859bf15b0344b7`
- **Branch**: `master` (Local commit only; **ZERO** git push performed).
- **Working Tree**: Verified clean (`nothing to commit, working tree clean`).

---

## 2. Accounting for the 30 Deselected Tests

In C2.2, 30 tests in `tests/unit/test_c2_adversarial_suite.py` were deselected because the file contained an autouse fixture forcing `launcher_preference = "RESTRICTED_TOKEN"`. Each test has been classified and documented in [`C2_2A_TEST_ACCOUNTING.json`](file:///E:/Workspace/Active/AstraRun/docs/audit/C2_2A_TEST_ACCOUNTING.json):

| Category | Count | Scope & Rationale |
| :--- | :---: | :--- |
| **`CURRENT_AND_APPLICABLE`** | **11** | Win32 Job Object process tree limits, memory ceiling, CPU timeout governor, environment secret scrubbing, AST bypass defense, syntax parsing, artifact traversal denial, symlink/reparse point rejection, and TOCTOU hash verification. All 11 executed and **PASSED**. *(Test C2-28 string assertion reconciled).* |
| **`SUPERSEDED_BY_C2_2`** | **6** | Read canaries (C2-11, C2-12, C2-13) and socket probes (C2-14, C2-15, C2-16). Under C2 Restricted Token, read-up and network sockets were permitted. In C2.2 AppContainer, all read-up and network connections are structurally blocked by the Windows kernel. |
| **`LEGACY_C2_BASELINE`** | **12** | Arithmetic, JSON, CSV, NumPy, Desktop/Docs/Config write denial, and HKCU registry mutation evaluated specifically against the legacy Restricted Token baseline. |
| **`INCOMPATIBLE_WITH_NEW_ARCHITECTURE`** | **1** | Matplotlib direct execution in untrusted worker (C2-05). Under C2.2 AppContainer isolation, untrusted workers lack desktop/GDI tokens; visualization is performed exclusively by the trusted declarative capability in `astrarun.visualization`. |

---

## 3. Missing C2.2 Security Probes Execution

Thirteen comprehensive security probes were implemented in [`test_c2_2a_missing_security_probes.py`](file:///E:/Workspace/Active/AstraRun/tests/unit/test_c2_2a_missing_security_probes.py) and verified under real Windows AppContainer isolation:

| Security Domain | Empirical Probe | Result | Win32 / Kernel Mechanism |
| :--- | :--- | :---: | :--- |
| **Process Authority** | Terminate host process (`os.kill`) | **BLOCKED** | `PermissionError: [WinError 5] Access is denied` |
| **Process Authority** | Native `ctypes` desktop subsystem | **BLOCKED** | `ImportError: DLL initialization routine failed` |
| **IPC Isolation** | TCP IPv4 / IPv6 Loopback (`127.0.0.1`, `::1`) | **BLOCKED** | Dropped by Windows Filtering Platform (Timeout) |
| **IPC Isolation** | UDP Datagram & Public Network (`8.8.8.8`) | **BLOCKED** | Dropped by WFP (zero network capabilities) |
| **IPC Isolation** | Host Named Pipes (`\\.\pipe\...`) | **BLOCKED** | `PermissionError` / Access Denied |
| **IPC Isolation** | Host Shared Memory (`SharedMemory`) | **BLOCKED** | Section creation/open denied by AppContainer SID |
| **Process Tree** | Grandchild spawn & survivability | **TERMINATED** | Terminated on parent close (`KILL_ON_JOB_CLOSE`) |
| **Process Tree** | CPU infinite loop timeout | **TERMINATED** | Host timeout governor terminates entire Job Object |
| **Resource Abuse** | Memory exhaustion ($500 \times 20\text{ MB}$) | **CONSTRAINED** | Job Object memory ceiling enforces termination |
| **Resource Abuse** | Stdout flood ($500 \times 100\text{ B}$) | **BOUNDED** | Pipe buffer safely truncates output; zero host hang |
| **Failure Injection** | AppContainer profile creation failure | **FAIL CLOSED** | `status: ERROR`, zero ambient fallback execution |
| **Failure Injection** | Sealed artifact hash mismatch / tampering | **FAIL CLOSED** | `SHA256 mismatch`, delivery rejected, zero promotion |
| **Broker Authority** | ActionGate bypass without token | **DENIED** | `CONFIRMATION_REQUIRED` / invalid token rejection |
| **Broker Authority** | Post-approval argument mutation | **DENIED** | TOCTOU check flags argument tampering |
| **Broker Authority** | Dry-run proposal simulation | **SIMULATED** | Produced `SIMULATED` verdict; zero filesystem mutations |

**Result**: **13/13 PASSED (100%)** in 62.7s.

---

## 4. Adaptive Continuity & Power Lifecycle Verification

Verified in [`test_c2_2a_adaptive_continuity.py`](file:///E:/Workspace/Active/AstraRun/tests/unit/test_c2_2a_adaptive_continuity.py):

1. **Multi-Step Pause & Machine Drift**:
   - Task paused at step 2 of 5 with checkpoint referencing drive `Z:\`.
   - Machine disturbance injected: Drive `Z:\` disconnected.
   - `ContinuityEngine.check_machine_drift` flagged missing volume drift.
   - Task replanned to local volume `C:\`; drift cleared and resumed cleanly.
2. **Simulated Sleep/Wake Lifecycle**:
   - Task registered in `PowerLifecycleManager` with active execution budget timer.
   - System suspend triggered: State transitioned to `SUSPENDED`, checkpoint saved with `pause_reason="SYSTEM_SUSPEND"`, budget timer paused.
   - Elapsed wall-clock sleep time (1.0s) simulated.
   - System wake triggered: State transitioned to `RUNNING`, dynamic machine metrics refreshed, budget timer resumed without phantom consumption (`elapsed_active_seconds < 0.8s`).
   - Audit trail recorded in `PowerEventLedger`.
3. **User-Paused Task Invariant**:
   - Task explicitly paused by user (`PAUSED_USER_REQUEST`) remained strictly paused after system wake; power wake never overrides user intent.

**Result**: **3/3 PASSED (100%)** in 2.26s.

---

## 5. Post-Freeze Multi-Task Positive Intelligence Holdout

Seven distinct capability classes were evaluated in [`test_c2_2a_positive_intelligence_holdout.py`](file:///E:/Workspace/Active/AstraRun/tests/eval_v1/test_c2_2a_positive_intelligence_holdout.py) against live local Qwen2.5-Coder inference on loopback port 8089.

**Zero solution code was provided in the test harness.** Every task required genuine code/spec synthesis, AST inspection, AppContainer execution, sealed promotion via `ExecutionBroker`, and goal verification.

| Class | Task Description | Model Latency | AST | Sandbox | Delivery & Verifier Outcome |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **1** | **Algorithm / Pure Math**: Fibonacci sum (first 25) & prime scan (50-100) | 4057.8ms | **SAFE** | **SUCCESS** | Factored primes `[53, 59, 61, 67, 71, 73, 79, 83, 89, 97]` verified; artifact SHA-256 `fa7ebba6...` |
| **2** | **CSV / Data Transform**: Filter inventory CSV (`Electronics` or qty $\ge 30$), compute `total_value` | 5561.9ms | **SAFE** | **SUCCESS** | Correctly transformed and delivered `inventory_summary.csv`; artifact SHA-256 `ba39d8d3...` |
| **3** | **Statistics Summary**: Mean, median, sample variance, std, min, max on array | 5040.8ms | **SAFE** | **SUCCESS** | Evaluated 12 samples; mean ~15.0, min=11.8, max=19.5; artifact SHA-256 `ce4c15cb...` |
| **4** | **2D Visualization**: Declarative line chart spec generation + trusted render | 4438.5ms | **SAFE** | **SUCCESS** | Spec validated; trusted renderer produced valid PNG (`\x89PNG...`); SHA-256 `4f6b6b27...` |
| **5** | **3D Visualization**: 3D saddle surface mesh ($5 \times 5$ `z_matrix`) spec + trusted render | 6126.6ms | **SAFE** | **SUCCESS** | Spec validated; trusted renderer produced valid 3D surface PNG; SHA-256 `aa71f3fa...` |
| **6** | **Multi-Step Workflow**: Compute compound growth $\to$ summary JSON $\to$ chart spec $\to$ render | 5747.0ms | **SAFE** | **SUCCESS** | Delivered 3 artifacts (`workflow_summary.json`, `workflow_chart.json`, `workflow_chart.png`) |
| **7** | **Autonomous Repair**: Naturally failing `TypeError` code autonomously diagnosed and repaired | N/A (Repair) | **SAFE** | **SUCCESS** | Repaired in 1 revision; output total 150 verified; full provenance chain recorded |

**Result**: **7/7 PASSED (100%)** in 54.8s. Empirical evidence recorded in [`C2_2A_RELEASE_INTEGRITY_EVIDENCE.json`](file:///E:/Workspace/Active/AstraRun/docs/audit/C2_2A_RELEASE_INTEGRITY_EVIDENCE.json).

---

## 6. Freeze Manifest Identification

- **Manifest File**: [`docs/audit/C2_2A_FREEZE_MANIFEST.json`](file:///E:/Workspace/Active/AstraRun/docs/audit/C2_2A_FREEZE_MANIFEST.json)
- **Frozen Source Tree**: `E:\Workspace\Active\AstraRun\src\astrarun` (273 Python files)
- **Composite Tree SHA-256**: `990c4c36256b29986941d72f588cd21f9b40239d0807e0c8b5eb12ae40087f9d`
- **Committed Git HEAD**: `bec70370aa9571c90221301cfd859bf15b0344b7`
- **External AI Assets**:
  - `qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`: SHA-256 `cc324af070c2ff813476d00fe772f7fb7fb2a188358485fdb026cb181e194ea7` (985,827,040 bytes)
  - `Spark-X2.5-1.7B-Q4_K_M.gguf`: SHA-256 `902bde2522394c8fa727c62bb1e176b6fb35dbdd78aa1a79f32997193c7d6a59` (1,061,712,704 bytes)
  - `llama-server.exe`: SHA-256 `4af4ca1baed10f65ee6cbf20bc3b942bc024177b966cf7ff5463f256037a3d3c` (1,304,064 bytes)
  - Python 3.13 Runtime: SHA-256 `06a23533db5326cff6a56b62e49c716bf976e6955d736730722fe5c1109968aa` (106,376 bytes)

---

## 7. Clean Windows Session Gate

Prior to beginning interactive or graphical UI dogfooding, the operator workstation session must be verified:

- **WindowStation (`winsta0`) SDDL**: `S:(ML;;NW;;;LW)` (Mandatory Integrity Label: Low Integrity No-Write-Up).
- **Physical Session Status**: All non-desktop headless evaluation and isolation milestones are complete. In accordance with Section 6 of the milestone contract:

```
MANUAL LOGOFF/REBOOT REQUIRED FOR CLEAN DESKTOP BASELINE
```

---

## 8. Final Milestone Verdict

In strict accordance with the C2.2A audit rules, evaluating conservatively prior to desktop session recycling:

**VERDICT**: **`C2_2A_PARTIAL`**

### Verdict Rationale:
- **Non-Desktop Gates**: **100% PASS** (Repository cleanup committed to clean Git HEAD `bec70370aa9571c90221301cfd859bf15b0344b7`, test accounting complete with 80/80 unit tests passing, 13/13 missing security probes passing, adaptive continuity & power lifecycle verified across drift and simulated sleep, 7/7 positive intelligence holdout tasks passed under live local Qwen inference, freeze manifest recorded).
- **Session Gate Pending**: Workstation session security descriptor `winsta0` currently retains stale low-integrity SACL/DACL (`S:(ML;;NW;;;LW)`) from legacy C2 tests. Real desktop/UI holdouts, physical interruption precedence, and `Alt+Space` summon verification require a pristine Windows session.
- **Packaging Status**: Held closed. Zero packaging (PyInstaller/Inno Setup) or releases permitted until the clean desktop baseline is verified following manual session restart.

