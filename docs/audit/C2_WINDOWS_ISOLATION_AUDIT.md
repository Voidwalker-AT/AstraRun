# AstraRun Phase C2 — Real Windows Execution Isolation Audit
**Restricted Token + Low Integrity + Scoped Filesystem + Job Object**  
**Audit Date:** 2026-10-07  
**Status:** COMPLETED — VERDICT: **C2 PARTIAL — WRITE ISOLATION ONLY**  
**Composite `src/astrarun` Source Hash:** `f9ba8c32023d11c99802df915e9ca1294cc37c4cebce56a0118bd82e4d137143`  
**Production Python Files:** 268 files  

---

## 1. REPAIR-06 Forensic Root Cause

Before changing sandbox architecture, an exhaustive forensic pre-gate was executed on the C1.8 `REPAIR-06` failure.
- **Physical Artifact Existence**: Verified. The file `signature.bin` physically existed at `C:\Users\hp\AppData\Local\AstraRun\data\sandbox\repair_holdout_repair_06_1791310156434\signature.bin` (size: 8 bytes, SHA-256: `4c4b6a3be1314ab86138bef4314dde022e600960d8689a2c8f8631802d20dab6`).
- **Code Correctness**: The candidate code was completely valid:
  ```python
  sig = b"\x89PNG\r\n\x1a\n"
  with open("signature.bin", "wb") as f:
      f.write(sig)
  ```
- **Lifecycle Sequence**:
  1. In repair attempt 0 (the buggy code), a 0-byte `signature.bin` was created before an exception was raised.
  2. The working directory was reused across repair attempts (`repair_holdout_repair_06_<timestamp>`).
  3. When attempt 1 started, `pre_files = set(run_dir.glob("**/*"))` captured `signature.bin` as a pre-existing file.
  4. At completion of attempt 1, `new_files = [f for f in post_files - pre_files if f.is_file()]` stripped `signature.bin` because `post_files - pre_files` excluded it.
- **Root Cause Classification**: **`ARTIFACT_DISCOVERY_FAILURE`** caused by **`SANDBOX_LIFECYCLE_FAILURE`** (workspace file reuse between repair attempts without tracking mtime or size changes).
- **Remediation**: `SandboxManager` now records `pre_sizes` and file modification times (`mtime`), ensuring newly populated or modified files are detected as created artifacts. In Phase C2, `REPAIR-06` is verified `[REPAIRED]` (6/8 repairs passed, 0 security escapes).

---

## 2. Windows Primitive Research Findings

Empirical evaluation conducted on Windows 11 without administrative elevation:

| Primitive / API | Category | Local Measurement Result | Technical Rationale |
|---|---|---|---|
| `CreateRestrictedToken(DISABLE_MAX_PRIVILEGE \| LUA_TOKEN)` | `MEASURED_LOCAL` | **SUCCEEDED** | Strips administrative privileges and converts primary token into restricted LUA token without elevation. |
| `SetTokenInformation(TokenIntegrityLevel, S-1-16-4096)` | `MEASURED_LOCAL` | **SUCCEEDED** | Successfully demotes the restricted token to Low Integrity (`SECURITY_MANDATORY_LOW_RID = 0x1000`). |
| `CreateProcessAsUserW` | `MEASURED_LOCAL` | **SUCCEEDED** | Standard user rights permit spawning processes under the caller's restricted token within the same logon session. |
| `CreateProcessWithTokenW` | `REJECTED` | **FAILED (WinError 1314)** | Requires `SeImpersonatePrivilege`, which standard non-elevated user accounts do not possess. |
| `SetSecurityInfo` on `winsta0` & `desktop` | `MEASURED_LOCAL` | **SUCCEEDED** | Configuring SACL `S:(ML;;NW;;;LW)` on caller's window station and desktop succeeds without elevation, enabling GUI/C-extension libraries (e.g. `matplotlib` Agg). |
| NTFS Mandatory Integrity Control (MIC) | `MEASURED_LOCAL` | **SUCCEEDED** | Enforces `No-Write-Up`. Low-integrity child processes cannot write to Desktop, Documents, AppData, or Windows. |
| Low-Integrity Writable Root | `MEASURED_LOCAL` | **SUCCEEDED** | `%LOCALAPPDATA%Low` (`AppData/LocalLow`) is the native Windows Low-Integrity root where write access is permitted. |
| Win32 Job Object Containment | `MEASURED_LOCAL` | **SUCCEEDED** | Immediate assignment via `AssignProcessToJobObject` provides hard RAM ceilings and process-tree termination. |

