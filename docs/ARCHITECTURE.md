# AstraRun Architecture Specification

> **Version**: 0.4.0  
> **Target Platform**: Windows 11 / Windows 10 (64-bit)  
> **Status**: APPROVED  

---

## 1. System Overview

AstraRun is a local Windows intelligent command launcher designed to act as the foundational command interface for an evolving AI-assisted workstation control ecosystem. 

Unlike traditional launchers that rely on string-interpolated shell execution or web technologies, AstraRun is built with:
- **Zero Raw Shell Ingestion**: Strict security pipeline ensuring user requests are parsed into typed decisions and executed exclusively through registered, validated tools.
- **Persistent Low-Latency Process**: Resident process with a hidden, pre-warmed Qt UI and a dedicated background Win32 message loop for instantaneous hotkey wake-up.
- **Deterministic & Fuzzy Multi-Signal Search Engine**: Fast in-memory candidate index with precomputed terms, hierarchical fuzzy scoring (exact, prefix, token, acronym, single-drop typo, subsequence, edit-distance), and bounded usage ranking.
- **Foreground-Aware Monitor Placement**: Native Win32 display detection anchoring the launcher to the active foreground application's display with mouse cursor and primary monitor fallbacks.
- **Local-Only Privacy-Preserving Telemetry & Shadow Logging**: Structured routing event collection and dual-track shadow evaluation logging with defensive credential redaction and zero off-machine network egress.
- **Laya Neural Decision Router in Shadow Mode (v0.3)**: Integrated non-autoregressive decision model (`convaiinnovations/laya`, 421M parameter ModernBERT-large) evaluated strictly in shadow mode with ZERO production execution authority.
- **Kev Neural Decision Router in Shadow Mode (v0.4)**: Integrated single-pass decision model (`jaredpalmer/kev-0.8b`, PEFT LoRA adapter on `Qwen/Qwen3.5-0.8B-Base` backbone with 256-dim dot-product `PointerHead` and calibrated temperature $T \approx 2.351$) evaluated strictly in shadow mode with ZERO production execution authority.
- **Fixed Intent Taxonomy**: 10 mutually exclusive semantic categories separating abstract intent prediction from deterministic parameter binding and policy enforcement.
- **Multi-Model Evolutionary Router Architecture**: Pluggable routing interface transitioning safely from pure deterministic matching (v0.2) to single shadow semantic evaluation (v0.3), dual-model comparative evaluation (v0.4), cascading resolution, and multi-step agent planning (v0.5+).

---

## 2. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph Input_Layer ["Input & Activation Layer"]
        HK["Global Hotkey (Win32 Alt+Space)"] -->|WM_HOTKEY| HKT["Hotkey Listener Thread"]
        HKT -->|Qt Signal| UI["PySide6 Launcher Window"]
        Pos["Win32 Positioning Engine"] -.->|Target Work Area| UI
        User["User Typing"] -->|Input String| UI
    end

    subgraph Search_Engine ["Search & Ranking Engine"]
        UI -->|Query As You Type| Index["SearchIndex (In-Memory)"]
        Index -->|Precomputed Candidates| Matcher["FuzzyMatcher"]
        Matcher -->|Multi-Signal Scoring| Scorer["FuzzyScorer"]
        Usage["UsageStore (data/usage.json)"] -.->|Bounded Boost <=0.03| Scorer
        Scorer -->|Ranked SearchResults| UI
    end

    subgraph Core_Pipeline ["Decision & Execution Pipeline"]
        UI -->|Committed Request| Router["DeterministicRouter"]
        Router -->|Exact / Prefix / Alias| DirectCheck{"Direct Match?"}
        DirectCheck -->|Yes| Dec["Decision Object"]
        DirectCheck -->|No| IndexFallback["SearchIndex Query"]
        IndexFallback -->|Score >= 0.75| Dec
        IndexFallback -->|Score < 0.75| Unknown["Unknown Decision"]
        Dec -->|Log Event| Telemetry["Telemetry Collector (Redacted)"]
        Dec -->|Validation & Policy| Reg["Tool Registry"]
        Reg -->|Dispatched Handler| Tool["Registered Tool (open_app / open_folder / open_url / refresh_apps)"]
        Reg -->|Record Success| Usage
    end

    subgraph OS_Layer ["Operating System Layer"]
        Tool -->|Win32 ShellExecute / os.startfile / subprocess argv| WinOS["Windows OS"]
    end
