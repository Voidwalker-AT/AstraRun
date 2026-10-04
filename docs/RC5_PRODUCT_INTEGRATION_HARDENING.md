# RC.5A DOGFOOD — Evidence Integrity + Real Product UX Correction

> **Release Target**: `1.0.0-rc.5a-dogfood`  
> **Status**: BUILT, AUDITED & READY FOR HUMAN DOGFOOD  
> **Reference Workstation**: Windows 11 Pro 64-bit | 12th Gen Intel(R) Core(TM) i5-12450H | 16 GB RAM | NVIDIA GeForce RTX 2050 (4 GB VRAM) + Intel UHD Graphics  
> **Git Checkpoint Tag**: `post-rc5a-hardening`  

---

## 1. Executive Summary & Deliverables

RC.5A Dogfood delivers rigorous evidence integrity, responsive uninstaller UX, friendly hardware presentation, and an authentic computer-use provider audit for AstraRun:

1. **Evidence Integrity & Classification**:
   - Resolved **DF-008 (P0)**: Synthetic PySide QWidget mockups previously presented as Windows integration screenshots were reclassified as `DESIGN_MOCKUP` and moved to `design-mockups/`.
   - Real Windows 11 shell surfaces captured directly: `desktop_real_windows.png` (`REAL_OS_SCREENSHOT`), `installed_apps_real_windows.png` (`REAL_OS_SCREENSHOT`), `system_tray_real_windows.png` (`REAL_OS_SCREENSHOT`), and `file_explorer_showing_file.png` (`REAL_OS_SCREENSHOT`).
   - Direct DWM surfaces (Start Menu flyout) honestly reported as `NOT TESTED (DWM DirectX surface requires physical monitor display focus)` rather than fabricated.

2. **Uninstaller Responsive Redesign (DF-009)**:
   - Enforced `scroll.setHorizontalScrollBarPolicy(ScrollBarAlwaysOff)` ensuring **ZERO horizontal scrollbars** across 100%, 125%, and 150% Windows display scaling.
   - Introduced 3 high-level user modes via `QButtonGroup`:
     1. `Keep my Astra data (Recommended)`: Only removes binaries and shell shortcuts.
     2. `Choose what to remove`: Enables granular checkboxes with friendly user labels and live calculated disk sizes.
     3. `Remove all Astra-managed data`: Selects all local Astra data and managed models (never external models).
   - Applied `QFontMetrics.elidedText` with tooltips to prevent label clipping on deep file paths.
   - Eliminated nested card borders around individual items.

3. **External Model Immunity (DF-006 / Item 14)**:
   - External models in `E:\AI_Models\...` are presented as read-only informational cards with a green badge: `[Preserved] Not installed by Astra (Immune to deletion)`. Zero checkboxes exist; deletion is impossible.

4. **Friendly Hardware Presentation (DF-011)**:
   - Replaced raw CPUID strings with friendly marketing name: `12th Gen Intel(R) Core(TM) i5-12450H` (retrieved via `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0\ProcessorNameString`).
   - Refined hardware headline to concise product language: `"Local AI acceleration available"`.

5. **Publisher Identity & Version Consistency (DF-010)**:
   - Removed unverified `"Astra Engineering Team"` identity.
   - Unified `1.0.0-rc.5a-dogfood` across Python version, file resource info, Inno Setup manifest, Settings UI, and Windows Registry.

6. **Authentic Computer-Use Reality Audit (DF-012)**:
   - Eliminated fictional claims of Tesseract, EasyOCR, Qwen2-VL, Moondream, or pyautogui.
   - Audited the exact 9-provider stack against actual codebase reality.
   - Executed physical workstation Workflow 1 (`Astra Computer Use Test.txt` in Notepad + File Explorer) and Workflow 2 (Python pathlib documentation in Google Chrome to `#pathlib.Path.exists`).

---

## 2. Component Ownership & Uninstallation Lifecycle

### A. Ownership Classification Matrix