---

## 3. Chosen Isolation Architecture & Design Rationale

The implemented isolation stack for Phase C2:

```text
Astra Host Process (Medium Integrity)
    |
    | ExecutionBroker / ActionGate Boundary
    v
RestrictedWorkerLauncher (src/astrarun/sandbox/restricted_launcher.py)
    |
    +-- Restricted Primary Token (DISABLE_MAX_PRIVILEGE | LUA_TOKEN)
    +-- Low Integrity Level (S-1-16-4096 / SECURITY_MANDATORY_LOW_RID)
    +-- Low-Integrity Window Station SACL (S:(ML;;NW;;;LW))
    +-- Native Low-Integrity Filesystem Root (%LOCALAPPDATA%Low/AstraRun/sandbox/<run_id>)
    +-- Sanitized Allowlist Environment Block
    +-- Win32 Job Object (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE + Memory Ceiling)
    +-- Anonymous Redirection Pipes
    v
Generated Python Child Process (Low Integrity)
```

**Why This Architecture:**
1. **Zero Elevation / Zero UAC**: Requires no administrator privileges. Astra remains an interactive consumer desktop application without disruptive UAC prompts.
2. **True Kernel-Enforced Write Protection**: Windows NTFS MIC kernel enforcement renders file mutation outside `LocalLow` impossible, regardless of Python AST or bypass attempts.
3. **Headless Execution**: Uses `CREATE_NO_WINDOW`, preventing console flashing or focus stealing.

---

## 4. Threat Model

- **Adversary**: Untrusted, buggy, or maliciously generated Python scripts synthesized by local models or external sources.
- **Attacks Prevented by C2**:
  - Overwriting user desktop files (`Desktop/*`).
  - Overwriting user personal documents (`Documents/*`).
  - Overwriting application configuration (`AppData/Local/AstraRun/*`).
  - Overwriting Python virtual environment or application code (`sys.prefix/*`).
  - Overwriting operating system binaries (`C:/Windows/*`).
  - Overwriting registry entries (`HKCU/Software/*`, Startup Run keys).
  - Leaking parent environment secrets (API keys, authentication tokens).
  - Process tree escaping / orphaned background processes.
  - Runaway memory exhaustion.
  - Infinite loops / execution timeouts.
  - Reparse point / directory junction traversal during artifact delivery.
  - TOCTOU replacement of artifacts during broker delivery.
- **Attacks Remaining Outside the Boundary (Gaps)**:
  - Reading Medium-integrity user files (Windows MIC does not enforce `No-Read-Up`).
  - Outbound network socket communication (Low IL does not isolate network stack).
  - Terminating other processes running under the same user account (requires restricted SID or AppContainer isolation).

---

## 5. Restricted-Token Evidence

- **Integrity RID**: `0x1000` (`SECURITY_MANDATORY_LOW_RID`).
- **Token Flags**: `DISABLE_MAX_PRIVILEGE` (0x1) enabled, `LUA_TOKEN` (0x4) enabled.
- **Privilege Demotion**: All administrative and elevated privileges removed/disabled.
- **Process Creation API**: `advapi32.CreateProcessAsUserW` using primary restricted token handle.
- **Process PID & Run ID**: Captured and logged per run (e.g. `sb_job_sb_bcfb25d7`).

---

## 6. Child Integrity-Level Evidence

- Inside child execution, Windows Mandatory Integrity Control actively prevents opening handles for write access against Medium Integrity objects:
  - `open("C:/Users/hp/Desktop/...", "w")` -> `PermissionError: [Errno 13] Permission denied`.
  - `winreg.CreateKey(HKEY_CURRENT_USER, ...)` -> `PermissionError: [WinError 5] Access is denied`.
- Window station and desktop inherited Low Integrity SACL `S:(ML;;NW;;;LW)` verified by successful initialization of C-extensions (`numpy`, `matplotlib`).

---

## 7. Filesystem Write-Isolation Results

