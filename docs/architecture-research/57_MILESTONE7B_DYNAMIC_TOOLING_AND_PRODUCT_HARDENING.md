# Milestone 7B: Governed Dynamic Tooling, Sandbox Containment & Product Engineering Hardening

> **Status**: COMPLETED & VERIFIED ON PHYSICAL WORKSTATION  
> **Target Application**: AstraRun 1.0 Release Candidate  
> **Platform**: Windows 11 Home x64 (Build 26200), NVIDIA GeForce RTX 2050 (4GB VRAM), Python 3.13  
> **Previous Checkpoint**: `88d700c` (tag: `post-milestone-7a`)  
> **Evidence Taxonomy**: Strictly distinguishes `AUTOMATED_ON_PHYSICAL_WORKSTATION`, `HUMAN_INTERACTION_VERIFIED`, `SIMULATED`, and `UNIT_TESTED`.

---

## 1. Executive Summary & Binding Architecture

Milestone 7B establishes the governed dynamic runtime and production-grade software delivery pipeline for AstraRun 1.0. Prior milestones validated resident UI presentation, dual-engine local cognition, multimodal perception, and disturbance recovery. Milestone 7B introduces **governed dynamic tool synthesis** allowing Astra to generate and execute ephemeral Python scripts to solve novel user tasks—while strictly anchoring execution **ABOVE an immutable trust boundary**.

```
+-----------------------------------------------------------------------------------+
|                        ADAPTIVE AGENT LAYER (FLEXIBLE)                            |
|  Planning | Model Routing | Prompt Synthesis | Dynamic Tool Builder | Skills      |
+-----------------------------------------------------------------------------------+
                                         │
                    [Authoritative Trust Boundary Gate]
                                         ▼
+-----------------------------------------------------------------------------------+
|                     NON-SELF-MODIFIABLE TRUST KERNEL                              |
|  ActionGate       SecretBroker      SandboxManager      NetworkBroker             |
|  ResourceGovernor TaskLedger        CapabilityRegistry  UpdateVerifier            |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
|                       OPERATING SYSTEM CONTAINMENT                                |
|  Win32 Job Object | CREATE_NO_WINDOW (0x08000000) | Isolated Temp Workspace       |
+-----------------------------------------------------------------------------------+
```

### Core Product Principle
AstraRun is an adaptive workstation agent. Planning, routing, tool selection, generated scripts, procedural skills, and retrieval strategies may adapt autonomously. However, **adaptation occurs strictly ABOVE a stable trust boundary**. The security kernel (`ActionGate`, `SecretBroker`, `SandboxManager`, `NetworkBroker`, `ResourceGovernor`, `TaskLedger`, `CapabilityRegistry`, `UpdateVerifier`) is authoritative and **cannot be modified, hot-patched, or bypassed autonomously**.

---

## 2. Dynamic Tooling Subsystem Architecture

### 2.1 CandidateTool Schema & DependencyRequest Specification
When a user objective cannot be satisfied by registered permanent capabilities (`ToolRegistry` or `skills/`), Astra synthesizes a strongly typed `CandidateTool`:

- **`goal`**: Explicit natural language intent.
- **`executable_code`**: Self-contained Python script implementing the functionality.
- **`test_verification_block`**: Verification assertions executed in dry-run mode prior to production execution.
- **`inputs` / `outputs`**: Typed dictionary parameter declarations.
- **`external_dependencies`**: List of explicit `DependencyRequest` objects declaring required packages, version specifiers, and rationale.
- **`required_permissions`**: Explicit capability claims evaluated by `ActionGate`.
- **`expected_side_effects`**: Explicit declaration of created artifacts or state alterations.
- **`sandbox_profile`**: Assigned containment profile (`EPHEMERAL_TOOL`, `WORKSPACE_TEST`, `RESEARCH_DOWNLOAD`).

