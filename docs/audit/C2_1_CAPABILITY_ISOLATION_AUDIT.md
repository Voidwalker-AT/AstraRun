# AstraRun C2.1 — Capability-Isolated Generated Workers Audit Report

> **Scope**: Implementation and Empirical Audit of Windows 11 AppContainer Worker Isolation, Authoritative ExecutionBroker Mediation, and Sealed Artifact Promotion  
> **Target Audience**: AstraRun Core Engineering, Adversarial Windows Security Audit, Architecture Review  
> **Audit Date**: 2026-10-07  
> **Status**: PASS WITH EMPIRICAL ARCHITECTURE ESCAPE HATCH CLASSIFICATION  

---

## 1. Executive Summary & Verdict

Phase C2 demonstrated that Windows Restricted Tokens combined with Low Integrity Level (`Low IL`) and Win32 Job Objects provide robust filesystem write protection and process containment, but leave three fundamental security gaps open against untrusted generated code:
1. **Confidentiality Gap**: Low IL processes can read Medium IL files (such as user Documents, SSH keys, browser profiles).
2. **Network Exfiltration Gap**: Low IL retains full Winsock network capabilities.
3. **Process Control Gap**: Low IL retains the ambient user SID, allowing `OpenProcess(PROCESS_TERMINATE)` against other processes owned by the same user.

Phase **C2.1** implemented and empirically verified **AppContainer Capability Isolation** (`AppContainerLauncher`) alongside **Authoritative ExecutionBroker Mediation** and **Sealed Artifact Promotion**.

### Key Audit Findings:
- **Zero Ambient Token Authority**: Untrusted generated Python code executed under `AppContainerLauncher` operates with a dedicated package SID (`S-1-15-2-...`) and zero ambient capability SIDs.
- **Confidentiality Enforced**: Reads to host user `Documents`, `Desktop`, and configuration files fail with `PermissionError: [Errno 13] Permission denied`.
- **Integrity Enforced**: Writes outside the ephemeral governed workspace fail with `PermissionError: [Errno 13] Permission denied`.
- **Network Exfiltration Blocked**: Raw TCP/UDP socket creation fails with `PermissionError: [WinError 10013] WSAEACCES` (offline by default).
- **Process Control Blocked**: Same-user process termination fails with `PermissionError: [WinError 5] Access is denied`.
- **Grandchild Containment Enforced**: Win32 Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` is assigned before the initial thread is resumed, guaranteeing no orphaned processes escape.
- **Empirical Architecture Escape Hatch**: Standard Python standard library and NumPy data processing execute cleanly. However, GUI/GDI C-extensions (specifically `matplotlib`'s `_c_internal_utils.pyd`) fail under AppContainer due to Windows Win32k system call filtering (`DLL load failed: An internal error occurred`). In strict compliance with the C2.1 charter, this incompatibility is classified honestly without weakening security.

---

## 2. Workstation Baseline & Verification Context

All empirical measurements and test executions were conducted on the reference physical workstation:

| Parameter | Measured Specification |
|---|---|
| **Operating System** | Windows 11 Build 26200 (AMD64, `Windows-11-10.0.26200-SP0`) |
| **Python Runtime** | Python 3.13.0 64-bit (`MSC v.1941 64 bit (AMD64)`) |
| **Active Virtualenv** | `E:\Workspace\Active\AstraRun\.venv\Scripts\python.exe` |
| **Base Python Prefix** | `C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe` |
| **UAC Configuration** | `EnableLUA = 1`, `ConsentPromptBehaviorAdmin = 5` (UAC actively enforced) |
| **Caller Token Elevation** | `IsUserAnAdmin() == False` (Standard non-elevated user token) |
| **Hardware** | Intel Core i5-12450H CPU, 16 GB RAM, NVIDIA GeForce RTX 2050 GPU (4 GB VRAM) |
| **Composite Source Tree SHA-256** | `60e818e7c4c80a2a37a47769879b160a391573e045223e70ec20a17b0ad805b2` (269 files) |

---

## 3. Architecture & Implementation of C2.1

### 3.1 AppContainerLauncher (`src/astrarun/sandbox/appcontainer_launcher.py`)

The C2.1 container launcher leverages Windows User Environment APIs and kernel process attributes:
1. **Profile Lifecycle**: Ephemeral container profiles (`CreateAppContainerProfile` / `DeleteAppContainerProfile`) generate an isolated package SID (`S-1-15-2-...`) per task run.
2. **Zero Ambient Capabilities**: The launcher passes `CapabilityCount = 0` and `Capabilities = NULL`, establishing an offline-by-default execution environment.
3. **Suspended Process Creation**: Processes are spawned with `CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW`.
4. **Attribute Configuration**: `InitializeProcThreadAttributeList` configures both `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` (AppContainer token) and `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` (inheriting only the anonymous I/O pipe write handle).
5. **Pre-Resume Job Object Assignment**: The suspended process handle is assigned to a `Win32JobObject` configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and strict memory limits before `ResumeThread` is called.
6. **Kernel Environment Constraint Resolution**: Windows `CreateProcessW` returns `WinError 203` (`ERROR_ENVVAR_NOT_FOUND`) if a custom `lpEnvironment` block is supplied alongside `SECURITY_CAPABILITIES`. Resolved by passing `lpEnvironment=None` and using an ephemeral bootstrap runner (`_ac_bootstrap.py`) staged inside the task workspace to scrub host secrets and inject governed paths (`ASTRARUN_OUTPUT_DIR`, `MPLCONFIGDIR`, etc.) prior to entrypoint execution.
7. **Deterministic Teardown**: `finally` blocks guarantee pipe handle closure, attribute list deletion, container profile deletion, and ACL revocation.

### 3.2 Authoritative ExecutionBroker Mediation (`src/astrarun/security/execution_broker.py`)

Every consequential system mutation is mediated through `ExecutionBroker -> ActionGate`:
- `TaskManager.execute_capability` routes all capability executions through `ExecutionBroker.execute(ActionProposal(...))` with fail-closed return on blocked or confirm verdicts.
- Dynamic artifact promotion in `DynamicToolBuilder.deliver_artifact_via_broker` synthesizes an `ActionProposal(category=ACT, capability_id="deliver_artifact")`, ensuring host filesystem writes pass policy gates.
- Side-effect-free dry-run enforcement: In `src/astrarun/app.py`, fast-path, single-step, and multi-step workflows verify `dry_run=True` and eliminate any fall-through to physical execution.

### 3.3 Sealed Artifact Promotion (`src/astrarun/files/service.py`)

The artifact delivery pipeline enforces cryptographic and filesystem boundary checks:
- **Hard Link Rejection**: `get_file_link_count(path)` queries `BY_HANDLE_FILE_INFORMATION.nNumberOfLinks` and rejects any file with link count `> 1` to prevent multi-link TOCTOU mutations.
- **Path Sanitization**: `validate_safe_path(path)` rejects device namespaces (`\\.\`, `\\?\`, `\??\`), NTFS Alternate Data Streams (`:`), UNC network paths (`\\`), and reserved DOS filenames (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`).
- **Cryptographic Match & Atomic Commit**: Streaming SHA-256 chunk verification confirms source integrity against declared hash before writing to a temporary file in the target directory and committing via atomic `os.replace`.