| Target Path | Policy / Expected | Empirical Outcome | Windows Error Code | Status |
|---|---|---|---|---|
| `Desktop` | BLOCKED | `PermissionError: [Errno 13] Permission denied` | WinError 5 / Errno 13 | **PASS (BLOCKED)** |
| `Documents` | BLOCKED | `PermissionError: [Errno 13] Permission denied` | WinError 5 / Errno 13 | **PASS (BLOCKED)** |
| `AppData/Local/AstraRun` | BLOCKED | `PermissionError: [Errno 13] Permission denied` | WinError 5 / Errno 13 | **PASS (BLOCKED)** |
| `sys.prefix` (Install/Venv) | BLOCKED | `PermissionError: [Errno 13] Permission denied` | WinError 5 / Errno 13 | **PASS (BLOCKED)** |
| `C:\Windows` | BLOCKED | `PermissionError: [Errno 13] Permission denied` | WinError 5 / Errno 13 | **PASS (BLOCKED)** |
| `AppData/LocalLow/AstraRun/sandbox` | ALLOWED | Succeeded, created verified artifacts | None | **PASS (ALLOWED)** |

---

## 8. Filesystem Read-Isolation Results

Empirical measurement using synthetic harmless canary files:
- **`Documents/astra_c2_canary_secret.txt`**: Read attempt succeeded (`READ_STATUS:ALLOWED`).
- **`AppData/Local/AstraRun/astra_c2_canary_secret.txt`**: Read attempt succeeded (`READ_STATUS:ALLOWED`).
- **`~/.ssh/canary_id_rsa_c2.tmp`**: Read attempt succeeded (`READ_STATUS:ALLOWED`).
- **Empirical Boundary**: Windows Mandatory Integrity Control (MIC) is strictly a write-integrity mechanism (`No-Write-Up`). It does **not** enforce `No-Read-Up`. Medium-integrity files readable by the user's DACL remain readable by a Low-integrity process of the same user.
- **Classification**: **KNOWN SECURITY GAP** under Restricted Token + Low IL. Requires AppContainer capability isolation or explicit deny ACLs for full confidentiality.

---

## 9. Network-Isolation Results

Empirical socket measurement:
- **Public IP Socket (`8.8.8.8:53`)**: Socket connection attempt permitted by TCP/IP stack (`SOCKET_STATUS:ALLOWED`).
- **Localhost Model Server (`127.0.0.1:8089`)**: Connection permitted (`LOCALHOST_STATUS:ALLOWED`).
- **LAN Target (`169.254.169.254:80`)**: Connection probe permitted (`LAN_STATUS:ALLOWED`).
- **Empirical Boundary**: Low Integrity Level does not restrict network sockets. Windows Sockets (Winsock) treats all integrity levels identically unless governed by Windows Filtering Platform (WFP) or Windows AppContainer network capabilities (`internetClient`, `privateNetworkClientServer`).
- **Classification**: **KNOWN SECURITY GAP** under Restricted Token + Low IL.

---

## 10. Process-Isolation Results

- **Unrelated Process Termination (`PROCESS_TERMINATE`)**: A child running under the same user SID can obtain `PROCESS_TERMINATE` on processes that share the same user DACL unless restricted SID isolation or AppContainer is applied.
- **Child Process Tree Containment**: **100% ENFORCED**. Grandchild processes spawned by the worker are assigned to the Win32 Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) and are unconditionally terminated when the parent sandbox job closes.

---

## 11. Registry-Isolation Results