```

---

## 3. Core Component Boundaries

### 3.1. Hotkey Layer (`astrarun.hotkeys.manager`)
- Runs a dedicated, non-blocking Win32 thread listening for `WM_HOTKEY` via `GetMessageW`.
- Uses native `ctypes.windll.user32.RegisterHotKey` with `MOD_ALT | MOD_NOREPEAT` and `VK_SPACE`.
- Communicates with the Qt Main Thread exclusively via thread-safe Qt Signals (`hotkey_pressed`).
- Allows hotkey configuration from `config/settings.json` without modifying code.

### 3.2. Presentation Layer (`astrarun.ui.launcher`)
- Implemented with **PySide6** (`QDialog` / `QWidget` with `FramelessWindowHint` and `WindowStaysOnTopHint`).
- Keeps the window resident in memory (`hide()` instead of `close()`) to achieve zero-latency presentation upon hotkey activation.
- Positioned dynamically centered on the active display (or primary display / monitor with cursor).
- Real-time suggestions UI (`SuggestionRowWidget`) displaying title, description, and visual category badges (`APP`, `FOLDER`, `WEB`, `COMMAND`).
- Keyboard-driven event filter:
  - `Escape` -> Hides the launcher and clears state.
  - `Up` / `Down` -> Cycles through ranked suggestions.
  - `Tab` -> Autocompletes input text with selected suggestion title.
  - `Enter` -> Commits selected suggestion or routes raw text through strict policy validation.
  - Focus Out -> Configurable auto-hide behavior.

### 3.3. Search & Ranking Engine (`astrarun.search`)
- **`SearchCandidate`**: In-memory representation of searchable items (applications, folders, URLs, commands). Precomputes clean alphanumeric tokens and acronyms at startup (`PrecomputedTerm`) to eliminate duplicate regex operations during keystrokes.
- **`FuzzyScorer`**: Implements multi-signal scoring hierarchy:
  1. Exact match (`1.0`)
  2. Alias exact match (`0.98`)
  3. Prefix match (`0.92`)
  4. Word token prefix match (`0.88`)
  5. Contiguous substring match (`0.82`)
  6. Acronym match (`0.78`)
  7. Single-drop typo match (`0.80 - 0.86`)
  8. Damerau-Levenshtein edit-distance match (`0.65 - 0.80`)
  9. Subsequence match (`0.60 - 0.70`)
  10. Usage frequency boost (`min(0.03, count * 0.005)`) — strictly bounded so frequency never overrules superior textual relevance.
- **`SearchIndex`**: Fast thread-safe query container caching ~400+ applications, system folders, URL aliases, and internal tools.

### 3.4. Display & Window Positioning Engine (`astrarun.ui.positioning`)
- Queries the active foreground window handle via `ctypes.windll.user32.GetForegroundWindow()`.
- Locates the enclosing monitor using `MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)`.
- Queries monitor work area (excluding taskbars) via `GetMonitorInfoW`.
- Falls back progressively:
  1. Active foreground window monitor.
  2. Monitor containing the mouse cursor (`QCursor.pos()`).
  3. Primary monitor work area.
- Computes launcher coordinates centered horizontally and placed in the upper third vertically for ergonomic eye level.

### 3.5. Routing Layer (`astrarun.routing`)
- Abstraction:
  ```python
  class BaseRouter(ABC):
      @abstractmethod
      def route(self, request: str, context: RoutingContext) -> Decision:
          pass
  ```
- **Deterministic Implementation (`DeterministicRouter`)**:
  - Normalizes whitespace, case, and prefixes (`open`, `launch`, `start`, `go to`, `show`).
  - Stage 1: Fast direct checks against URL aliases, folders, known apps, and raw URLs.
  - Stage 2: Fallback query to `SearchIndex` with strict auto-execution threshold `AUTO_EXECUTE_MIN_SCORE = 0.75`.
  - Rejects ambiguous or low-confidence matches as `Decision(tool="unknown")`, ensuring a 0.0% false execution rate on unsupported queries.

### 3.6. Tool Registry (`astrarun.tools.registry`)
- Registry mapping tool names to typed tool handlers and security metadata.
- Registered tools in v0.2: `open_app`, `open_folder`, `open_url`, `refresh_apps`.
- Enforces risk policy:
  - `LOW`: Safe local operations (opening registered applications, known directories, trusted URLs, internal cache refresh).
  - `MEDIUM`: Operations modifying local files or non-standard protocols.
  - `HIGH`: System modification or elevated processes (requires explicit confirmation).
  - `BLOCKED`: Arbitrary command-line execution or shell invocation (`cmd /c`, `powershell -c`).

### 3.7. Usage Store (`astrarun.usage.store`)
- Tracks launch counts and ISO timestamps in local JSON file (`data/usage.json`).
- Resilient to file corruption, auto-initializes defaults.
- Supplies usage statistics to `FuzzyScorer` for subtle tie-breaking without mutating user intent.

### 3.8. Telemetry Engine (`astrarun.telemetry`)
- Records structured routing and execution events in local append-only JSONL format (`data/routing_events.jsonl`).
- Redacts credentials, tokens, bearer headers, and passwords defensively via regex.
- Zero network code: 100% local, no telemetry packets ever leave the workstation.

### 3.9. Discovery Layer (`astrarun.discovery`)
- **Applications**:
  - Windows `App Paths` registry (`HKLM` and `HKCU`).
  - System PATH.
  - Windows User and System Start Menu `.lnk` shortcuts (`%APPDATA%` and `%PROGRAMDATA%`).
  - Filters out uninstallers, help, and documentation links.
  - Custom user entries in `config/apps.json`.
- **Known Folders**: Dynamically queried via Windows User Shell Folders / `SHGetKnownFolderPath`.

### 3.10. Laya Neural Decision Router (`astrarun.routing.laya`)
- **Upstream Engine**: ModernBERT-large (421M parameters) with single-pass non-autoregressive decision classification head trained via Reinforcement Learning from AI Feedback (RLCD) (`convaiinnovations/laya`).
- **Operational Mode**: Strictly **Shadow Mode** (`"mode": "shadow"`). Evaluates user input in real-time or asynchronously in a daemon thread, with **ZERO production execution authority**.
- **Intent Taxonomy**: Maps input queries across 10 mutually exclusive intents (`open_app`, `open_folder`, `open_url`, `open_project`, `find_file`, `process_action`, `system_action`, `ai_query`, `browser_action`, `unknown`).
- **Execution Authority Separation**: Only primitive intents supported by production tools (`open_app`, `open_folder`, `open_url`) are marked `is_executable_now=True`; all others require multi-step entity resolution or planning (`requires_resolution=True`).
- **Hardware Isolation**: Runs on CPU via `torch+cpu` on Intel Core i5-12450H, achieving ~500ms latency via ONNX Runtime with 0MB VRAM footprint, preserving RTX 2050 for heavy LLM workflows. Canonical weights cached in `E:\AI_Models\HF_CACHE` (Platform Rule 9).

### 3.11. Kev Neural Decision Router (`astrarun.routing.kev`)
- **Upstream Engine**: `jaredpalmer/kev-0.8b` (PEFT LoRA adapter on `Qwen/Qwen3.5-0.8B-Base` backbone with 256-dimensional dot-product `PointerHead`).
- **Operational Mode**: Strictly **Shadow Mode** (`"mode": "shadow"`). Zero production execution authority.
- **Decision Mechanism**: Employs Qwen FIM/box delimiters (`<|fim_prefix|>`, `<|fim_middle|>`, `<|box_start|>`, `<|box_end|>`, `<|fim_suffix|>`) and dot-product pointer logits scaled by a fitted temperature parameter ($T \approx 2.351096$).
- **Inference Profile**: Non-autoregressive single forward pass. On CPU, due to absence of specialized `flash-linear-attention` / `causal_conv1d` kernels on Windows, execution falls back to PyTorch interpreter loops (~15-20s per query).
- **Abstention Tendency**: High abstention on out-of-domain desktop launcher actions, safely defaulting to `unknown`.

### 3.12. Multi-Model Shadow Telemetry Pipeline (`astrarun.telemetry.shadow_collector`)
- Independent, thread-safe shadow event collectors: `LayaShadowEventCollector` (`data/laya_shadow_events.jsonl`) and `KevShadowEventCollector` (`data/kev_shadow_events.jsonl`).
- Pairs live production deterministic decisions with concurrent neural predictions.
- Appends structured records with schema versioning, execution latencies, full probability distributions, and defensive credential redaction (`redact_sensitive_data()`).
- Dispatches asynchronously on background daemon threads without delaying UI responsiveness or command execution.

---

## 4. Execution Flow Sequence

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Hotkey as Win32 Hotkey Thread
    participant UI as PySide6 Launcher Window
    participant Index as SearchIndex
    participant Router as Deterministic Router
    participant Telemetry as Telemetry Collector
    participant Registry as Tool Registry
    participant Executor as Tool Handler
    participant Windows as Windows OS

    User->>Hotkey: Presses Alt+Space
    Hotkey->>UI: Emits hotkey_pressed signal
    UI->>UI: Position on foreground monitor, show(), focus input
    User->>UI: Types "notpad" (typo)
    UI->>Index: search("notpad", limit=5)
    Index-->>UI: Return [SearchResult("Notepad", score=0.86, tool="open_app")]
    UI->>UI: Render suggestion row with [APP] badge
    User->>UI: Presses Enter
    UI->>Router: route("notpad", context)
    Router->>Index: Fallback search("notpad") -> top score 0.86 >= 0.75
    Router-->>UI: Return Decision(tool="open_app", args={"app": "notepad"}, confidence=0.86)
    UI->>Telemetry: log_event(request="notpad", decision, success=True)
    UI->>Registry: execute(decision)
    Registry->>Executor: dispatch("open_app", {"app": "notepad"})
    Executor->>Windows: Launch target executable safely
    UI->>UI: Clear input & hide()
```