---

## 4. Empirical Security & Isolation Comparison Matrix

The following matrix compares empirical results obtained on Windows 11 Build 26200:

| Security / Workload Dimension | Probe Description | C2 Restricted Token (Low IL) | C2.1 AppContainer |
|---|---|---|---|
| **Confidentiality** (Documents Read) | Read synthetic canary in `C:\Users\hp\Documents` | **ALLOWED** (`CONFIRMED_GAP`) — Low IL permits read-up | **BLOCKED** — `PermissionError: [Errno 13] Permission denied` |
| **Integrity** (Desktop Write) | Write file to `C:\Users\hp\Desktop` | **BLOCKED** — NTFS MIC `No-Write-Up` | **BLOCKED** — `PermissionError: [Errno 13] Permission denied` |
| **Network Exfiltration** | Outbound TCP connection to `1.1.1.1:53` | **ALLOWED** (`CONFIRMED_GAP`) — Winsock unconstrained | **BLOCKED** — `PermissionError: [WinError 10013] WSAEACCES` |
| **Process Control** | `OpenProcess(PROCESS_TERMINATE)` on same-user process | **ALLOWED** (`CONFIRMED_GAP`) — User SID matches host | **BLOCKED** — `PermissionError: [WinError 5] Access is denied` |
| **Process Tree Containment** | Terminate parent worker with running grandchild | **ENFORCED** — Job Object kills grandchildren | **ENFORCED** — Job Object assigned pre-resume kills grandchildren |
| **Governed Workspace** | Write output files to task directory | **ALLOWED** — AppData/LocalLow writable | **ALLOWED** — Task workspace writable via ephemeral ACL |
| **Workload: Python StdLib** | Arithmetic, JSON, CSV parsing | **ALLOWED** — Clean execution | **ALLOWED** — Clean execution (Exit Code 0) |
| **Workload: NumPy** | Array math, matrix linear algebra | **ALLOWED** — Clean execution | **ALLOWED** — Clean execution (Exit Code 0, sum=10) |
| **Workload: Matplotlib** | Render plot to PNG via headless Agg | **ALLOWED** — Clean execution | **BLOCKED** — `ImportError: DLL load failed while importing _c_internal_utils: An internal error occurred` |

---

## 5. Workload Compatibility & Architecture Escape Hatch

In accordance with the C2.1 charter:
> *If running standard Python under AppContainer requires broad ACL grants or fails due to system call filtering (e.g. Win32k/GDI), classify compatibility honestly, halt untrusted execution, and compare alternative isolation mechanisms.*

### 5.1 Compatibility Classification

1. **Pure Python & Standard Library (`NATIVE_COMPATIBLE`)**:
   Standard algorithms, text transformation, JSON/CSV parsing, and mathematical calculations execute with zero permission friction under AppContainer.