### 2.2 AST Safety Screening (`ASTInspector`)
Before any generated script touches the disk or executes, it passes static abstract syntax tree inspection:
1. **Forbidden Modules**: Blocks unmanaged memory manipulation (`ctypes`, `_ctypes`, `_winapi`), raw low-level network bypass (`socket`, `socketserver`), unmanaged child processes (`subprocess`, `pty`), package managers (`pip`, `ensurepip`), and direct imports of Trust Kernel components (`astrarun.security`, `astrarun.sandbox`, `astrarun.network.broker`).
2. **Dynamic Execution Prohibitions**: Flags and rejects `eval()`, `exec()`, `compile()`, and `__import__()`.
3. **OS System Call Prohibitions**: Flags and rejects `os.system()`, `os.popen()`, `os.kill()`, `shutil.rmtree()` on root or system folders.

---

## 3. First-Class SandboxManager

The `SandboxManager` provides deterministic OS-level containment:
1. **Distinct Sandbox Profiles**:
   - `EPHEMERAL_TOOL`: Short-lived temporary workspace, zero network access, 15–30s execution cap, memory quota.
   - `WORKSPACE_TEST`: Confined to target workspace directory with path boundaries.
   - `RESEARCH_DOWNLOAD`: Quarantine staging only; code execution is strictly prohibited.