---

- **System Exceptions**: Caught by global exception boundaries, recorded in `logs/astrarun.log` with stack traces, while keeping the launcher UI stable and responsive.

---

## 6. Decision Fusion, Entity Resolution & External Reference Architecture (v0.5)

### 6.1. Decision Fusion Engine (`astrarun.routing.fusion`)
- Ensembles Generic Zero-Shot Laya and Domain-Adapted AstraRun-Laya across modes E0 through E5.
- Computes statistical disagreement metrics:
  - Top-choice binary agreement indicator.
  - Jensen-Shannon divergence $D_{\text{JS}}(P_{\text{gen}} \parallel P_{\text{ft}}) \in [0, 1]$.
  - Shannon entropy $H(P_{\text{fused}})$ measuring epistemic prediction uncertainty.
- In Mode E4 and E5, executes an active **disagreement gate**: if models disagree or $D_{\text{JS}} > 0.25$, forces safe abstention to `unknown`.
- In Mode E5, applies multi-question gating: rejects if consequence risk is `BLOCKED`, and forces disambiguation if ambiguity is `ambiguous` or `unknown`.

### 6.2. Deterministic Entity Resolution Engine (`astrarun.routing.entity_resolver`)
- Translates high-level semantic intents into concrete, verified workstation targets without neural hallucinations.
- Target Resolvers:
  - `open_project`: Resolves against `workspace.json` (read-only) in `E:\Workspace`. Emits `status="ambiguous"` with candidate list if multiple projects match within $\Delta \le 0.15$.
  - `open_app`: Resolves against discovered Windows applications via `AppDiscoveryCache`.
  - `open_folder`: Resolves known directories via `FolderResolver`.
  - `open_url`: Validates FQDN and URI schema.
  - `process_action`: Extracts port numbers and process names; verifies against hard policy.
  - `system_action`: Power, locking, and display management.
- Hard Policy Security Boundaries:
  - System processes (`lsass`, `csrss`, `svchost`, `smss`, `wininit`, etc.) are unconditionally blocked.
  - Privileged ports ($\le 1023$) are strictly protected from automated termination.
  - Destructive commands (`rmdir /s /q`, `format`, `del system32`) are intercepted prior to resolution.
- **ZERO Production Authority**: Emits structured `ProposedAction` objects for evaluation and UI inspection only.

### 6.3. External Reference Decision Model (`astrarun.routing.jev`)
- Quarantined adapter interfacing with TypeSafe Jev System One API.
- Relegated strictly to an offline benchmark quality auditor.
- Sanitizes all local file paths to `<LOCAL_PATH>` prior to transmission.
- Degrades gracefully to safe offline simulation if `TYPESAFE_API_KEY` is not present.

