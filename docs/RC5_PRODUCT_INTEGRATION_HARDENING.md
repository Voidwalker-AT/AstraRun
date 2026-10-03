# RC.5 DOGFOOD — Install / Uninstall / Computer-Use Integration & UX Hardening

> **Release Target**: `1.0.0-rc.5-dogfood`  
> **Status**: BUILT, AUDITED & READY FOR HUMAN DOGFOOD  
> **Reference Workstation**: Windows 11 Pro 64-bit | Intel i5-12450H | 16 GB RAM | NVIDIA GeForce RTX 2050 (4 GB VRAM) + Intel UHD Graphics  
> **Git Checkpoint Tag**: `post-rc5-hardening`  

---

## 1. Executive Summary & Deliverables

RC.5 Dogfood establishes the complete product-grade lifecycle for AstraRun:
1. **Packaging & Distribution**:
   - Packaged Directory: `dist\AstraRun\AstraRun.exe` (Embedded version: `1.0.0-rc.5-dogfood`, `1.0.5.0`)
   - Standalone Setup: `dist\installer\AstraRun-Setup-1.0.0-rc.5-dogfood.exe`
   - Size: `234,958,745 bytes` (~224.07 MB)
   - SHA-256: `D95420303264D316E83E8A6E90185C7D2958AB1EBE0B6469FB7456F4726A201B`
2. **Strict Component Ownership & Lifecycle Governance**:
   - Zero-deletion immunity for externally owned models (`E:\AI_Models\...`) and workstation runtimes.
   - Active task detection during uninstall with user choice (`Cancel` [default], `Pause & checkpoint`, `Stop tasks`).
   - Granular removal checkboxes with live measured sizes and external model preservation badges.
3. **Product Surface UX & Maintenance**:
   - Settings dialog redesigned conforming to the near-black Astra design system (`BG_APP #12151c`, `SURFACE #1a1e28`, Astra Blue accent `#58a6ff`).
   - First-run wizard updated to detect preserved state on reinstall.
   - Desktop and Start Menu shortcut validation with multi-resolution `.ico` assets.
   - Built-in lightweight self-healing engine (`AstraRun.exe --repair`): 6/6 system components verified/repaired.
4. **Computer-Use Provider Matrix**:
   - Complete audit across UIA, CDP, COM, Physical Input, Takeover, OCR, CV, Visual Grounder, and VLM.

---

## 2. Component Ownership & Uninstallation Lifecycle

### A. Ownership Classification Matrix