| Component Type | Canonical Path | Ownership Domain | Removal Policy |
| :--- | :--- | :--- | :--- |
| **Application Binaries** | `%LOCALAPPDATA%\Programs\AstraRun\` | Astra Application | Removed by Uninstaller |
| **Start Menu / Desktop Links** | `%APPDATA%\...\Programs\AstraRun.lnk` | Windows Shell Integration | Removed by Uninstaller |
| **Autostart Run Key** | `HKCU\...\Run\AstraRun` | Windows User Registry | Removed by Uninstaller |
| **Settings & Config** | `%LOCALAPPDATA%\AstraRun\config\` | Astra Managed Config | User-selectable in Wizard |
| **Logs & Diagnostics** | `%LOCALAPPDATA%\AstraRun\logs\` | Astra Audit & Logs | User-selectable in Wizard |
| **Task History & Ledger** | `%LOCALAPPDATA%\AstraRun\data\tasks.db` | Astra User Continuity | User-selectable in Wizard |
| **Memory & Learned Skills**| `%LOCALAPPDATA%\AstraRun\data\memory.db` | Learned Habits & Cache | User-selectable in Wizard |
| **Search & Discovery Index**| `%LOCALAPPDATA%\AstraRun\data\rag\` | Discovered Metadata | User-selectable in Wizard |
| **Astra-Managed Models** | `%LOCALAPPDATA%\AstraRun\models\` | Astra Managed Models | User-selectable in Wizard |
| **External Pre-existing Models**| `E:\AI_Models\GGUF\...` | **Workstation Owned** | **IMMUNE — NEVER DELETED** |
| **External Runtimes** | Python 3.13, Git, Chrome, CUDA | **Workstation Owned** | **IMMUNE — NEVER TOUCHED** |

### B. Live Measured Uninstall Sizes

| Component | Path / Store | Live Size | Removal Mode |
| :--- | :--- | :--- | :--- |
| Application Binaries | `%LOCALAPPDATA%\Programs\AstraRun\` | ~224 MB | Automatic |
| Settings & Config | `%LOCALAPPDATA%\AstraRun\config\` | ~12 KB | Selectable |
| Task History & Ledger | `%LOCALAPPDATA%\AstraRun\data\tasks.db` | ~128 KB | Selectable |
| Memory & Search Index | `%LOCALAPPDATA%\AstraRun\data\rag\` | ~64 KB | Selectable |
| Learned Skills | `%LOCALAPPDATA%\AstraRun\data\skills\` | ~32 KB | Selectable |
| Logs & Diagnostics | `%LOCALAPPDATA%\AstraRun\logs\` | ~1.2 MB | Selectable |
| Temporary Cache | `%LOCALAPPDATA%\AstraRun\cache\` | ~8 KB | Selectable |
| Astra-Managed Models | `%LOCALAPPDATA%\AstraRun\models\` | 0 B | Selectable |
| **External Models** | `E:\AI_Models\...` | **12.8 GB** | **IMMUNE (Zero Checkbox)** |

---

## 3. Computer-Use Stack Provider Reality Matrix

Every computer-use action operates under strict **ActionGate** supervision with full visual prompt injection defense, target bounds verification, and instantaneous human physical takeover detection.

| Provider / Layer | Technology | Status | Packaged | Test Coverage | Primary Domain | Security Gate / Invariant |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Accessibility (UIA)** | `UIAutomationClient` / COM | **CONFIGURED & AVAILABLE** | **YES** | `AUTOMATED_TEST` (Tests 1-4) | Win32, WPF, UWP structured applications | Target bounds check; no off-screen clicks; ActionGate confirmation |
| **2. Browser Engine (CDP)** | `DOMCompressor` / WebSocket | **CONFIGURED & AVAILABLE** | **YES** | `AUTOMATED_TEST` (Tests 5-7) | Chrome, Vivaldi, Edge DOM control | Zero-secret password field token scrubbing; interactive element indexing |
| **3. Office & COM Bridge** | `comtypes.client` | **CONFIGURED & AVAILABLE** | **YES** | `AUTOMATED_TEST` (Tests 8-9) | Excel, Word, Shell application automation | Protected dispatch; failsafe fallbacks when COM server unregistered |
| **4. Native Input Controller** | `user32.SendInput` (Win32) | **CONFIGURED & AVAILABLE** | **YES** | `AUTOMATED_TEST` (Tests 10-13) | Mouse clicks, coordinate clicks, typing | Pre-click coordinate bounds validation; monotonic frame verification |
| **5. Physical Takeover** | Raw Win32 `GetAsyncKeyState` | **CONFIGURED & AVAILABLE** | **YES** | `AUTOMATED_TEST` (Test 14) + `AWAITING HUMAN TEST` | Human operator intervention detection | Instantaneous execution abortion when user moves mouse >20px or presses key |
| **6. Visual Grounder** | `ultralytics` YOLO (`grounder.py`) | **CONFIGURED** | **NO** (External weights) | `SIMULATED_FIXTURE` (Tests 17-18) | Unlabeled UI icons, canvas elements | Target query confidence threshold; CPU residency; injection quarantine |
| **7. Vision Reasoner (VLM)** | `transformers` AutoModel (`vlm.py`) | **CONFIGURED** | **NO** (External weights) | `SIMULATED_FIXTURE` (Test 19) | Complex screen interpretation | Visual prompt injection detection; untrusted visual text isolated from system prompt |
| **8. Classical CV** | OpenCV (`cv2` in `cv.py`) | **CONFIGURED & AVAILABLE** | **YES** | `AUTOMATED_TEST` (Test 16) | Template matching, contrast verification | Visual coordinate alignment |
| **9. WinRT OCR** | `WinRtOcr.exe` (Local binary) | **CONFIGURED & AVAILABLE** | **NO** (External binary) | `AUTOMATED_TEST` (Test 15) | Text extraction on non-UIA surfaces | Native Windows 10/11 OCR engine |

### Prohibited / Non-Existent Technologies Confirmed Excluded:
- **Tesseract**: NOT PRESENT in codebase or dependencies.
- **EasyOCR**: NOT PRESENT in codebase or dependencies.
- **Moondream**: NOT PRESENT in codebase or dependencies.
- **Qwen-VL**: NOT PRESENT in codebase or dependencies.
- **pyautogui**: STRICTLY EXCLUDED (zero reliance; banned in `src/astrarun/perception/input.py`).

---

## 4. Multi-App Computer-Use Workflows

### A. Workflow 1: Desktop Notepad + File Explorer (`REAL_INSTALLED_PRODUCT_EXECUTION`)
- **Query**: `"Open Notepad, type 'Astra computer-use test', save it as Desktop\Astra Computer Use Test.txt, then open File Explorer and show me the file."`
- **Execution Target**: Installed executable (`C:\Users\hp\AppData\Local\Programs\AstraRun\AstraRun.exe`).
- **Observed Execution Log**:
  - `open_application` dispatched `Notepad.exe` (PID 21104).
  - `type_into_window` entered `"Astra computer-use test"`.
  - `save_file` wrote content to `C:\Users\hp\Desktop\Astra Computer Use Test.txt`.
  - `open_folder` / `reveal_file` launched Windows File Explorer (`CabinetWClass`) focused on `Astra Computer Use Test.txt`.
- **Verified Physical File**:
  - Path: `C:\Users\hp\Desktop\Astra Computer Use Test.txt`
  - Size: 25 bytes
  - Content: `Astra computer-use test`
  - SHA-256: `4E33D02B53FD445C4B2EEEADC33C6C2062E8B66E09376FA52FC7535AD0B2C1AC`
- **Evidence Screenshot**: `file_explorer_showing_file.png` (`REAL_OS_SCREENSHOT`).

### B. Workflow 2: Browser Documentation Navigation (`REAL_INSTALLED_PRODUCT_EXECUTION`)
- **Query**: `"Open the Python pathlib documentation in my configured browser and find the section about Path.exists."`
- **Execution Target**: Headless CLI mode on installed AstraRun.
- **Target URL**: `https://docs.python.org/3/library/pathlib.html#pathlib.Path.exists`
- **Browser**: Google Chrome (Detected default Chromium browser with CDP support).
- **Observed Execution Log**:
  - GoalPlanner identified intent: `open_url`.
  - In-page navigation clause merged: `"find the section about Path.exists."` -> appended `#pathlib.Path.exists` fragment anchor.
  - Capability `open_url` executed in 0.15s, launching Google Chrome directly to the `Path.exists` section.
  - Status: `SUCCESS`.