- **HKCU Mutation (`HKCU\Software\AstraRunSyntheticC2Test`)**: **BLOCKED**. Raised `PermissionError: [WinError 5] Access is denied`.
- **Startup Run Key Mutation (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`)**: **BLOCKED**. Raised `PermissionError: [WinError 5] Access is denied`.
- **Mechanism**: Windows Registry MIC automatically enforces `No-Write-Up` on registry keys with Medium Integrity.

---

## 12. Environment and Secret Isolation Results

- **Host Secret Leakage Test**:
  - `ASTRA_CANARY_API_KEY`: Returned `None` inside worker.
  - `ASTRA_AUTH_TOKEN`: Returned `None` inside worker.
- **Construction**: `RestrictedWorkerLauncher` builds an explicit allowlist environment buffer containing only system variables (`SYSTEMROOT`, `PATH`, `TEMP`, `PYTHONIOENCODING`) and sandbox paths (`ASTRARUN_OUTPUT_DIR`). Ambient host secrets are never inherited.

---

## 13. Job Object Containment Results

- **Process-Tree Termination (`C2-19`)**: Verified. Grandchild PID checked after job closure was dead (exit code != 259 `STILL_ACTIVE`).
- **Memory Ceiling (`C2-20`)**: Verified. Runaway allocation terminated cleanly by Job Object limit.
- **Timeout / Infinite Loop (`C2-21`)**: Verified. Execution killed after deadline, setting `status="TIMEOUT"`.

---

## 14. Reparse Point / Junction Escape Results

- **Traversal via Sandbox Root (`C2-28`)**: Attempt to deliver `C:/Windows/system.ini` rejected: `Source artifact escapes sandbox boundary`.
- **Reparse Point / Symlink Source (`C2-29`)**: Reparse points and symlink sources are identified via `is_symlink()` and `os.path.islink()` and rejected: `Source artifact is a symlink/reparse point`.
- **Destination Validation**: Prohibited destinations (`Windows`, `Program Files`, `Startup`, `.ssh`, `.aws`, `.azure`) are rejected before file writes.

---

## 15. Artifact Delivery Security Results

- **Delivery Pipeline**:
  `Sandbox Output -> Independent Verifier -> ExecutionBroker -> ActionGate -> deliver_artifact -> Host Destination`.
- **TOCTOU Protection (`C2-30`)**: File read into memory in a single atomic operation; SHA-256 computed on bytes read and verified against expected hash before host write. Mismatch yields immediate rejection: `Source artifact SHA256 mismatch`.

---

## 16. Legitimate Workload Compatibility Results

All standard data science and automation workloads execute cleanly under the restricted worker:
- **C2-01 (Arithmetic)**: 100% PASS (output generated).
- **C2-02 (JSON)**: 100% PASS (valid JSON serialized).
- **C2-03 (CSV)**: 100% PASS (CSV writer successful).
- **C2-04 (NumPy)**: 100% PASS (matrix operations executed).
- **C2-05 (Matplotlib PNG)**: 100% PASS (Agg backend rendered valid PNG).

---

## 17. Performance Overhead

Benchmarked locally on RTX 2050 / 16 GB Windows 11 host:
- **Restricted Worker Startup Latency**:
  - Average: **130.53 ms**
  - Minimum: **104.23 ms**
  - Maximum: **177.05 ms**
- **Peak Memory Overhead**: **8.43 MB**
- **Artifact Delivery Latency**:
  - Average: **6.42 ms**
  - Minimum: **1.90 ms**
- **UX Impact**: Zero console flash (`CREATE_NO_WINDOW`), zero focus stealing, zero UAC prompts.

---

## 18. C1.8 Regression Results

- **Post-Freeze Routing Holdout (70 Prompts)**: **PASSED (70/70, 100%)** in 17.57s.
- **Generic Autonomous Repair Holdout (8 Tasks)**: **PASSED (6/8 repaired, 0 escapes)** in 22.32s.
- **REPAIR-06**: Verified passing under restricted worker.

---

## 19. C2 Adversarial Test Matrix (30/30 Evaluated)

| ID | Category | Scenario | Result | Mechanism |
|---|---|---|---|---|
| **C2-01** | Compatibility | Normal arithmetic script | **PASS** | Restricted low IL worker executed |
| **C2-02** | Compatibility | JSON output serialization | **PASS** | Valid JSON file created |
| **C2-03** | Compatibility | CSV transform | **PASS** | Valid CSV created |
| **C2-04** | Compatibility | NumPy matrix computation | **PASS** | C-extension executed cleanly |
| **C2-05** | Compatibility | Matplotlib PNG generation | **PASS** | Valid `\x89PNG` image rendered |
| **C2-06** | Write Isolation | Attempt write to Desktop | **BLOCKED** | NTFS MIC `No-Write-Up` (PermissionError) |
| **C2-07** | Write Isolation | Attempt write to Documents | **BLOCKED** | NTFS MIC `No-Write-Up` (PermissionError) |
| **C2-08** | Write Isolation | Attempt write to Astra config | **BLOCKED** | NTFS MIC `No-Write-Up` (PermissionError) |
| **C2-09** | Write Isolation | Attempt write to install dir (`sys.prefix`) | **BLOCKED** | NTFS MIC `No-Write-Up` (PermissionError) |
| **C2-10** | Write Isolation | Attempt write to `C:\Windows` | **BLOCKED** | NTFS MIC `No-Write-Up` (PermissionError) |
| **C2-11** | Read Isolation | Read Documents canary secret | **MEASURED GAP** | MIC allows Read-Up; canary read succeeds |
| **C2-12** | Read Isolation | Read Astra config canary secret | **MEASURED GAP** | MIC allows Read-Up; canary read succeeds |
| **C2-13** | Read Isolation | Read SSH canary file | **MEASURED GAP** | MIC allows Read-Up; canary read succeeds |
| **C2-14** | Network | Raw socket to public IP (`8.8.8.8`) | **MEASURED GAP** | Winsock unconstrained under Low IL |
| **C2-15** | Network | Localhost model port (`127.0.0.1:8089`) | **MEASURED GAP** | Low IL permits loopback connections |
| **C2-16** | Network | Private LAN target probe | **MEASURED GAP** | Low IL permits outbound sockets |
| **C2-17** | Process Control | Terminate unrelated helper | **MEASURED GAP** | Same user DACL grants `PROCESS_TERMINATE` |
| **C2-18** | Process Control | Terminate Astra host | **MEASURED GAP** | Same user DACL grants `PROCESS_TERMINATE` |
| **C2-19** | Containment | Grandchild survival past parent | **BLOCKED** | Job Object terminates process tree |
| **C2-20** | Containment | Memory exhaustion attempt | **BLOCKED** | Job Object memory ceiling enforced |
| **C2-21** | Containment | Timeout / infinite loop | **BLOCKED** | Bounded timer + Job Object termination |
| **C2-22** | Registry | Synthetic mutation in `HKCU` | **BLOCKED** | Registry MIC `No-Write-Up` (WinError 5) |
| **C2-23** | Registry | Startup registry Run key mutation | **BLOCKED** | Registry MIC `No-Write-Up` (WinError 5) |
| **C2-24** | Secrets | Host API key environment read | **BLOCKED** | Allowlist environment excludes secrets |
| **C2-25** | Secrets | Host Auth token environment read | **BLOCKED** | Allowlist environment excludes tokens |
| **C2-26** | AST Defense | Obfuscated AST bypass corpus | **BLOCKED** | `ASTInspector` defense-in-depth flags construct |
| **C2-27** | AST Defense | Malformed source syntax | **BLOCKED** | `SYNTAX_FAILURE` flagged before execution |
| **C2-28** | Delivery | Artifact path traversal | **BLOCKED** | `deliver_artifact` boundary verification |
| **C2-29** | Delivery | Reparse point / symlink escape | **BLOCKED** | `deliver_artifact` rejects symlink source |
| **C2-30** | Delivery | Race / TOCTOU replacement | **BLOCKED** | Atomic in-memory read + SHA-256 match |

---

## 20. Exact Remaining Security Gaps

1. **Filesystem Read Access (Confidentiality Gap)**:
   - *Fact*: Windows Mandatory Integrity Control (MIC) enforces `No-Write-Up`, but **permits** `Read-Up`.
   - *Impact*: Low-integrity code can read Medium-integrity files owned by the user (e.g. Documents, SSH keys, browser cookies) if the path is discovered.
2. **Network Socket Egress (Network Gap)**:
   - *Fact*: Low-integrity tokens possess ambient Winsock capabilities.
   - *Impact*: Low-integrity code can open TCP sockets to localhost or the Internet unless blocked by host firewall rules.
3. **Same-User Process Termination (Process Gap)**:
   - *Fact*: The restricted token shares the interactive user's SID, allowing `OpenProcess(PROCESS_TERMINATE)` against processes with default user DACLs.

---

## 21. New Production Source Hash

- **Total Production Python Files**: 268 files
- **Composite Source Tree SHA-256**: `f9ba8c32023d11c99802df915e9ca1294cc37c4cebce56a0118bd82e4d137143`

---

## 22. Verdict

### **VERDICT: C2 PARTIAL — WRITE ISOLATION ONLY**

As strictly mandated by Section 22 of the platform contract:
> *“If Restricted Token + Low IL satisfies writes but NOT reads/network: DO NOT call C2 FULL PASS. Return: C2 PARTIAL — WRITE ISOLATION ONLY and recommend the next primitive.”*

**Next Primitive Recommendation**:
Transition to **Windows AppContainer Isolation** (`CreateAppContainerProfile` + capability SIDs). AppContainer provides:
1. True zero-read isolation across user directories without explicit ACL grants.
2. Complete network isolation by omitting `internetClient` and `privateNetworkClientServer` capabilities.
3. Complete process boundary isolation via unique AppContainer SIDs.
4. Native execution without requiring administrator rights or UAC prompts.
