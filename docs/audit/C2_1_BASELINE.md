# AstraRun C2.1 — Stage 0 Baseline Audit Report
**Scope:** Reconstruct Baseline State, Physical Workstation Parameters, Security Invariants, and Discrepancies  
**Audit Date:** 2026-10-07  
**Status:** BASELINE RECONSTRUCTED  

---

## 1. System, Runtime, and Workstation Baseline

### Git Revision and Tree Status
- **Base Commit HEAD:** `f4e5d06` (`fix(rc5a): end-to-end causal workflow execution, save_text_file capability, and evidence integrity`)
- **Uncommitted Modifications:** 49 tracked files modified across `src/astrarun` and project roots.
- **Untracked Directories/Files:** 25 entries (including test holdout suites, audit evidence, architecture documents).
- **Composite Production Source Tree SHA-256 (268 files):** `f9ba8c32023d11c99802df915e9ca1294cc37c4cebce56a0118bd82e4d137143`

### Workstation Environment & UAC State
- **Operating System:** Windows 11 Build 26200 (Platform string: `Windows-11-10.0.26200-SP0`, 64-bit AMD64).
- **Python Version:** `3.13.0 (tags/v3.13.0:60403a5, Oct  7 2024, 09:38:07) [MSC v.1941 64 bit (AMD64)]`
- **Active Executable:** `E:\Workspace\Active\AstraRun\.venv\Scripts\python.exe`
- **Base Python Runtime:** `C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe`
- **UAC Configuration (HKLM):**
  - `EnableLUA = 1` (UAC actively enabled)
  - `ConsentPromptBehaviorAdmin = 5` (Prompt for consent for non-Windows binaries)
- **Caller Process Elevation:** `IsUserAnAdmin() == False` (Standard non-elevated user token; no administrative bypass).
- **Hardware Resources:**
  - System RAM: ~16 GB
  - CPU: Intel Core i5-12450H
  - GPU: NVIDIA GeForce RTX 2050 (4 GB VRAM)

---

## 2. Actual Production Call Graph

The verified causal call graph from user/model proposal to OS action and back:

```text
User Intent / Prompt
    |
    v
[InputRouter] (src/astrarun/routing/input_router.py)
    |-- Non-Dynamic / System Intent -> Pre-registered Capability Path
    +-- Dynamic Synthesis Intent -> [DynamicToolBuilder]
            |
            v
[DynamicToolBuilder] (src/astrarun/tools/dynamic_builder.py)
    |-- AST Defense: [ASTInspector] (defense-in-depth, not OS boundary)
    |-- Pre-execution Resource Check: [ResourceGovernor]
    |-- Execute Candidate / Script: [SandboxManager]
            |
            v
[SandboxManager] (src/astrarun/sandbox/manager.py)
    |-- Workspace setup in AppData/LocalLow/AstraRun/sandbox/<run_id>
    |-- Staging inputs & recording pre-existing files/sizes/mtimes
    |-- Worker Launch Boundary:
            |
            v
    [RestrictedWorkerLauncher] (C2) / [AppContainerLauncher] (C2.1)
            |-- Suspended Process Creation (No-Window)
            |-- Job Object Assignment (Ceilings + Kill-On-Close)
            |-- Resume Process & Capture Pipe Output
            v
    [Win32 Kernel Enforcement]
            |-- NTFS MIC / Container DACL Check
            |-- Network Capability Check
            |-- Process Boundary Check
            v
    [Independent Verifier / Sandbox Output Discovery]
            |
            v
    [ExecutionBroker] (src/astrarun/security/execution_broker.py)
            |-- ActionProposal created (ACT vs OBSERVE)
            |-- [ActionGate] (src/astrarun/security/action_gate.py)
            |       |-- Policy, Confirmation, Risk Evaluation
            v
    [deliver_artifact] (src/astrarun/files/service.py)
            |-- Reparse point & symlink source rejection
            |-- Sandbox boundary verification (real_path strictly in sandbox)
            |-- TOCTOU-resistant atomic in-memory read & SHA-256 match
            |-- Prohibited destination filtering (Windows, Startup, .ssh)
            |-- Host write
            v
[TaskLedger / Context Updates]
```

---

## 3. C2 Claim Reconciliation & Raw Evidence

