# Dossier 58: Milestone 7C — Machine Intelligence, Capability Discovery & Environment Compatibility

> **Platform**: AstraRun 1.0 Runtime Architecture  
> **Status**: COMPLETED & VERIFIED  
> **Tag**: `post-milestone-7c`  
> **Target Hardware**: NVIDIA GeForce RTX 2050 Mobile (4GB VRAM), 12th Gen Intel Core i5-12450H (8C/12T), 16GB RAM, Windows 11  
> **Last Verified**: 2026-10-03  

---

## 1. Executive Summary & Core Principle

In Milestone 7C, AstraRun 1.0 transitions from executing plans based on generic LLM assumptions to grounding all planning, dynamic tooling, model residency, and task continuity in **authoritative, observed machine reality**.

### Core Product Principle
> Astra must know the machine it is operating on sufficiently well that planning and execution are based on observed machine reality rather than generic model assumptions.
> 
> This is **NOT** permission for ambient surveillance. Machine knowledge is strictly:
> - **Structured**: Strong typing, explicit units, standardized schema.
> - **Scoped**: Only developer toolchains, system compute, displays, storage volumes, and runtime capabilities.
> - **Provenanced**: Exact discovery source and authority tracked for every fact.
> - **Freshness-Aware**: Multi-tier TTL and caching model (`IMMUTABLE`, `STABLE`, `SESSION`, `VOLATILE`, `REALTIME`).
> - **Resource-Aware**: Zero-overhead micro-second polling (<15ms budget).
> - **Privacy-Preserving**: Strict non-intrusive boundaries. Zero scanning of user documents, browser cookies, keystrokes, or peripheral media. Sanitized exports scrub personal paths and secrets.
> - **Incrementally Updated**: Event-driven notification for storage, network, and power transitions.

---

## 2. Machine Fact Schema & Multi-Tier Freshness

Every machine attribute is modeled as an immutable `MachineFact` instance:

```python
@dataclass(frozen=True)
class MachineFact:
    key: str                                # E.g., "hardware.gpu.vram_free_mb"
    value: Any                              # Normalized typed value
    unit: Optional[str] = None              # E.g., "MB", "GB", "MHz", "%"
    source: FactAuthority = FactAuthority.OS_API
    observed_at: float = field(default_factory=time.time)
    freshness_class: FreshnessClass = FreshnessClass.STABLE
    ttl_sec: Optional[float] = None
    confidence: float = 1.0                 # 0.0 - 1.0 scale
    authority: str = "authoritative"        # "authoritative", "probe", "inferred"
    sensitivity: FactSensitivity = FactSensitivity.INTERNAL
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Freshness Classification & Invalidation Policy

| Freshness Tier | Scope & Examples | Default TTL | Invalidation / Refresh Strategy |
| :--- | :--- | :--- | :--- |
| **`IMMUTABLE`** | CPU architecture, CPU physical cores, Total physical RAM, OS architecture | Never | Discovered once on first launch; permanently retained in SQLite. |
| **`STABLE`** | OS build, GPU model, Total VRAM, Installed browsers/IDEs, Git path, Pagefile size | 86,400s (24h) | Re-verified once per 24 hours or on explicit user rescan request. |
| **`SESSION`** | Process elevation (`IsUserAnAdmin`), UAC status, Python venv path | Run duration | Discovered at resident process startup; static until process termination. |
| **`VOLATILE`** | Free storage per volume, Battery %, Active power source, Network connection | 300s (5m) | Lazy refresh if requested past TTL; fast background update. |
| **`REALTIME`** | Instant CPU %, Free RAM, Free VRAM, Commit pressure | 0s (Instant) | Never cached in SQLite; captured on-demand via `ResourceSnapshot.capture()`. |

---

## 3. Modular Discovery Providers

Discovery is isolated into 5 specialized providers adhering to `BaseMachineProvider`:

### 1. `HardwareProvider`
- **CPU**: Model (`12th Gen Intel(R) Core(TM) i5-12450H`), 8 physical cores, 12 logical threads, max frequency.
- **Memory**: Total RAM (15.65 GB), available RAM, used %, pagefile total/used.
- **GPU & VRAM**: Primary detection via Win32 `nvml.dll` ctypes C-API, falling back to PyTorch and `nvidia-smi`. Discovers NVIDIA GeForce RTX 2050 (4.00 GB total dedicated VRAM, 3.64 GB free).
- **Storage**: Discovers all mounted drive letters (`C:`, `E:`, `G:`, `H:`), total/free capacities, filesystems (NTFS), and drive types (Fixed/SSD/Removable).
- **Displays**: Multi-monitor detection via `GetSystemMetrics` (`SM_CMONITORS`), primary resolution (`1536x864`), display bounds, and OS DPI scaling factor.
- **Network**: Active non-loopback interface status (`isup`), gateway detection.
- **Power**: AC plugged status, battery percentage, charging state.
- **Peripherals (Privacy-Preserved)**: Non-intrusive probe checking Win32 `waveInGetNumDevs` and registry device classes. Confirms microphone and camera presence without opening media streams or capturing samples.

### 2. `OSModelProvider`
- **Windows Version & Build**: Discovers Windows 10/11 version (`Windows 10 Home Single Language` / Build `26200`).
- **Elevation & UAC**: Probes `ctypes.windll.shell32.IsUserAnAdmin()` and registry `EnableLUA` to verify elevation without popping UAC prompts.
- **Filesystem Capabilities**: Probes Win32 long path support (`LongPathsEnabled` in `SYSTEM\CurrentControlSet\Control\FileSystem`).

### 3. `SoftwareProvider`
- **Developer Toolchains**: Scoped executable probe using `CREATE_NO_WINDOW = 0x08000000` to prevent console flashing:
  - `git`: `C:\Program Files\Git\cmd\git.EXE` (v2.54.0.windows.1)
  - `node`: `C:\Program Files\nodejs\node.EXE` (v22.12.0)
  - `gcc`: Installed via MinGW/GCC toolchain
  - `nvcc`: NVIDIA CUDA Compiler on PATH
  - `pwsh` / `powershell`: PowerShell 7 / Windows PowerShell
- **Desktop Browsers**: Direct detection of executable paths and automation readiness for Chrome, Edge, Vivaldi, and Firefox.
- **IDEs**: Detection of VS Code (`C:\Users\hp\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd`) and Cursor.

### 4. `PythonEnvProvider`
- **Active Environment**: Detects active `.venv` runtime (`E:\Workspace\Active\AstraRun\.venv\Scripts\python.exe`, Python 3.13.0).
- **Key Scientific Libraries**: Authoritative package verification: `numpy`, `matplotlib`, `torch`, `transformers`.

### 5. `TopologyProvider`
- **Filesystem Boundaries**: System Desktop, Downloads, AppData, Temp.
- **Canonical Model Storage**: References `E:\AI_Models` (`OLLAMA`, `GGUF`, `HF_CACHE`) per Workspace Rule 9.
- **Workspace Registry**: Discovers `E:\Workspace` root and active category trees.

---

## 4. Sub-15ms ResourceSnapshot & Ctypes NVML Telemetry

For real-time model residency eviction and pre-flight task gating, AstraRun captures an instantaneous `ResourceSnapshot`:

```python
snap = ResourceSnapshot.capture(include_gpu=True)
```

### Zero-Overhead Ctypes NVML Architecture
Previously, querying GPU telemetry via `nvidia-smi` took 25-50ms and risked spawning unwanted console flashes. In Milestone 7C, `ResourceSnapshot` binds directly to Windows `C:\Windows\System32\nvml.dll` via Python `ctypes`:
- **Latency**: Under **0.15ms** for GPU memory inspection.
- **Memory Overhead**: 0 MB (no PyTorch CUDA context initialization required).
- **Accuracy**: Reports true hardware driver telemetry (4.00 GB total VRAM, 3.64 GB free VRAM on the physical RTX 2050).

### Measured Telemetry Performance
- **ResourceSnapshot Capture Latency**: **11.02 ms average** (min: 9.30ms, max: 12.28ms). Well within the <15ms resident budget.
- **Machine DB Footprint**: **48.0 KB** SQLite database (`data/machine/machine_facts.db`).
- **Cold Discovery Latency**: 5.10s across all 5 providers (145 facts).
- **Warm Startup Latency**: 2.69s (validating cached facts).

---

## 5. Derived Capability Predicates

The `MachineCapabilityResolver` evaluates 15 operational capabilities with supporting evidence citations and recovery remediations:

| Capability Name | Live Status on Workstation | Reason / Citation | Remediation |
| :--- | :---: | :--- | :--- |
| `CAN_RUN_LOCAL_SPARK` | **`AVAILABLE`** | Host has 15.65 GB RAM (>= 6.0 GB required for Spark-1.7B). | None |
| `CAN_RUN_LOCAL_QWEN` | **`AVAILABLE`** | Host has 15.65 GB RAM (>= 8.0 GB required for Qwen-Coder-1.5B). | None |
| `CAN_LOAD_LOCAL_VLM_NOW` | **`AVAILABLE`** | Live free VRAM is 3.64 GB (>= 2.5 GB required). | Evict resident local models |
| `CAN_RUN_PYTHON_VISUALIZATION` | **`AVAILABLE`** | Python runtime with `numpy` and `matplotlib` is fully available. | None |
| `CAN_COMPILE_CPP` | **`AVAILABLE`** | Native C/C++ compiler (GCC) is installed and verified. | Install MSVC or MinGW |
| `CAN_USE_CUDA` | **`AVAILABLE`** | CUDA acceleration available on NVIDIA GeForce RTX 2050. | None |
| `CAN_AUTOMATE_BROWSER` | **`AVAILABLE`** | Supported desktop browser (Chrome) is installed and accessible. | Install Chrome or Edge |
| `CAN_USE_UIA` | **`AVAILABLE`** | Windows UI Automation (UIA) foundation available via OS runtime. | None |
| `CAN_USE_CDP` | **`AVAILABLE`** | Chromium-based browser (Chrome) supports Chrome DevTools Protocol. | Launch Chromium browser |
| `CAN_DOWNLOAD` | **`AVAILABLE`** | Workstation network adapter reports active connection. | Connect to network |
| `CAN_EXTRACT_ZIP` | **`AVAILABLE`** | Python standard library `zipfile` module available. | None |
| `CAN_RENDER_VIDEO` | **`UNAVAILABLE`** | `ffmpeg` executable not detected on system PATH. | Install ffmpeg via scoop/winget |
| `CAN_USE_GIT` | **`AVAILABLE`** | Git version control CLI is installed and operational. | Install Git |
| `CAN_RUN_NODE` | **`AVAILABLE`** | Node.js runtime is installed and operational. | Install Node.js |
| `CAN_BUILD_CUDA` | **`AVAILABLE`** | NVIDIA CUDA Compiler (`nvcc`) is installed on PATH. | Install CUDA Toolkit |

---

## 6. Pre-flight Compatibility & Architectural Integration

The `CompatibilityEngine` validates proposed workloads prior to task execution:
- **CUDA Workloads**: Validates hardware GPU presence, CUDA driver initialization, and compares required VRAM against live free VRAM. Returns `RESOURCE_BLOCKED` when free VRAM is insufficient.
- **Vision Models**: Assesses SmolVLM / OmniParser requirements, verifying 2.5 GB VRAM headroom or planning a graceful CPU fallback.
- **Data Visualization**: Validates Python environment for `matplotlib` and `numpy`.
- **C/C++ Compilation**: Checks for `cl.exe` or `gcc.exe` before accepting native build tasks.

### Subsystem Wiring
1. **Planner (`ContextBuilder`)**: Injects concise, relevant facts into model prompts via `build_machine_context()`. Omits extraneous device details, battery serials, or private home paths.
2. **Dynamic Tool Builder (`DynamicToolBuilder`)**: Queries `MachineModel` before emitting a `DependencyRequest` to avoid attempting to install tools that already exist or fail on incompatible hardware.
3. **Network Broker (`NetworkBroker`)**: Directly checks `hardware.network.connected` to fail fast on offline status before issuing external HTTP requests.
4. **Continuity Engine (`ContinuityEngine`)**: Evaluates task checkpoints against live storage volumes via `check_machine_drift()` to detect missing drives (e.g. unplugged external disks) before resuming execution.

---

## 7. Natural Language Machine Query Engine & Privacy

The `MachineQueryEngine` translates conversational machine queries into authoritative, factual responses directly from `MachineModel`:

### Verified Physical Workstation NL Results (`AUTOMATED_ON_PHYSICAL_WORKSTATION`)
1. **"What CPU do I have?"**  
   *Answer*: You have an 12th Gen Intel(R) Core(TM) i5-12450H with 8 physical cores and 12 logical threads.
2. **"How much RAM is free right now?"**  
   *Answer*: You have 9.72 GB of physical RAM free right now (out of 15.65 GB total).
3. **"What GPU do I have?"**  
   *Answer*: Your graphics adapter is NVIDIA GeForce RTX 2050 with 4.0 GB dedicated VRAM (CUDA Available: True).
4. **"How much VRAM is free?"**  
   *Answer*: You currently have 3.63 GB of free dedicated VRAM available on your GPU (out of 4.0 GB total).
5. **"Which monitors are connected?"**  
   *Answer*: You have 1 monitor(s) connected. Primary display resolution is 1536x864 at 100% scaling.
6. **"Is Vivaldi installed?"**  
   *Answer*: No, Vivaldi was not detected on this PC.
7. **"Is VS Code installed?"**  
   *Answer*: Yes, Visual Studio Code is installed at: `C:\Users\hp\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd`.
8. **"Where is Git?"**  
   *Answer*: Git is installed at `C:\Program Files\Git\cmd\git.EXE` (git version 2.54.0.windows.1).
9. **"Can I run CUDA?"**  
   *Answer*: CUDA Capability: AVAILABLE. CUDA acceleration available on NVIDIA GeForce RTX 2050.
10. **"Can I load the visual model right now?"**  
    *Answer*: Visual Model Status: AVAILABLE. Live free VRAM is 3.63 GB (>= 2.5 GB required).
11. **"What drives have enough space for a 5 GB file?"**  
    *Answer*: The following drives have at least 5 GB of free space: Drive C: (19.88 GB free), Drive E: (29.09 GB free), Drive G: (27.63 GB free), Drive H: (27.63 GB free).

### Privacy & Sanitization Verification
The `MachineDiagnostics.export_sanitized_diagnostics()` pipeline ensures zero leak of personal information:
- Redacts local Windows user account names (`<USER>`).
- Redacts user profile root directories (`<USER_HOME>`).
- Scrubs embedded tokens and secret values through `SecretBroker`.
- Physical workstation export verified: **Zero user or secret tokens detected**.

---

## 8. Verification & Acceptance Evidence Summary

- **Automated Regression Suite**: **554 / 554 tests passing (100%)** (`UNIT_TESTED`).
- **Milestone 7C Dedicated Test Suite**: **11 / 11 tests passing (100%)** covering fact schemas, providers, telemetry, persistence, resolver, pre-flight compatibility, 8-profile synthetic matrix, and drift detection.
- **Physical Machine Live Script**: **PASSED** (`AUTOMATED_ON_PHYSICAL_WORKSTATION`).
- **Packaging Spec**: PyInstaller spec updated with `astrarun.machine` submodules.
- **Git Checkpoint**: Committed (`feat(milestone-7c): add machine intelligence and compatibility model`) and tagged (`post-milestone-7c`).
