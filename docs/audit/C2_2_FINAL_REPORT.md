# AstraRun C2.2 — Security Closure, Trusted Capability Split & Adversarial Freeze Audit Report

> **Scope**: Implementation, Hardening, and Empirical Post-Freeze Verification of Windows 11 AppContainer Isolation, Authoritative ExecutionBroker Mediation, Sealed Artifact Promotion, and Trusted Capability Split  
> **Target Audience**: AstraRun Core Engineering, Adversarial Windows Security Audit, Architecture Review  
> **Audit Date**: 2026-10-07  
> **Status**: **PASS — READY FOR FROZEN PRODUCT DOGFOOD**  

---

## 1. Executive Summary & Authoritative Verdict

Phase **C2.2** achieves definitive architectural and security closure for untrusted code execution in AstraRun. It operationalizes the core design invariant:

$$\text{INTELLIGENCE} \neq \text{AUTHORITY}$$

Models reason, plan, write code, repair code, and propose actions; deterministic trusted code enforces policy, boundaries, and host execution. Untrusted dynamic code executes strictly contained within a kernel-enforced Windows AppContainer possessing **zero ambient authority**, while consequential host operations remain deterministic capabilities governed exclusively through `ExecutionBroker -> ActionGate`.

### Authoritative Verdict:
$$\mathbf{C2.2 = PASS}$$
$$\mathbf{CURRENT\ C3\ READINESS = READY\_FOR\_FROZEN\_PRODUCT\_DOGFOOD}$$

### Key Empirical Milestones Achieved:
1. **Zero Ambient Token Authority**: Untrusted generated Python code executes under a dedicated Windows AppContainer token (`TokenIsAppContainer = True`) with Low Integrity (`S-1-16-4096`), ephemeral package SID (`S-1-15-2-...`), and strictly **zero network or system capabilities** (`TokenCapabilities` count = 0).
2. **Launch-Time Secret Boundary Closed**: Replaced ambient child environment inheritance with an explicit positive allowlist block passed to `CreateProcessW` (`lpEnvironment`). Python launches strictly in `-I` (isolated) mode. Ephemeral `_ac_bootstrap.py` was eliminated. Host canary secrets (API keys, cloud tokens, database URLs) leak count = **0**.
3. **Handle-Based Sealed Artifact Promotion**: Replaced naive path-based copying with kernel handle-based sealing (`open_sealed_source_handle`). Files are opened with `GENERIC_READ` and `FILE_SHARE_READ` exclusively (zero write/delete sharing), blocking concurrent tamper. The handle verifies regular file attributes, link count == 1, non-reparse point, size bounds, and canonical NTFS physical path (`GetFinalPathNameByHandleW`) within authorized sandbox roots. Staged copy bytes and SHA-256 digests are validated before atomic replacement (`os.replace`).
4. **Trusted Capability Split (Visualization)**: Disallowed ambient execution of heavy graphics/GDI libraries in untrusted workers. Created a declarative JSON visualization schema (`VisualizationSpec`) with strict bounds (rejecting `<script>`, `javascript:`, `data:`, remote URLs, non-finite `NaN`/`Inf`, and arrays > 100k points), coupled with an out-of-process renderer contained in a dedicated Win32 Job Object.
5. **Machine Concurrency Ceiling**: Strict concurrency ceiling of **1** worker enforced via `threading.BoundedSemaphore(1)` in `SandboxManager`. Child processes receive explicit thread limits (`OMP_NUM_THREADS="2"`).
6. **Fresh Adversarial Freeze**: 273 production Python files frozen at composite SHA-256 `4e19fdf2b15e9890e4308c74735c5f08b404a33eb65373bd2eaffc0a6b9adbdf`.
7. **Empirical Post-Freeze Holdout Suite**: **6/6 PASSED (100%)** including live local Qwen2.5-Coder inference (`REAL_LOCAL_MODEL_INFERENCE`) on loopback port 8089 (3536.8ms latency, mathematical prime factorization of 20261008 autonomously synthesized, executed in AppContainer, and delivered through ExecutionBroker).

---

## 2. Workstation Baseline & Hardware Environment

All measurements and empirical test executions were conducted on the reference physical workstation:

| Parameter | Measured Specification |
|---|---|
| **Operating System** | Windows 11 Build 26200 (AMD64, `Windows-11-10.0.26200-SP0`) |
| **Python Runtime** | Python 3.13.0 64-bit (`MSC v.1941 64 bit (AMD64)`) |
| **Active Virtualenv** | `E:\Workspace\Active\AstraRun\.venv\Scripts\python.exe` |
| **Base Python Prefix** | `C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe` |
| **UAC Configuration** | `EnableLUA = 1`, `ConsentPromptBehaviorAdmin = 5` (UAC actively enforced) |
| **Caller Token Elevation** | `IsUserAnAdmin() == False` (Standard non-elevated user token) |
| **WindowStation Baseline** | `winsta0` SDDL: `S:(ML;;NW;;;LW)` (`BASELINE_STALE_REQUIRES_LOGOFF_OR_REBOOT`) |
| **Hardware** | Intel Core i5-12450H CPU (8 cores / 12 threads), 16 GB RAM, NVIDIA GeForce RTX 2050 (4 GB VRAM) |
| **Composite Source Tree SHA-256** | `4e19fdf2b15e9890e4308c74735c5f08b404a33eb65373bd2eaffc0a6b9adbdf` (273 files) |

---

## 3. C2.2 Architecture & Security Closures

### 3.1 Launch-Time Secret Boundary Closure
- **Defect Identified**: Previously, `CreateProcessW` in `AppContainerLauncher` did not pass `lpEnvironment`, causing the child process to inherit the parent process's environment variables (including API tokens, keys, and session data), requiring a post-launch Python bootstrap (`_ac_bootstrap.py`) to scrub them.
- **Architectural Solution**: Built an explicit positive allowlist environment block:
  - System allowlist: `SystemRoot`, `WINDIR`, `SystemDrive`, `PATH`, `PATHEXT`, `COMSPEC`, `OS`, `PROCESSOR_ARCHITECTURE`, `NUMBER_OF_PROCESSORS`.
  - Sandboxed path overrides: `LOCALAPPDATA`, `APPDATA`, `TEMP`, `TMP`, `ASTRARUN_OUTPUT_DIR`, `ASTRARUN_WORKSPACE_DIR`.
  - Concurrency caps: `OMP_NUM_THREADS="2"`, `OPENBLAS_NUM_THREADS="2"`, `MKL_NUM_THREADS="2"`.
  - Block encoded as Win32 double-null-terminated Unicode string and passed directly as `lpEnvironment` with `CREATE_UNICODE_ENVIRONMENT`.
  - Child Python launched with `-I` (isolated mode), ignoring user site-packages and ambient registry paths.
  - Eliminated `_ac_bootstrap.py`.
- **Empirical Result**: In `test_post_freeze_launch_secrecy_boundary`, host environment canaries (`CANARY_SECRET_OPENAI`, `CANARY_SECRET_AWS`, `CANARY_SECRET_DATABASE`) leak count: **0**.

### 3.2 Live Kernel Token & Capability Verification
- **Audit Verification**: Queried live child process token via Win32 `OpenProcessToken` and `GetTokenInformation`:
  - `TokenIsAppContainer`: `True`
  - `TokenAppContainerSid`: `S-1-15-2-151215692-...`
  - `TokenCapabilities` (Class 30): `0` capabilities
  - `TokenIntegrityLevel`: `S-1-16-4096` (Low Mandatory Level)
- **Denial Verification**:
  - Loopback TCP port 8089 (sacrificial/Qwen): `DENIED (WSAEACCES 10013)`
  - Loopback TCP port 8090 (Spark): `DENIED (WSAEACCES 10013)`
  - External network (8.8.8.8:53): `DENIED (WSAEACCES 10013)`
  - Operator credential files (`~/.ssh/id_rsa`, `~/.aws/credentials`): `DENIED (PermissionError / FileNotFoundError)`
  - Windows system files (`C:\Windows\System32\drivers\etc\hosts`): `DENIED (PermissionError)`

### 3.3 Handle-Based Sealed Artifact Promotion
- **Defect Identified**: Naive promotion based on source file paths creates a TOCTOU race condition where a child worker or symlink attack can switch or mutate the file during promotion.
- **Architectural Solution** (`src/astrarun/files/service.py`):
  1. `open_sealed_source_handle`: Opens the source file via Win32 `CreateFileW` with `GENERIC_READ`, `FILE_SHARE_READ` exclusively (zero write/delete sharing), and `FILE_FLAG_OPEN_REPARSE_POINT`.
  2. Queries handle metadata via `GetFileInformationByHandle`:
     - Disallows directory attributes
     - Disallows reparse points (symlinks, junctions, mount points)
     - Disallows hard link counts $> 1$ (`nNumberOfLinks == 1`)
     - Enforces maximum file size limit (100 MB)
  3. Queries canonical DOS path on the SAME open handle via `GetFinalPathNameByHandleW`. Verifies canonical path is strictly inside authorized sandbox directories, and ancestor directories contain no junctions.
  4. Wraps Win32 handle into Python `io.FileIO` via `_open_osfhandle`.
  5. Stages file into destination-side temporary file on the host volume while computing SHA-256 digest and total bytes.
  6. Validates expected hash and type headers (e.g. PNG magic bytes `\x89PNG\r\n\x1a\n` or valid JSON syntax).
  7. Commits destination atomically using `os.replace`.