| Claimed C2 Security Dimension | C2 Label | C2.1 Re-evaluation | Raw Evidence / Status |
|---|---|---|---|
| Filesystem Write Isolation | `PASS` | `RAW_MEASURED` | **ENFORCED**. NTFS MIC `No-Write-Up` blocks writes to Desktop, Documents, AppData, `sys.prefix`, and Windows with `PermissionError: [Errno 13]`. |
| Filesystem Read Isolation | `GAP_MEASURED` | `RAW_MEASURED` | **CONFIRMED GAP**. Low IL permits read-up from Medium integrity user files. Synthetic Documents and SSH canaries were read. |
| Network Isolation | `GAP_MEASURED` | `RAW_MEASURED` | **CONFIRMED GAP**. Low IL possesses unconstrained Winsock socket access. TCP connects to `8.8.8.8:53` and localhost succeeded. |
| Process Control Isolation | `GAP_MEASURED` | `RAW_MEASURED` | **CONFIRMED GAP**. `OpenProcess(PROCESS_TERMINATE)` succeeded against sacrificial same-user processes because user SID was unchanged. |
| Process-Tree Containment | `PASS` | `RAW_MEASURED` | **ENFORCED**. Win32 Job Object `KILL_ON_JOB_CLOSE` terminates grandchild processes upon parent job closure. |
| Registry Isolation | `PASS` | `RAW_MEASURED` | **ENFORCED**. Registry MIC blocks writes to `HKCU` and Run keys with `PermissionError: [WinError 5] Access is denied`. |
| Secret Isolation | `PASS` | `RAW_MEASURED` | **ENFORCED**. Explicit allowlist environment block excludes host secrets and API keys. |
| Artifact Delivery & TOCTOU | `PASS` | `RAW_MEASURED` | **ENFORCED**. Source symlinks/reparse points, sandbox escapes, and mismatched SHA-256 hashes are strictly rejected. |
| Legitimate Workloads | `PASS` | `RAW_MEASURED` | **ENFORCED**. Arithmetic, JSON, CSV, NumPy, and Matplotlib execute cleanly under Low IL. |

---

## 4. Shared Window Station & Desktop Security Descriptors

### Inspection Results
- **Current `winsta0` Handle:** 316
  - **DACL SDDL:** `D:(A;NP;LCWP;;;S-1-5-21-...-1001)(A;OICIIO;GAGXGWGR;;;S-1-5-5-0-...)(A;NP;0x20327;;;S-1-15-2-2)(A;NP;0x20327;;;AC)`
  - **LABEL SDDL:** `S:(ML;;NW;;;LW)` (Low Mandatory Level label set by C2)
- **Current `desktop` Handle:** 320
  - **DACL SDDL:** Includes `ALL APPLICATION PACKAGES` (`AC`) and `ALL RESTRICTED APPLICATION PACKAGES` (`S-1-15-2-2`)
  - **LABEL SDDL:** None (implicit Medium Integrity)

### Finding & Safe Remediation
- **Analysis:** In Phase C2, `RestrictedWorkerLauncher.ensure_window_station_low_integrity()` called `SetSecurityInfo` to apply `S:(ML;;NW;;;LW)` to `winsta0`.
- **Constraint:** As instructed, we **do not guess an original descriptor and blindly reset shared objects** via manual API mutation. Window stations and desktop objects in Windows are session-ephemeral kernel objects bound to the interactive logon session.
- **Safe Remediation:** 
  1. Window stations naturally reset to clean Windows defaults on session logoff/logon or system reboot.
  2. All new C2.1 code eliminates `ensure_window_station_low_integrity()` entirely.
  3. Generated worker processes are strictly headless and do not relabel interactive desktop/station objects.

---

## 5. Process-Control Ambiguity Reproduction (Sacrificial Targets)

Empirical test executed using an isolated sacrificial helper process (`PID 15436`):
- **Child Token:** Restricted Token + Low Integrity Level (`0x1000`).
- **Target Process:** Medium Integrity Python helper process (`PID 15436`).
- **Probe Results:**
  - `OpenProcess(PROCESS_TERMINATE, False, pid)`: **`handle=True, err=0`** (Acquisition Succeeded!).
  - `OpenProcess(PROCESS_VM_READ, False, pid)`: **`handle=False, err=5`** (Access Denied by MIC).
  - `OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)`: **`handle=False, err=5`** (Access Denied by MIC).
  - `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)`: **`handle=True, err=0`** (Allowed).
- **Target Survival:** Helper process remained alive (terminate was not invoked during probe), but the capability to terminate was proven available under the C2 token.
- **Conclusion:** Proves that C2's Restricted Token + Low IL has an inherent process-termination gap because user SID is retained and process DACLs grant user access.

---

## 6. Separation of Regressions from Unseen Holdouts & Freeze Ordering

- **C1.8 Routing Holdout (70 Prompts):** Authoritative regression test suite (`tests/unit/test_post_freeze_routing_holdout.py`). Status: 70/70 PASS (100%).
- **C1.8 Generic Repair Holdout (8 Programs):** Authoritative regression test suite (`tests/unit/test_generic_repair_holdout.py`). Status: 6/8 repaired, 0 escapes, `REPAIR-06` passing.
- **C2 Adversarial Matrix (30 Tests):** Authoritative regression test suite (`tests/unit/test_c2_adversarial_suite.py`). Status: 30/30 PASS (100%).
- **Freeze Ordering Invariant:** In Stage 4, all production and harness code must be frozen before fresh unseen C2.1 holdouts are generated and executed. No production changes may follow holdout execution.