2. **NumPy & Numerical Computing (`NARROW_RUNTIME_LAYOUT_REQUIRED`)**:
   Numerical computation runs cleanly provided the active virtual environment has `(RX)` permissions granted to the AppContainer package SID.
3. **Matplotlib & Win32k GUI/GDI Extensions (`MATERIAL_SECURITY_GRANT_REQUIRED / FUNDAMENTALLY_INCOMPATIBLE`)**:
   Matplotlib's compiled extension `_c_internal_utils.cp313-win_amd64.pyd` imports `USER32.dll`, `GDI32.dll`, and `SHELL32.dll`. Under Windows AppContainer, Win32k system call filtering blocks these subsystems for non-packaged processes, returning `An internal error occurred`.

### 5.2 Comparative Analysis of Stronger Primitives

To execute workloads requiring full Win32k/GDI capabilities or arbitrary compiled extensions without exposing host authority, two stronger alternatives are evaluated:

| Primitive | Threat Model / Isolation Guarantee | Performance / Latency | Implementation Complexity |
|---|---|---|---|
| **AppContainer (C2.1 Implemented)** | OS capability boundary; blocks network, credentials, and processes. Zero ambient token. | Very fast (~200ms process startup). Low memory overhead. | Native Win32 APIs; requires Win32k-compatible headless libraries. |
| **Dedicated Restricted Worker Account** (`AstraWorker`) | Separate Windows local user account with independent `C:\Users\AstraWorker` profile. Zero access to operator files/registry. Unrestricted Win32k/GDI rendering for headless plotting. | Fast (~300ms startup via `CreateProcessWithLogonW` or secondary service). | Requires one-time setup of local service account and credential management. |
| **Windows Sandbox / Hyper-V Container** | Hardware-virtualized hypervisor partition. Complete OS kernel, driver, and filesystem isolation. Native GPU partitioning. | Higher latency (5–10s cold start). Higher memory footprint (~1 GB). | Requires Hyper-V feature enabled; container management agent. |

**Recommendation**: Retain AppContainer as the primary sandbox for dynamic computational, algorithmic, and data manipulation tasks. For workloads requiring complex visualization or native desktop libraries, route execution through a dedicated restricted local worker account or containerized environment.

---

## 6. Comprehensive Test Suite Verification

All relevant test suites were executed against the active virtual environment runtime:

| Suite Name | Scope | Results | Status |
|---|---|---|---|
| `test_post_freeze_routing_holdout.py` | 70 unseen post-freeze intent routing prompts | 70/70 Passed (0 regressions) | **PASS** |
| `test_generic_repair_holdout.py` | 8 real local Qwen code synthesis & autonomous repair cycles | 8/8 Passed (100% causal model inference) | **PASS** |
| `test_milestone7b_dynamic_tooling.py` | Dynamic tool builder pipeline, AST safety, AppContainer execution, skill promotion | 9/9 Passed | **PASS** |
| `test_c2_adversarial_suite.py` | 30 adversarial isolation scenarios (Restricted Token baseline comparison) | 30/30 Passed | **PASS** |
| `tests/unit/` (Full Suite) | AST differential security, broker authority, paths, memory, routing | 52/52 Passed (1 deselected holdout) | **PASS** |
| `test_self_repair.py` | Bounded repair ceiling & CodeProvenance revision tracking | 2/2 Passed | **PASS** |

---

## 7. Source Tree Integrity & Cryptographic Freeze

- **Repository HEAD**: `f4e5d06`
- **Tracked Files Modified**:
  - `src/astrarun/sandbox/appcontainer_launcher.py` (New native AppContainer launcher)
  - `src/astrarun/sandbox/models.py` (Extended configuration and diagnostics)
  - `src/astrarun/sandbox/manager.py` (Integrated AppContainerLauncher with fail-closed semantics)
  - `src/astrarun/security/execution_broker.py` (Added `raw_result` support)
  - `src/astrarun/tasks/manager.py` (Mandatory broker routing for capabilities)
  - `src/astrarun/app.py` (Broker injection and side-effect-free dry-run)
  - `src/astrarun/files/service.py` (Hard link rejection and atomic artifact delivery)
  - `src/astrarun/tools/candidate.py` (Code cleaning and `derive_repaired` support)
  - `src/astrarun/tools/dynamic_builder.py` (Robust repair error extraction)
  - `src/astrarun/cognition/service.py` (Unclosed fence extraction and prompt precision)
- **Production File Count**: 269 Python files in `src/astrarun`
- **Composite Production SHA-256**: `60e818e7c4c80a2a37a47769879b160a391573e045223e70ec20a17b0ad805b2`

---

## 8. Verification Sign-Off

Phase C2.1 successfully achieves capability isolation for generated dynamic workers, eliminates ambient user token inheritance, enforces fail-closed broker mediation, and secures artifact promotion. In accordance with strict instructions, no packaging, installer, or dogfooding steps were taken.