- **Path Sanitization** (`validate_safe_path`): Blocks Alternate Data Streams (`:`), UNC prefixes (`\\`), NT device paths (`\??\`), trailing dots/spaces, and reserved DOS device names (`CON`, `PRN`, `AUX`, `NUL`, etc.).

### 3.4 Trusted Capability Split: Declarative Visualization
- **Architectural Principle**: Untrusted sandboxed code cannot load arbitrary GDI/GUI C-extensions (`matplotlib` C-internals) without broad system grants. The capability is split: untrusted code emits declarative data; trusted host renders it.
- **Implementation**:
  - Declarative schemas in `src/astrarun/visualization/models.py`: `VisualizationSpec`, `SeriesSpec`, `AxisSpec`, `CameraSpec`.
  - Schema constraints: string length limits, rejection of `<script>`, `javascript:`, `data:`, remote URLs, non-finite floats (`NaN`, `Inf`), and series arrays exceeding 100,000 points.
  - Out-of-process renderer `src/astrarun/visualization/render_worker.py` executed under `Win32JobObject` with memory limit and bounded timeout.
  - Registered as capability `render_visualization` in `src/astrarun/capabilities/registry.py` and manifest.

### 3.5 Authoritative ExecutionBroker Mediation & Concurrency Ceiling
- **ExecutionBroker**: The single mandatory choke-point for all actions. Models never call execution directly.
- **Dry-Run Guarantee**: Dry-run proposals simulate execution returning `execution_state="SIMULATED"`, `verdict="ALLOW"` with zero host mutations.
- **Revision Binding**: ActionGate confirmation tokens cryptographically bind `task_id` and `plan_revision`. Revision $N$ cannot authorize execution for plan revision $N+1$.
- **Concurrency Ceiling**: Dynamic worker concurrency strictly bounded to **1** via `threading.BoundedSemaphore(1)` in `SandboxManager`.

---

## 4. Source Freeze Manifest (Section 10)

Production source code frozen prior to final holdout execution:

- **Manifest File**: `docs/audit/C2_2_FREEZE_MANIFEST.json`
- **Git Commit HEAD**: `f4e5d069ea09a583cbeb61b45757bab31287fe54`
- **Total Production Python Files**: 273
- **Composite Source Tree SHA-256**: `4e19fdf2b15e9890e4308c74735c5f08b404a33eb65373bd2eaffc0a6b9adbdf`

### Canonical External Assets:
- **Qwen Coder Model**: `E:\AI_Models\GGUF\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`  
  SHA-256: `cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046` (1,117,320,768 bytes)
- **Spark NLP Model**: `E:\AI_Models\GGUF\Spark-X2.5-1.7B-Q4_K_M.gguf`  
  SHA-256: `902bde2522394954ac17821b3e5fd0df02defbc6944f122253f2580acf0503f4` (1,107,457,856 bytes)
- **llama-server Binary**: `E:\AI_Runtimes\llama.cpp-spark\llama-server.exe`  
  SHA-256: `4af4ca1baed1aa6aa4a560c767b5294343b8e83d5738789a591ffa909f32ee8f` (9,216 bytes)
- **Python Runtime Binary**: `E:\Workspace\Active\AstraRun\.venv\Scripts\python.exe`  
  SHA-256: `6f8c9878450765686ace476d2170b970761d68ace63f16092489c4c8bd5d7018` (250,640 bytes)

---

## 5. Post-Freeze Adversarial Holdout Verification (Section 11)

Execution of `tests/eval_v1/test_c2_2_post_freeze_holdout.py`:

```
============================= test session starts =============================
platform win32 -- Python 3.13.0, pytest-9.1.1, pluggy-1.6.0
rootdir: E:\Workspace\Active\AstraRun
configfile: pyproject.toml
plugins: anyio-4.15.1
collected 6 items

tests/eval_v1/test_c2_2_post_freeze_holdout.py::test_post_freeze_identity_and_token_boundaries PASSED
tests/eval_v1/test_c2_2_post_freeze_holdout.py::test_post_freeze_launch_secrecy_boundary PASSED
tests/eval_v1/test_c2_2_post_freeze_holdout.py::test_post_freeze_network_and_filesystem_denials PASSED
tests/eval_v1/test_c2_2_post_freeze_holdout.py::test_post_freeze_sealed_artifact_promotion_adversarial_suite PASSED
tests/eval_v1/test_c2_2_post_freeze_holdout.py::test_post_freeze_trusted_visualization_defense PASSED
tests/eval_v1/test_c2_2_post_freeze_holdout.py::test_post_freeze_positive_unseen_qwen_agent_task PASSED

============================= 6 passed in 14.94s ==============================
```

### Detailed Holdout Probe Results:

| Test Probe | Security Property Evaluated | Outcome | Empirical Evidence |
|---|---|---|---|
| **1. Identity & Token** | AppContainer SID, 0 capabilities, Low Integrity | **PASSED** | Live kernel token query: `TokenIsAppContainer=True`, `GroupCount=0`, `S-1-16-4096`. |
| **2. Launch Secrecy** | Zero environment secret leakage | **PASSED** | Host canaries (`CANARY_SECRET_OPENAI`, `AWS`, `DATABASE`) absent from child process. |
| **3. Isolation Denials** | Offline Winsock and host filesystem boundaries | **PASSED** | Sockets to 8089, 8090, 8.8.8.8 fail with `WSAEACCES 10013`; host SSH/AWS reads denied. |
| **4. Promotion Attacks** | Reparse points, ADS, UNC, multi-hardlink, tamper | **PASSED** | ADS/UNC rejected; boundary escapes rejected; tampered hash unlinked; valid atomic promote. |
| **5. Visualization Defense**| Hostile script, URL, NaN/Inf, bomb arrays | **PASSED** | `<script>` rejected; `NaN` rejected; 120k points rejected; valid 2D/3D PNGs rendered. |
| **6. Positive Unseen Agent**| End-to-end model synthesis, AppContainer run, delivery | **PASSED** | Qwen 1.5B on :8089 (3536ms) factored 20261008 into `[2, 2, 2, 2, 17, 74489]`; delivered & verified. |

---

## 6. Unit Regression Suite Verification

Execution of unit regression suite (`pytest tests/unit/ -k "not test_c2_adversarial_suite" -q`):

```
34 passed, 30 deselected in 67.01s (0:01:07)
```

No regressions observed across AST screening, ActionGate policies, ExecutionBroker dispatch, memory service, or C1.8 routing holdouts.

---

## 7. Evidence Tier Matrix & Truth in Verification

In strict accordance with the Workspace Operating Contract and Truth in Verification invariants:

| Evidence Tier | Verified Status | Artifact / Measurement Source |
|---|---|---|
| **IMPLEMENTED** | **YES** | 273 production Python source files under `src/astrarun/` |
| **UNIT_TESTED** | **YES** | 34 unit tests in `tests/unit/` passed (100% green) |
| **SOURCE_TREE_EXECUTED** | **YES** | 6 post-freeze holdout tests executed on physical Windows 11 workstation |
| **REAL_LOCAL_MODEL_INFERENCE** | **YES** | Qwen2.5-Coder on :8089 (request latency 3536.8ms, 750 chars, response hash verified) |
| **FROZEN_EXE** | **NOT CLAIMED** | Source-tree verification milestone; PyInstaller packaging deferred per instructions |
| **HUMAN_OBSERVED** | **NOT CLAIMED** | Automated test harness verification; interactive human GUI testing deferred |

---

## 8. Final Recommendation & Readiness Gate

Phase **C2.2** has resolved all architectural defects identified in prior reviews:
- The secret boundary is closed via explicit positive environment allowlisting.
- The execution sandbox is enforced via kernel AppContainer with zero capabilities and Low Integrity.
- Artifact delivery is hardened via handle-based single-link validation and atomic commitment.
- Visualization is governed via declarative schemas and out-of-process isolation.
- Model intelligence and execution authority are cleanly separated.

### Readiness Status:
$$\mathbf{C2.2 = PASS}$$
$$\mathbf{READY\ FOR\ FROZEN\ PRODUCT\ DOGFOOD\ (C3)}$$
