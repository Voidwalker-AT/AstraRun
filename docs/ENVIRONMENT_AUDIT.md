# Environment Audit: AstraRun Host Environment

> **Date**: 2026-09-26  
> **Host Platform**: Microsoft Windows 11 Home Single Language (Build 10.0.26200, 64-bit)  
> **Workspace Category**: `Active`  
> **Target Path**: `E:\Workspace\Active\AstraRun`  

---

## 1. Operating System & Hardware Metrics

- **Operating System**: Microsoft Windows 11 Home Single Language (Version 10.0.26200)
- **Architecture**: 64-bit (x86_64)
- **Display Setup**:
  - Monitor Count: 1
  - Primary Resolution: 1536 x 864
  - Virtual Desktop Bounds: 1536 x 864
  - Primary Display Scaling: Standard High-DPI active
- **Shell**: PowerShell 7 (`pwsh`)
- **Git Version**: 2.54.0.windows.1 (Repository initialized inside `AstraRun/`, parent `E:\Workspace` and `Active/` are not Git repos)

---

## 2. Python Ecosystem & Runtime Strategy

- **System Runtimes Detected**:
  - Python 3.13.0 (64-bit) at `C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe`
  - Python 3.12 (Store edition)
  - Python 3.11 (64-bit) at `C:\Users\hp\AppData\Local\Programs\Python\Python311\python.exe`
  - Python 3.10 (64-bit) at `C:\Program Files\Python310\python.exe`
  - Astral/uv CPython 3.11.16
- **Package Manager**: `uv` 0.12.10 detected and operational.
- **AstraRun Virtual Environment**:
  - Path: `E:\Workspace\Active\AstraRun\.venv`
  - Base Python: Python 3.13.0
  - Installed packages: `PySide6` (6.11.2), `pytest` (9.1.1)

---

## 3. Alt+Space Conflict & Hotkey Analysis

- **Investigation**:
  - PowerToys (Preview) 0.100.2 is installed at `C:\Users\hp\AppData\Local\PowerToys\`.
  - Process audit confirmed that **no PowerToys process is currently running**.
  - Direct Win32 test of `user32.RegisterHotKey(None, 1, MOD_ALT | MOD_NOREPEAT, VK_SPACE)` was executed:
    - **Result**: `SUCCESS (code: 1, LastError: 0)`
  - Alt+Space is currently available and successfully bindable.
- **Conflict Mitigation Strategy**:
  - While Alt+Space is free right now, launching PowerToys in the future could create a hotkey collision with PowerToys Run.
  - Therefore, the global hotkey mechanism is decoupled into an isolated hotkey manager and configured via `config/settings.json`.
  - If a collision occurs upon startup, AstraRun catches the failure gracefully, logs the exact error, and falls back to a configurable secondary shortcut or presents a clear diagnostic.

---

## 4. Key Target Applications & Discovery Vectors

| Target Application | Expected Path / Location | Discovery Mechanism |
| :--- | :--- | :--- |
| **Notepad** | `C:\Windows\System32\notepad.exe` | System PATH / Windows Apps |
| **Calculator** | `C:\Windows\System32\calc.exe` | System PATH / App URI (`calc:`) |
| **Windows Terminal** | `C:\Program Files\WindowsApps\Microsoft.WindowsTerminal_1.24.11911.0_x64__8wekyb3d8bbwe\wt.exe` | Windows App Paths Registry / `wt.exe` |
| **PowerShell** | `C:\Users\hp\scoop\apps\pwsh\current\pwsh.exe` & `powershell.exe` | PATH / System32 |
| **Command Prompt** | `C:\Windows\System32\cmd.exe` | System PATH |
| **File Explorer** | `C:\Windows\explorer.exe` | System PATH |
| **VS Code** | `C:\Users\hp\AppData\Local\Programs\Microsoft VS Code\Code.exe` | App Paths Registry & PATH |
| **Vivaldi** | `E:\vivaldi\Application\vivaldi.exe` | App Paths Registry (`HKLM/HKCU App Paths\vivaldi.exe`) |

---

## 5. Folder Resolution Strategy

Windows User Shell Folders was inspected under `HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders`:
- **Downloads**: `{374DE290-123F-4565-9164-39C4925E467B}` -> dynamically resolved.
- **Documents**: `Personal` -> dynamically resolved.
- **Desktop**: `Desktop` -> dynamically resolved.
- **Pictures**: `My Pictures` -> dynamically resolved.
- **Videos**: `My Video` -> dynamically resolved.
- **Workspace**: Dynamically resolved from parent workspace discovery (`E:\Workspace`).
- **Active Projects**: Dynamically resolved from `E:\Workspace\Active`.

No usernames or fixed machine paths are hardcoded.