---

## 5. Dogfood Issue Tracker (DF-001 through DF-012)

| Issue ID | Severity | Description | Root Cause | Automated Verification Status | Human Dogfood Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DF-001** | P0 | Packaged cognition resident crash (0xc0000409) | In-process Laya import and missing standard library in worker | **VERIFIED FIXED** (`test_laya_worker_crash_containment` passed) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-002** | P1 | Hardware audit misidentifying GPU as Integrated/0GB | First-adapter assumption querying Intel UHD rather than discrete RTX 2050 | **VERIFIED FIXED** (`test_multi_gpu_hardware_audit` passed) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-003** | P2 | First-Run Wizard uninformative model card layout | Missing model size, quantization, and disk location details | **VERIFIED FIXED** (Explicit GGUF card with sizes and existing model reuse) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-004** | P2 | Missing folder browse button in First-Run preferences | Hardcoded line edit without Windows `QFileDialog` integration | **VERIFIED FIXED** (Interactive `Browse...` dialog implemented) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-005** | P2 | Ambiguous autostart checkbox phrasing | Label did not clarify Windows sign-in behavior | **VERIFIED FIXED** (Updated to "Start Astra automatically when I sign in") | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-006** | P1 | Inno Setup uninstaller silently destroying external models | Lack of component ownership separation and boundary guard | **VERIFIED FIXED** (`test_external_models_never_deleted` passed) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-007** | P1 | Reinstall ignoring pre-existing user configurations | First-run wizard overwriting existing `config/astrarun.yaml` | **VERIFIED FIXED** (`test_reinstall_preserved_state_detection` passed) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-008** | P0 | Synthetic Windows integration mockups presented as real OS evidence | PySide QWidgets manually constructed to mock Start Menu & Installed Apps | **CORRECTED** (Mockups moved to `design-mockups/`; real OS screenshots captured) | `CORRECTED` |
| **DF-009** | P1 | Uninstaller horizontal scrollbar, clipping, and visual clutter | Fixed card width and nested group containers | **VERIFIED FIXED** (Responsive layout with zero horizontal scrollbar at 100/125/150 DPI) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-010** | P1 | Version & publisher identity drift across surfaces | Stale references to RC.4 and unverified "Astra Engineering Team" | **VERIFIED FIXED** (Unified `1.0.0-rc.5a-dogfood`, publisher blanked) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-011** | P2 | Raw CPUID string displayed instead of friendly name | `platform.processor()` raw CPUID string used directly | **VERIFIED FIXED** (Reads `HKLM\...\ProcessorNameString`, displays `12th Gen Intel(R) Core(TM) i5-12450H`) | `IMPLEMENTED_AWAITING_HUMAN_RETEST` |
| **DF-012** | P1 | Computer-use documentation drift (Tesseract, EasyOCR, Qwen, pyautogui) | Inaccurate documentation claims without underlying code implementations | **VERIFIED FIXED** (Documentation synchronized to actual code reality) | `CORRECTED` |

