# Architecture Decision Records (ADRs)

---

## ADR-001: Choice of UI Framework — Python + PySide6
- **Status**: ACCEPTED
- **Context**: The launcher must be fast, native-feeling, modern, dark-mode friendly, and capable of direct Windows desktop and display integration. It must not feel like a sluggish web view or consume hundreds of megabytes like Electron.
- **Decision**: PySide6 (Qt 6 for Python) was chosen.
- **Consequences**:
  - Extremely fast render times and native window handle access.
  - Zero-flicker frameless window manipulation with native High-DPI support.
  - Lightweight compared to Electron (~50MB idle RAM vs 300MB+ for Electron).
  - Python ecosystem integration allows seamless future AI/ML bridge integration.

---

## ADR-002: Structured Tool Registry Instead of Arbitrary Shell Execution
- **Status**: ACCEPTED
- **Context**: Many command-line launchers parse user input into `cmd.exe /c ...` or `os.system(user_input)`, leading to shell injection risks, fragile quoting, and dangerous unintended side-effects.
- **Decision**: AstraRun strictly prohibits raw shell execution. The router outputs a typed `Decision` specifying a registered tool (`open_app`, `open_folder`, `open_url`) and structured arguments. The tool registry validates arguments and executes the action using safe Win32 APIs (`os.startfile`, `subprocess.Popen` with argument lists, or `ctypes ShellExecuteW`).
- **Consequences**:
  - Elimination of command injection vectors.
  - Provides a safe sandbox for future autonomous AI routing (Laya/Kev).
  - High observability and auditability of all launcher operations.

---

## ADR-003: Resident Process with Win32 Native RegisterHotKey Loop
- **Status**: ACCEPTED
- **Context**: A global hotkey must summon the launcher instantaneously (<50ms). Starting a new Python process on hotkey press would introduce several hundred milliseconds of cold-start latency.
- **Decision**: AstraRun runs as a resident background process with a hidden, pre-initialized PySide6 window. Global hotkey listening is handled by a dedicated background thread utilizing native Win32 `user32.RegisterHotKey` and `GetMessageW`.
- **Consequences**:
  - Instantaneous UI appearance on `Alt+Space` (`show()` and `setFocus()`).
  - Near-zero idle CPU usage (thread blocks natively in OS kernel message queue).
  - No dependency on invasive global keyboard hooks (`SetWindowsHookEx`) or third-party hook libraries that trigger false-positive antivirus heuristics.

---

## ADR-004: Router Abstraction for Future Multi-Tiered AI (Laya / Kev)
- **Status**: ACCEPTED
- **Context**: v0.1 must be fast and 100% functional without requiring heavy LLMs, but future iterations will incorporate fast local intent classifiers (Laya) and semantic orchestration (Kev).
- **Decision**: The routing pipeline is decoupled behind an abstract base class `BaseRouter` with method `route(request, context) -> Decision`. v0.1 implements `DeterministicRouter`.
- **Consequences**:
  - The UI and Tool Registry are completely agnostic to the intelligence source.
  - Adding Laya or Kev requires only implementing the router contract and composing it into a fallback chain.

---

## ADR-005: Decoupled Discovery Cache & Windows Known Folder Resolution
- **Status**: ACCEPTED
- **Context**: Launching applications and folders requires finding installed software without scanning the entire hard drive on every hotkey press, and without hardcoding machine-specific usernames.
- **Decision**:
  - Applications are discovered via the Windows `App Paths` registry, `PATH`, and user-defined configuration, and cached in memory.
  - Known folders are queried dynamically via Windows Registry `User Shell Folders` and Windows Shell APIs.
- **Consequences**:
  - Hotkey activation is zero-latency because discovery is done at startup or reloaded on config change.
  - Fully portable across different Windows user accounts and drive layouts.
