# AstraRun 1.0.0-rc.1 Release Notes

**AstraRun 1.0.0-rc.1** marks the official Release Candidate milestone for AstraRun, the resident local-first AI assistant for Windows desktop environments.

---

## Key Highlights

### 1. Standalone Windows Executable & Installer
- **Thin Core Architecture**: The core application and runtime dependencies are packaged into a standalone installer (`AstraRun-Setup-1.0.0-rc.1.exe`).
- **Zero Developer Prerequisites**: Runs natively without requiring Python, Git, PowerShell, or manual virtual environments.
- **Per-User Non-Elevated Installation**: Installs cleanly into `%LOCALAPPDATA%\Programs\AstraRun` without requiring Administrator privileges or UAC prompts.
- **Clean Uninstallation**: Standard Windows uninstaller preserves user-downloaded models, logs, and configurations while removing application binaries cleanly.

### 2. First-Run Onboarding Experience
- **Hardware Audit Wizard**: Automatically scans CPU, system RAM, NVIDIA GPU capabilities, and available VRAM to determine system compatibility.
- **Managed Model Packs**: Automated downloading, HTTP resume support, and cryptographic SHA-256 integrity verification for standard cognitive packs (`Spark-X2.5`, `Qwen2.5-Coder`, `BGE-small`).
- **Autostart Configuration**: Transparent opt-in for Windows user-level login autostart (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).

### 3. Continuous Resident Runtime & Desktop Integration
- **Zero Terminal Windows**: Native GUI subsystem process launch (`CREATE_NO_WINDOW`) guarantees zero flashing or persistent command prompt windows.
- **Single Instance Enforcement**: Named mutex and IPC pipe ensure only one resident process runs at any time; subsequent launches signal the existing resident process.
- **System Tray & Summon Surface**: Unobtrusive system tray icon with quick controls; `Alt+Space` summons the command surface smoothly.

### 4. Robust Diagnostics & Security
- **Secret Scrubbing**: Automated credential filtering in crash reports and release loggers ensures API tokens and private data are never stored in plain text.
- **Crash Reporting**: Automated structured diagnostics saved to `%LOCALAPPDATA%\AstraRun\logs\crash_*.json`.