2. **Environment Sanitization**:
   - Maintains a strict allowlist of benign system variables (`PATH`, `SYSTEMROOT`, `TEMP`, `PYTHONPATH`, etc.).
   - Cryptographically purges all host secrets, API keys, and cloud credentials (matching `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `AWS`, `AZURE`, `OPENAI`, `ANTHROPIC`, `GEMINI`).
3. **Win32 Job Object Containment**:
   - Every worker process is assigned to an authoritative Win32 Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and explicit memory limits.
   - Stealth execution enforced via `CREATE_NO_WINDOW = 0x08000000`.
4. **Stream Capping & Output Redaction**:
   - `stdout` and `stderr` streams capped at 512 KB to prevent denial-of-service / memory exhaustion.
   - All streams processed through `SecretBroker.scrub_text()` to prevent credential leakage.

---

## 4. NetworkBroker & Download Quarantine

1. **Default DENY Network Policy**:
   - Blocks unauthorized egress and loopback/LAN probes (`127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`, `169.254.169.254` AWS metadata).
   - Only permitted local exception is designated inference ports (`8080`, `8081`).
2. **Operation Stratification**:
   - `HTTP_GET` / `HTTP_HEAD`: Permitted for public documentation and index lookups (low risk).
   - `HTTP_POST`: Outbound payload transmission containing local data requires interactive confirmation via `ActionGate` (high risk).
   - `DOWNLOAD`: All downloads routed directly into quarantine staging.
3. **Quarantine Staging (`data/quarantine/`)**:
   - Files stored by content SHA-256 hash prefix.
   - Sidecar metadata (`<filename>.meta.json`) recording source URL, timestamp, size, MIME type, and quarantine status.
   - **Zero Automatic Execution**: Quarantined executable artifacts (`.exe`, `.bat`, `.ps1`, `.py`, `.dll`) cannot be executed by the agent autonomously.

---

## 5. Bounded Self-Repair & Skill Lifecycle

### 5.1 Bounded Self-Repair Loop
When a generated tool encounters a syntax error or runtime failure:
1. Structured execution observation captures `exit_code`, `stderr`, and traceback.
2. The `DynamicToolBuilder` applies targeted repairs (Agg backend initialization, missing standard imports, numerical domain handling).
3. **Strict Bound**: Maximum of 2 repair attempts. If repair attempts are exhausted, the tool terminates gracefully and reports an authoritative failure.

### 5.2 Dynamic Tool -> Skill Promotion
1. Trajectory tracking records usage frequency, success rate, and produced artifacts.
2. Tools meeting the recurrence threshold (≥2 successful runs, ≥80% reliability) are promoted into permanent procedural skills.
3. Promoted skills are formatted in standard Hermes `SKILL.md` specification within `skills/<skill_name>/SKILL.md`.

---

## 6. Task, Session & Semantic Continuity

1. **Task Continuity**: Checkpoint persistence captures state, step index, produced artifacts, and context variables.
2. **Session Continuity**: Discovers unfinished tasks across application restarts.
3. **Semantic Continuity**: Resolves ambiguous conversational prompts (e.g., *"continue the graph thing we were doing"*):
   - Computes semantic similarity and artifact overlap against recent task history.
   - If confidence ≥ 0.80: Resumes context seamlessly.
   - If confidence < 0.80 or ambiguous: Formulates clarification candidate list; never hallucinates or guesses.

---

## 7. Authoritative Verification Evidence Matrix

All verification conducted on the actual physical workstation:

| ID | Test Description | Evidence Label | Result | Details / Telemetry |
|:---|:---|:---:|:---:|:---|
| **T1** | Live 3D Graph Dynamic Tool Generation | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Generated `live_test_11_dynamic_3d_graph.png` (562.6 KB) via numpy & matplotlib; duration 1787.59 ms, peak RAM 450.09 MB |
| **T2** | Semantic Continuity Resolution | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Prompt *"continue the graph thing we were doing"* resolved to task `task_3d_graph_active` with confidence 1.0 (100%) |
| **T3** | Network Public Read & Quarantine | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Fetched `pathlib.rst` (68.8 KB); staged untrusted artifact with `.meta.json`; execution strictly disabled |
| **T4** | Governed Failure & Bounded Repair | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Missing `math` import repaired in 1 attempt; verified `assert calculate() == 16.0` |
| **T5** | Dependency Governance (Disallow Pip) | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | AST inspector blocked `import pip`; structured `DependencyRequest` generated |
| **T6** | Trust Kernel Mutation Protection | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Autonomous attempt to alter `trust_kernel.py` rejected with `PermissionError` |
| **T7** | Schema Migrations (Config & SQLite) | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Config migrated v0 -> v2; SQLite DB migrated to v2 with columns `artifacts`, `risk_level`, `tool_id` |
| **R1** | Full Regression Test Suite | `UNIT_TESTED` | **PASSED** | **543 / 543 passed** in 127.78s across all core, UI, cognitive, and security modules |
| **R2** | Presentation Latency Benchmark | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Hotkey-to-visible presentation latency: **7.14 ms** average (50 cycles) |
| **R3** | Deterministic Routing Integrity | `UNIT_TESTED` | **PASSED** | 88/88 test cases routed deterministically with 0.0% false execution |
| **B1** | PyInstaller GUI Assembly | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Standalone directory distribution created in `dist/AstraRun/` (`AstraRun.exe` GUI subsystem) |
| **B2** | Inno Setup Windows Installer | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Compiled `dist/AstraRun-Setup-1.0.0-rc.1.exe` (SHA256: `baf7ff88...`) |
| **B3** | SPDX 2.3 SBOM Generation | `AUTOMATED_ON_PHYSICAL_WORKSTATION` | **PASSED** | Generated `dist/AstraRun-1.0.0-rc.1.spdx.json` (99 packages cataloged with licenses and hashes) |

---

## 8. Artifact Cryptographic Hashes

Generated release candidate artifacts stored in `dist/`:

| Artifact | Size | SHA-256 Checksum |
|:---|:---:|:---|
| `dist/AstraRun-Setup-1.0.0-rc.1.exe` | 1.84 GB | `BAF7FF88CCBC7678306658A659B2B2309B43FF99B545F165200149C86FC4CD21` |
| `dist/AstraRun/AstraRun.exe` | 13.9 MB | `0DF6399D0F825E3BAE8A19F82EE95D7910EE2A8435E7C6113C0DC3A7EB19E3B8` |
| `dist/AstraRun-1.0.0-rc.1.spdx.json` | 58.2 KB | `DD1E265A14773395A71C1D60E331179567387B6DE40E8EDF8FB9C9D774B039B0` |
| `live_test_11_dynamic_3d_graph.png` | 562.6 KB | `6E62F18E5E57FFD89C405B60BDDE970ED9A3C23FA8D455F60B84D3528A6B2961` |

---

## 9. Conclusion & Release Gate Status

All Milestone 7B requirements are completely implemented and physically verified. 
**Release Publication Status**: **BLOCKED & FROZEN**. In strict compliance with instructions, no GitHub Release has been drafted or published. The codebase is fully verified, locked, and ready for operator review.
