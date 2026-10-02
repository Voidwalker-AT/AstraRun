# Architecture & Release Dossier: Milestone 6 — Packaging, Installer & Resident Distribution

> **Scope**: Standalone Windows Release Candidate Packaging (`AstraRun 1.0.0-rc.1`)  
> **Status**: COMPLETED & VERIFIED  
> **Platform**: Windows 11 x64 (Clean Machine / Zero-Developer Prerequisites)  
> **Distribution**: Thin Core Standalone Installer + Managed Model Packs  

---

## 1. Executive Summary

Milestone 6 transitions AstraRun from a developer repository executed via virtual environments and CLI scripts into a standard, self-contained Windows desktop application. 

### Key Deliverables:
1. **Core Executable**: `dist\AstraRun\AstraRun.exe` (Standalone GUI binary, no terminal windows).
2. **Setup Installer**: `dist\AstraRun-Setup-1.0.0-rc.1.exe` (Per-user Inno Setup 6 installer).
3. **Multi-Resolution Icon**: 7 standard Windows icon sizes embedded (`16, 24, 32, 48, 64, 128, 256` px).
4. **Clean App Layout**: `%LOCALAPPDATA%\AstraRun\` for user data, logs, models, runtimes, and configs.
5. **Zero Admin Rights Required**: Installs to `%LOCALAPPDATA%\Programs\AstraRun` with zero UAC elevation.
6. **Autostart Manager**: User-level `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` integration.
7. **First-Run Experience**: Hardware audit, model pack downloader with HTTP resume and SHA-256 verification.
8. **Crash Reporting**: Automated diagnostic collection with SecretBroker scrubbing.

---

## 2. Directory Layout & Mode Resolution

AstraRun distinguishes between `AppMode.DEVELOPMENT` (running from source repository) and `AppMode.RELEASE` (running from packaged binary) via `src/astrarun/core/paths.py`.

```
%LOCALAPPDATA%\
  Programs\AstraRun\              <- Application binaries and libraries (Installer target)
    AstraRun.exe
    _internal\
  AstraRun\                       <- User data, persistence & cache
    config\                       <- astrarun.yaml, .first_run_completed
    data\                         <- tasks.db, memory.db, rag_vectors.db
    logs\                         <- astrarun.log, crash_*.json
    cache\                        <- temporary artifacts
    models\                       <- downloaded GGUF & ONNX models
    runtimes\                     <- llama-server.exe
    skills\                       <- user-installed agent skills
```

---

## 3. Packaging Architecture & Comparison

During Milestone 6, an empirical evaluation between packaging engines was conducted:

| Feature / Metric | Nuitka 4.2.2 | PyInstaller 6.22.3 |
| :--- | :--- | :--- |
| **Compilation Approach** | C-transpilation + host C compiler | Pure CPython freeze + bootloader |
| **Toolchain Dependencies** | Required external Zig/MSVC setup | Zero external compiler needed |
| **PySide6 / Qt Support** | Complex plugin handling | Native built-in collector |
| **Reliability on Host** | Blocked on interactive prompt | Passed build on first invocation |
| **Decision** | Abandoned | **Selected for Release Packaging** |

---

## 4. Verification & Hardening Results

- **Executable File Size**: ~73.8 MB (`AstraRun.exe`).
- **Single Instance Enforcement**: Named mutex prevents multi-process collisions; secondary summons focus resident tray/HUD.
- **Console Window Audit**: Zero terminal windows spawned across all execution flows (`console=False`, `CREATE_NO_WINDOW = 0x08000000`).
- **Security & Privacy**: Release crash dumps and loggers automatically scrub API tokens, JWTs, and passwords.
