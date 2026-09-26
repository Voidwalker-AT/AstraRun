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

---

## ADR-006: Precomputed Candidate Terms for Low-Latency Fuzzy Matching
- **Status**: ACCEPTED
- **Context**: Matching ~400+ installed applications and system shortcuts on every keystroke requires evaluating exact, prefix, token, acronym, single-drop typo, and subsequence algorithms. Doing regex tokenization and lowercasing inside per-keystroke inner loops caused p95 search latency to climb to ~15.5ms.
- **Decision**: Precompute clean lowercase terms, token lists, and acronyms at candidate creation time (`PrecomputedTerm`) when building or refreshing the `SearchIndex`. During live search queries, compare the query directly against these precomputed structures.
- **Consequences**:
  - Keystroke search latency dropped by 5x to ~3.03ms mean and 21µs p50.
  - Zero garbage collection pressure during interactive typing.
  - Keeps UI fluid at 60+ FPS while typing without needing a separate search worker process.

---

## ADR-007: Strict 0.75 Auto-Execution Threshold to Prevent False Execution
- **Status**: ACCEPTED
- **Context**: In v0.1, unknown commands fell through to rejection. In v0.2, fuzzy matching allows typo tolerance (e.g. `notpad` -> `Notepad`). However, aggressive fuzzy matching on destructive, unsupported, or nonsense inputs (e.g. `kill port 3000`, `asdfgh`, `open the project from yesterday`) could erroneously trigger an app or folder launch with disastrous side effects.
- **Decision**: Establish an immutable auto-execution threshold `AUTO_EXECUTE_MIN_SCORE = 0.75`. Candidates with scores below 0.75 are shown in suggestions as hints if requested, but pressing `Enter` on raw text will never auto-execute them. Instead, they are cleanly rejected as `Decision(tool="unknown")`.
- **Consequences**:
  - False Execution Rate on unsupported/ambiguous queries is empirically proven at 0.0% across 88 benchmark queries.
  - Typo tolerance remains effective (single-drop typos score 0.80 - 0.86 >= 0.75).
  - Out-of-scope commands remain safely quarantined for future intelligent classifiers (Laya/Kev).

---

## ADR-008: Local-Only Privacy Guarantee for Routing Telemetry
- **Status**: ACCEPTED
- **Context**: To train future intelligent classifiers (Laya) and semantic routers (Kev), we need empirical logs of user requests, latencies, and execution decisions. However, developer command launchers frequently receive sensitive data (e.g. tokens, URLs with credentials, confidential project paths).
- **Decision**:
  - Telemetry is recorded strictly to a local, append-only JSONL file (`data/routing_events.jsonl`).
  - No network socket, HTTP client, or cloud transmission telemetry code is included.
  - All incoming query strings are passed through a defensive credential redactor before logging.
  - Telemetry is fully toggleable via `config/settings.json` (`telemetry.enabled = false`).
- **Consequences**:
  - Zero data leakage risk.
  - Zero telemetry network overhead or external dependencies.
  - High-fidelity local dataset for offline model evaluation.

---

## ADR-009: Foreground-Window-Aware Monitor Placement with Cursor Fallback
- **Status**: ACCEPTED
- **Context**: In multi-monitor developer workstations, launching a utility on the wrong monitor (e.g., secondary reference display instead of the monitor where the developer is actively writing code) breaks focus and causes visual disorientation.
- **Decision**: Query the active foreground window handle via `ctypes.windll.user32.GetForegroundWindow()`, map it to its enclosing monitor via `MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)`, and extract its working area. If no foreground window exists or it is minimized, fall back to the monitor containing the mouse cursor, and finally the primary monitor.
- **Consequences**:
  - Launcher always appears directly in the user's active visual field.
  - Respects per-monitor taskbar boundaries and DPI scales.
  - Graceful degradation if Win32 API calls encounter non-standard window managers.