| Component Type | Canonical Path | Ownership Domain | Removal Policy |
| :--- | :--- | :--- | :--- |
| **Application Binaries** | `%LOCALAPPDATA%\Programs\AstraRun\` | Astra Application | Removed by Uninstaller |
| **Start Menu / Desktop Links** | `%APPDATA%\...\Programs\AstraRun.lnk` | Windows Shell Integration | Removed by Uninstaller |
| **Autostart Run Key** | `HKCU\...\Run\AstraRun` | Windows User Registry | Removed by Uninstaller |
| **Configuration** | `%LOCALAPPDATA%\AstraRun\config\` | Astra Managed Config | User-selectable in Wizard |
| **Logs & Telemetry** | `%LOCALAPPDATA%\AstraRun\logs\` | Astra Audit & Logs | User-selectable in Wizard |
| **Task History & Ledger** | `%LOCALAPPDATA%\AstraRun\data\tasks.db` | Astra User Continuity | User-selectable in Wizard |
| **Memory Database** | `%LOCALAPPDATA%\AstraRun\data\memory.db` | Learned Habits & Cache | User-selectable in Wizard |
| **Search & RAG Index** | `%LOCALAPPDATA%\AstraRun\data\rag\` | Discovered Metadata | User-selectable in Wizard |
| **Astra Downloaded Models** | `%LOCALAPPDATA%\AstraRun\models\` | Astra Managed Models | User-selectable in Wizard |
| **External Pre-existing Models** | `E:\AI_Models\GGUF\...` | **Workstation Owned** | **IMMUNE — NEVER DELETED** |
| **External Runtimes** | Python 3.13, Git, Vivaldi, CUDA | **Workstation Owned** | **IMMUNE — NEVER TOUCHED** |

### B. Active Task Protection Flow
When `unins000.exe` or `AstraRun.exe --uninstall-ui` is invoked:
1. Inspects `astrarun_state.json` and `task_ledger.db` for running or active tasks.
2. If active tasks exist, displays warning banner with 3 explicit choices:
   - **`Cancel uninstall` (Default)**: Immediately aborts uninstallation without altering state.
   - **`Pause & checkpoint`**: Triggers `ContinuityEngine.checkpoint_active_tasks()` and persists state to SQLite before proceeding.
   - **`Stop tasks`**: Marks active tasks as cleanly stopped.
3. IPC Named Pipe (`\\.\pipe\astrarun_ipc`) signals resident AstraRun shell to exit gracefully before file deletion.

---

## 3. Computer-Use Stack Provider Matrix & Security Equivalence

Every computer-use action operates under strict **ActionGate** supervision with full visual prompt injection defense, target bounds verification, and instantaneous human physical takeover detection.

| Provider / Layer | Technology | Primary Domain | Fallback Path | Security Gate / Invariant |
| :--- | :--- | :--- | :--- | :--- |
| **1. Accessibility (UIA)** | `pywinauto` / Windows UI Automation | Win32, WPF, UWP structured applications | OCR + Visual Grounder | Target bounds check; no off-screen clicks; ActionGate confirmation on destructive actions |
| **2. Browser Engine (CDP)** | Chrome DevTools Protocol / WebSocket | Vivaldi, Chrome, Edge DOM control | UIA / OCR fallback | Zero-secret password field token scrubbing; interactive element bounding boxes |
| **3. Office & COM Bridge** | `win32com` / `comtypes` | Excel, Word, Shell application automation | Window activation + UIA | Protected dispatch; failsafe fallbacks when COM server unregistered |
| **4. Native Input Controller** | `pyautogui` / `SendInput` (Win32) | Mouse clicks, coordinate clicks, typing | Interactive prompt | Pre-click coordinate bounds validation; monotonic frame verification; user takeover detection |
| **5. Physical Takeover** | Raw Win32 Mouse Hook (`GetAsyncKeyState`) | Human operator intervention detection | Immediate Agent Halt | Instantaneous execution abortion when user moves mouse >20px or presses key |
| **6. Visual Grounder & OCR** | Local Grounding Model + Tesseract / EasyOCR | Unlabeled UI icons, canvas elements, games | VLM Vision Reasoner | Target query confidence threshold; CPU residency; injection quarantine |
| **7. Vision Reasoner (VLM)** | Qwen2-VL / Local Vision LLM | Complex screen interpretation | ActionGate Block | Visual prompt injection detection; untrusted visual text isolated from system prompt |

---

## 4. Workstation Self-Healing Engine (`AstraRun.exe --repair`)

AstraRun includes an integrated repair mechanism invokable from Settings or via CLI:
```powershell
AstraRun.exe --repair
```

### Verified Self-Healing Output:
```text
[SUCCESS] 6/6 system components healthy or repaired.
  • Application Executable: [OK] Frozen executable verified: AstraRun.exe (72529 KB)
  • Autostart Registration: [OK] HKCU\Software\Microsoft\Windows\CurrentVersion\Run verified.
  • Start Menu Shortcut: [OK] Start Menu link verified: AstraRun.lnk
  • Workstation Profile: [REPAIRED] Machine facts refreshed. Compute GPU: NVIDIA GeForce RTX 2050
  • Model Storage Directory: [OK] Writable model path verified: C:\Users\hp\AppData\Local\AstraRun\models
  • Search & Discovery Index: [REPAIRED] Reindexed 398 apps and 9 folders.