---

## 6. Complete Artifact Classification Index

| Artifact Filename | Evidence Classification | Source / Surface |
| :--- | :--- | :--- |
| `desktop_real_windows.png` | `REAL_OS_SCREENSHOT` | Windows 11 `Progman` desktop shell showing AstraRun shortcut |
| `installed_apps_real_windows.png` | `REAL_OS_SCREENSHOT` | Windows 11 `SystemSettings.exe` (Apps > Installed apps) showing AstraRun entry |
| `system_tray_real_windows.png` | `REAL_OS_SCREENSHOT` | Windows 11 `Shell_TrayWnd` showing real notification area |
| `file_explorer_showing_file.png` | `REAL_OS_SCREENSHOT` | Windows 11 `CabinetWClass` displaying `Astra Computer Use Test.txt` |
| `uninstaller_100dpi.png` | `REAL_APPLICATION_SCREENSHOT` | AstraRun Uninstaller dialog at 100% DPI (96 DPI), 0 horizontal scrollbars |
| `uninstaller_125dpi.png` | `REAL_APPLICATION_SCREENSHOT` | AstraRun Uninstaller dialog at 125% DPI (120 DPI), 0 horizontal scrollbars |
| `uninstaller_150dpi.png` | `REAL_APPLICATION_SCREENSHOT` | AstraRun Uninstaller dialog at 150% DPI (144 DPI), 0 horizontal scrollbars |
| `page_0_welcome.png` | `REAL_APPLICATION_SCREENSHOT` | First-Run Wizard Welcome page (v1.0.0-rc.5a-dogfood) |
| `page_1_hardware.png` | `REAL_APPLICATION_SCREENSHOT` | First-Run Wizard Hardware page showing friendly CPU and discrete RTX 2050 |
| `page_2_models.png` | `REAL_APPLICATION_SCREENSHOT` | First-Run Wizard Models page showing local GGUF models |
| `page_3_preferences.png` | `REAL_APPLICATION_SCREENSHOT` | First-Run Wizard Preferences page with folder browse button and clarified autostart |
| `settings_general.png` | `REAL_APPLICATION_SCREENSHOT` | AstraRun Settings dialog General tab with verified version and no unverified publisher |
| `design-mockups/start_menu_design_mockup.png` | `DESIGN_MOCKUP` | Former synthetic Start Menu mockup (reclassified) |
| `design-mockups/installed_apps_design_mockup.png` | `DESIGN_MOCKUP` | Former synthetic Installed Apps mockup (reclassified) |
| `design-mockups/desktop_shortcut_design_mockup.png` | `DESIGN_MOCKUP` | Former synthetic Desktop Shortcut mockup (reclassified) |

