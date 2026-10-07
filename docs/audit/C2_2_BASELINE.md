# AstraRun C2.2 Baseline Reconstruction & Reality Audit

> **Scope**: Baseline Architecture, Git State, Physical Workstation Parameters, Side-Effect Call Graph, and Launch-Time Secret Vulnerability  
> **Audit Date**: 2026-10-07  
> **Milestone**: Phase C2.2 Security Closure & Trusted Capability Split  
> **Status**: BASELINE RECONSTRUCTED  

---

## 1. System, Runtime, and Workstation Baseline

### 1.1 Git Revision and Working Tree State
- **Base Commit HEAD**: `f4e5d06` (`fix(rc5a): end-to-end causal workflow execution, save_text_file capability, and evidence integrity`)
- **Uncommitted Modifications**: 49 tracked files modified across `src/astrarun/` and root configurations.
- **Untracked Directories/Files**: 26 entries (including unit test holdout suites, audit evidence, architecture documents).
- **Composite Production Source Tree SHA-256 (269 files)**: `60e818e7c4c80a2a37a47769879b160a391573e045223e70ec20a17b0ad805b2`

### 1.2 Physical Workstation Specifications
- **Operating System**: Windows 11 Build 26200 (Platform string: `Windows-11-10.0.26200-SP0`, 64-bit AMD64).
- **Python Version**: `3.13.0 (tags/v3.13.0:60403a5, Oct  7 2024, 09:38:07) [MSC v.1941 64 bit (AMD64)]`.
- **Active Executable**: `E:\Workspace\Active\AstraRun\.venv\Scripts\python.exe`.
- **Base Python Runtime**: `C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe`.
- **UAC Configuration (HKLM)**:
  - `EnableLUA = 1` (UAC actively enforced)
  - `ConsentPromptBehaviorAdmin = 5` (Prompt for consent for non-Windows binaries)
- **Caller Process Elevation**: `IsUserAnAdmin() == False` (Standard non-elevated user token; no administrative bypass).
- **Hardware Resources**:
  - System RAM: ~16 GB
  - CPU: Intel Core i5-12450H (8 cores / 12 threads)
  - GPU: NVIDIA GeForce RTX 2050 (4 GB VRAM)

---

## 2. Evidence Classification Hierarchy

In accordance with Section 0 and Section 12, evidence classes are strictly separated and never promoted across tiers:

1. **`IMPLEMENTED`**: Code present in source tree and syntactically valid.
2. **`UNIT_TESTED`**: Evaluated in synthetic, isolated pytest harness.
3. **`SOURCE_TREE_EXECUTED`**: Executed against live Windows workstation in source-tree environment (`.venv`).
4. **`REAL_LOCAL_MODEL_INFERENCE`**: Causal inference request and response against resident local llama-server (Qwen2.5-Coder / Spark).
5. **`REAL_COMPUTER_USE`**: Verified physical mouse, keyboard, or window interaction on workstation session.
6. **`FROZEN_EXE`**: Packaged executable artifact evaluated in clean distribution container (NOT claimed in C2.2).
7. **`HUMAN_OBSERVED`**: Manually observed and confirmed by human operator.

---

## 3. Current Production Call Graph & Side-Effect Paths

The current causal chain from user proposal to host mutation:

```text
User Request / Goal
    │
    ▼
[InputRouter] (src/astrarun/routing/input_router.py)
    │
    ├─── Direct / Known Capability
    │         │
    │         ▼
    │    [TaskManager] (src/astrarun/tasks/manager.py)
    │         │
    │         ▼
    │    [ExecutionBroker] (src/astrarun/security/execution_broker.py)
    │         │
    │         ▼
    │    [ActionGate] (src/astrarun/security/action_gate.py)
    │         │
    │         ▼
    │    [CapabilityRegistry.execute] ──► Host OS Mutation
    │
    └─── Dynamic Synthesis Required
              │
              ▼
         [AgentExecutionEngine] (src/astrarun/agent/loop.py)
              │
              ▼
         [DynamicToolBuilder] (src/astrarun/tools/dynamic_builder.py)
              │
              ├── AST Defense: [ASTInspector]
              ├── Machine Pressure: [ResourceGovernor]
              │
              ▼
         [SandboxManager] (src/astrarun/sandbox/manager.py)
              │
              ▼
         [AppContainerLauncher] (src/astrarun/sandbox/appcontainer_launcher.py)
              │
              ├── CreateAppContainerProfile (Zero Capabilities)
              ├── Suspended Process (Job Object assigned pre-resume)
              ├── lpEnvironment=None (DEFECT: Inherits parent environment)
              │
              ▼
         [Worker Process]
              │
              ├── Ephemeral Workspace Output
              │
              ▼
         [DynamicToolBuilder.deliver_artifact_via_broker]
              │
              ▼
         [ExecutionBroker.execute(ActionProposal)]
              │
              ▼
         [ActionGate.evaluate]
              │
              ▼
         [deliver_artifact] (src/astrarun/files/service.py)
              ├── Hardlink check (link count > 1 rejected)
              ├── Device path / ADS / traversal rejection
              └── Atomic replace to destination
```

### 3.1 Inventory of OS-Visible Side-Effect Paths
Every production path capable of causing host changes:
1. `files/service.py`: `deliver_artifact`, `write_file`, `delete_file`, `move_file`.
2. `browser/service.py`: Playwright browser automation, navigation, downloads.
3. `windows/controller.py`: Window focus, minimize, maximize, close.
4. `interaction/service.py`: `SendInput` mouse movement, mouse clicks, keystrokes.
5. `processes/controller.py`: `OpenProcess`, `TerminateProcess`, process launch.
6. `sandbox/manager.py`: Creation and deletion of temporary run directories and AppContainer profiles.
7. `network/broker.py`: Outbound HTTP/socket requests.

---

## 4. Immediate Architectural Defect: Launch-Time Secret Exposure

### The Finding
In Phase C2.1, `AppContainerLauncher` was implemented with:
```python
flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_SUSPENDED
ok = kernel32.CreateProcessW(
    None, cmd, None, None, True, flags,
    None,  # lpEnvironment = None -> INHERITS HOST ENVIRONMENT
    str(workspace), ctypes.byref(siex), ctypes.byref(pi),
)
```
Followed by a post-launch Python bootstrap (`_ac_bootstrap.py`) that purged sensitive keys from `os.environ`.

### Why This Fails the C2.2 Security Boundary
1. **Memory Exposure**: During child process initialization (ntdll.dll, kernelbase.dll, python313.dll), the entire parent process environment block—including `OPENAI_API_KEY`, cloud credentials, user tokens, and private paths—is loaded into the child's address space.
2. **Early Hook Hijacking**: Any `.pth` file, `sitecustomize.py`, or native C-extension (`.pyd`) executed during Python startup can read `PEB->ProcessParameters->Environment` or invoke `GetEnvironmentVariableW` **before** `_ac_bootstrap.py` executes.
3. **Requirement**: A valid security sandbox must never pass host secrets to the child process at launch time. `CreateProcessW` must receive an explicit, positive allowlist environment block.

---

## 5. Verification Sign-Off

The baseline state is established. Phase C2.2 implementation begins with Section 1: empirical investigation and resolution of the explicit `lpEnvironment` block under AppContainer on Windows 11 Build 26200.