```

---

## 5. Dogfood Issue Tracker (DF-001 through DF-007)

| Issue ID | Description | Root Cause | Automated Verification Status | Human Dogfood Status |
| :--- | :--- | :--- | :--- | :--- |
| **DF-001** | Packaged cognition resident crash (0xc0000409) | In-process Laya import and missing standard library in worker | **VERIFIED FIXED** (Isolated child process IPC + zero-resident crash) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-002** | Hardware audit misidentifying GPU as Integrated/0GB | First-adapter assumption querying Intel UHD rather than discrete RTX 2050 | **VERIFIED FIXED** (Discrete NVIDIA RTX 2050 4GB preferred for compute) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-003** | First-Run Wizard uninformative model card layout | Missing model size, quantization, and disk location details | **VERIFIED FIXED** (Explicit GGUF card with sizes and existing model reuse) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-004** | Missing folder browse button in First-Run preferences | Hardcoded line edit without Windows `QFileDialog` integration | **VERIFIED FIXED** (Interactive `Browse...` dialog implemented) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-005** | Ambiguous autostart checkbox phrasing | Label did not clarify Windows sign-in behavior | **VERIFIED FIXED** (Updated to "Start Astra automatically when I sign in") | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-006** | Inno Setup uninstaller silently destroying external models | Lack of component ownership separation and boundary guard | **VERIFIED FIXED** (Two-stage Python/Inno uninstaller with external immunity) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-007** | Reinstall ignoring pre-existing user configurations | First-run wizard overwriting existing `config/astrarun.yaml` | **VERIFIED FIXED** (Restoration banner detecting preserved settings) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |

---

## 6. Exact 21 Evidence Package

### 1. Uninstall Ownership Model
Documented in Section 2.A. Application binaries and shortcuts are owned by Astra. Pre-existing models (`E:\AI_Models\...`) and system runtimes are workstation-owned and strictly immune. User data is individually selectable.

### 2. Uninstall UI Screenshots
- `uninstaller_normal.png`: Shows clean component inventory with live disk size calculations and external model immunity badges.
- `uninstaller_active_tasks.png`: Shows active task detection banner with default `Cancel uninstall` choice.

### 3. Uninstall Active-Task Behavior
Verified via `tests/test_rc5_product_hardening.py::test_uninstall_ownership_classification`. Active task detection correctly returns running task counts, provides graceful shutdown via IPC, and allows user pause/checkpoint.

### 4. External-Model Preservation Test
`test_external_models_never_deleted` executes an uninstall plan with external model paths (`E:\AI_Models\GGUF\...`) present; asserts that `is_external=True`, `removable=False`, and zero deletions occur outside `%LOCALAPPDATA%\AstraRun`. Result: **PASSED**.

### 5. Managed-Model Removal Test
`test_managed_components_removal` verifies that managed models inside `%LOCALAPPDATA%\AstraRun\models` are marked as removable and purged when explicitly selected by the user. Result: **PASSED**.

### 6. Reinstall / Preserved-State Result
`test_reinstall_preserved_state_detection` verifies that when `%LOCALAPPDATA%\AstraRun\config\astrarun.yaml` exists, `has_preserved_config` is set to `True` and the first-run wizard presents the configuration restore card. Result: **PASSED**.

### 7. First-Run Screenshots
- `page_0_welcome.png`: Welcome page with subtitle "Local-first adaptive Windows agent".
- `page_1_hardware.png`: Hardware profile showing discrete NVIDIA RTX 2050 (4GB) compute GPU and secondary Intel UHD display GPU.
- `page_2_models.png`: Model card with Spark-X2.5 and Qwen 2.5 Coder detection.
- `page_3_preferences.png`: Interactive `Browse...` folder picker and clarified autostart phrasing.

### 8. Desktop Shortcut Screenshot
`desktop_shortcut.png`: Displays verified desktop shortcut `%USERPROFILE%\Desktop\AstraRun.lnk` pointing to `C:\Users\hp\AppData\Local\Programs\AstraRun\AstraRun.exe` with embedded multi-resolution icon.

### 9. Start Menu Screenshot
`start_menu.png`: Displays Windows Start Menu entries for `AstraRun` and `Uninstall AstraRun`.

### 10. Installed Apps Screenshot
`installed_apps.png`: Displays Windows Installed Apps entry: `AstraRun`, `1.0.0-rc.5-dogfood`, `Astra Engineering Team`, `224 MB`.

### 11. Computer-Use Provider Matrix
Documented in Section 3. Integrates UIA, CDP, COM, Native Input, Physical Takeover, OCR, CV, Visual Grounder, and VLM under ActionGate governance.

### 12. UIA Smoke Result
`test_milestone4_perception_control.py` tests 15-18: Structured window observation, direct pattern invocation without moving physical cursor, and staleness detection. Result: **PASSED**.

### 13. Browser / CDP Smoke Result
`test_milestone4_perception_control.py` tests 19-21: Token-saving DOM compression, zero-secret password field redaction, and interactive element indexing. Result: **PASSED**.

### 14. Physical-Input / Takeover Result
`test_user_takeover_detection_and_halt`: Physical mouse movement during automation triggers immediate `UserTakeoverException` and releases input control. Result: **PASSED**.

### 15. Visual Fallback Result
`test_canonical_fixtures`: Fixture A (UIA), Fixture B (CDP), Fixture C (Visual Grounder for unlabeled buttons), and Fixture D (VLM vision reasoner) cleanly resolve actions across visual fallback levels. Result: **PASSED**.

### 16. Install -> Use -> Uninstall Result
Full cycle verified:
- Install: `AstraRun-Setup-1.0.0-rc.5-dogfood.exe /DIR="C:\Users\hp\AppData\Local\Programs\AstraRun" /VERYSILENT` exited 0.
- Use: `C:\Users\hp\AppData\Local\Programs\AstraRun\AstraRun.exe --repair` exited 0 with 6/6 components verified.
- Uninstall: `AstraRun.exe --uninstall-ui` renders options and Inno Setup uninstaller cleanly purges application root while preserving external models.

### 17. CI Additions
Automated smoke test suite in `tests/test_rc5_product_hardening.py` covers:
- Ownership classification
- External model immunity
- Managed component removal
- Size calculation accuracy
- Reinstall state preservation
- Repair manager execution
- Settings dialog hierarchy
- Uninstall wizard dialog structure
- Computer-use provider matrix imports

### 18. Dogfood Issue Tracker Status
All issues DF-001 through DF-007 are **AUTOMATED_ON_PHYSICAL_WORKSTATION VERIFIED** in code and packaged binaries, with human operational status set to `IMPLEMENTED_AWAITING_HUMAN_RETEST`.

### 19. RC.5 Installer Path
`E:\Workspace\Active\AstraRun\dist\installer\AstraRun-Setup-1.0.0-rc.5-dogfood.exe`

### 20. Size & SHA-256
- **Size**: `234,958,745 bytes` (~224.07 MB)
- **SHA-256**: `D95420303264D316E83E8A6E90185C7D2958AB1EBE0B6469FB7456F4726A201B`

### 21. Exact Human Retest Checklist
For the human operator during dogfood testing:
1. Double-click `AstraRun-Setup-1.0.0-rc.5-dogfood.exe` from File Explorer.
2. Verify installer options: Desktop Shortcut (checked), Autostart (checked).
3. Verify First-Run Wizard:
   - Check Hardware page: Verify NVIDIA GeForce RTX 2050 (4 GB) is identified as primary compute GPU.
   - Check Models page: Verify Spark-X2.5 and Qwen 2.5 Coder detection.
   - Check Preferences page: Test the `Browse...` folder button.
4. Press `Alt + Space` to summon launcher: Enter `"What GPU do I have and how much VRAM is free right now?"` and observe immediate inline answer.
5. In system tray, right-click AstraRun icon -> select `Settings`:
   - Inspect the 5 tabs (`General`, `Models & Storage`, `Machine Profile`, `Repair & Logs`, `About`).
   - Click `Run Repair & Verification` and confirm 6/6 items pass.
6. Open Windows `Installed Apps` -> click `Uninstall`:
   - Verify AstraRun Uninstaller dialog appears with the Astra near-black theme.
   - Verify external models are marked read-only with preservation note.
   - Test `Cancel uninstall` to ensure uninstaller aborts cleanly without altering machine state.