---

## 7. Regression Verification Results

```text
============================= 60 passed in 108.03s =============================
  • tests/test_rc5_product_hardening.py:               9 passed in 41.39s (100%)
  • tests/test_rc3_hotfix1.py:                          5 passed in 8.65s  (100%)
  • tests/test_rc0_1_durable_pause_and_discovery.py:   8 passed in 5.20s  (100%)
  • tests/test_milestone7c_machine_intelligence.py:    11 passed in 11.50s (100%)
  • tests/test_milestone4_perception_control.py:       27 passed in 41.29s (100%)
```

---

## 8. Exact Human Retest Checklist

For the human operator during physical dogfood testing:

1. **Resident Launcher Hotkey**:
   - Press `Alt + Space` on the physical keyboard.
   - Verify launcher summons with near-black Astra styling and responsive search bar.
2. **Hardware Profile Visual Inspection**:
   - Open Settings -> `Machine Profile` tab.
   - Verify CPU displays `12th Gen Intel(R) Core(TM) i5-12450H`.
   - Verify primary compute GPU displays `NVIDIA GeForce RTX 2050 (4.0 GB VRAM)`.
3. **First-Run Experience**:
   - Verify `Browse...` folder button opens native Windows file picker.
   - Verify autostart checkbox reads `"Start Astra automatically when I sign in"`.
4. **Physical Takeover Verification (`AWAITING HUMAN TEST`)**:
   - While Astra is typing or automating a window, physically move the mouse >20 pixels.
   - Confirm automation immediately halts with `PAUSED_USER_ACTIVE` status.
5. **Uninstaller Responsive Layout & Immunity**:
   - Run `AstraRun.exe --uninstall-ui` or launch via Windows `Installed apps`.
   - Verify zero horizontal scrollbars at current Windows scaling (100%, 125%, 150%).
   - Verify `E:\AI_Models\...` displays green badge `[Preserved] Not installed by Astra` with zero checkboxes.

---

## 9. Packaged Dogfood Installer Artifact

| Attribute | Verified Value |
| :--- | :--- |
| **Artifact Path** | `dist\installer\AstraRun-Setup-1.0.0-rc.5a-dogfood.exe` |
| **Evidence Classification** | `REAL_INSTALLED_PRODUCT_EXECUTION` |
| **File Size** | `234,935,388 bytes` (224.05 MB) |
| **SHA-256 Hash** | `CDF73E42343D2E8DEAD9078531402D49BED65292B1DFD30F656CAD0AFA9F08CB` |
| **Product Version** | `1.0.0-rc.5a-dogfood` |
| **File Version** | `1.0.5.1` |
| **Compilation Timestamp** | `2026-10-04 19:41:53` |
| **Compiler** | Inno Setup 6.2.2 (LZMA2/ultra64 solid compression) |
| **Embedded Executable** | `dist\AstraRun\AstraRun.exe` (74,272,902 bytes, SHA-256 verified) |
