# AstraRun — Windows Intelligent Command Launcher (v0.3)

AstraRun is a local, lightweight, low-latency Windows command launcher engineered as the foundational command interface for an evolving AI-assisted workstation control ecosystem.

AstraRun replaces fragile string-interpolated shell execution with a strictly typed pipeline:
`Natural Language -> Request Normalizer -> Fuzzy / Deterministic Router -> Typed Decision -> Tool Registry -> Windows OS`.

---

## Key Capabilities (v0.3)

- **Instantaneous Hotkey Activation**: Summoned with `Alt+Space` in ~4.5ms from a pre-warmed resident background process.
- **Multi-Signal Fuzzy Matching Engine**: Combines exact, alias, prefix, word-token, acronym, single-drop typo (`notpad` -> `Notepad`), and Damerau-Levenshtein edit-distance scoring with bounded usage boost (`<= 0.03`).
- **Ranked Suggestions UI**: Dynamic dropdown drawer with visual category badges (`APP`, `FOLDER`, `WEB`, `COMMAND`), active selection highlighting, and ergonomic auto-expansion.
- **Full Keyboard Navigation**: Complete keyboard-only control via `Up`/`Down` arrow navigation, `Tab` autocompletion, `Enter` execution, and `Escape` dismissal.
- **Zero Raw Shell Ingestion & 0.0% False Execution Rate**: Strict confidence gating (`0.75`) guarantees ambiguous or out-of-scope queries (`kill port 3000`, `delete system32`, `asdfgh`) are safely rejected as `unknown` rather than mistriggering apps.
- **Laya Neural Decision Router in Shadow Mode (v0.3)**: Integrated ModernBERT-large (421M parameters) non-autoregressive decision model running on CPU with **ZERO production execution authority**.
- **10-Class Intent Taxonomy**: Formally defined semantic intent classes separating classification from parameter binding and OS tool invocation.
- **Dual-Track Privacy-Preserving Shadow Telemetry**: Concurrently records production vs. Laya decisions in `data/laya_shadow_events.jsonl` with automated regex credential redaction (zero off-workstation egress).
- **Foreground-Window-Aware Monitor Placement**: Anchors the launcher to the active foreground application's display with mouse cursor and primary monitor fallbacks using native Win32 APIs.
- **Expanded Application Discovery**: Discovers **~400 applications** cached at startup from Windows User & System Start Menu shortcuts (`.lnk`), `App Paths` registry, and `PATH`.
- **Standardized Semantic Benchmark**: 325 curated queries evaluated across 15 categories, measuring calibration error (ECE 0.0443), Brier score (0.7450), and three-way system performance.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Activation ["Activation & Display"]
        HK["Global Hotkey (Win32 Alt+Space)"] -->|WM_HOTKEY| HKT["Hotkey Listener Thread"]
        HKT -->|Qt Signal| UI["PySide6 Launcher Window"]
        Pos["Win32 Positioning Engine"] -.->|Target Work Area| UI
        User["User Typing"] -->|Input String| UI
    end

    subgraph Search ["Search & Ranking Engine"]
        UI -->|Live Query| Index["SearchIndex (In-Memory)"]
        Index -->|Precomputed Terms| Matcher["FuzzyMatcher"]
        Matcher -->|Multi-Signal Scoring| Scorer["FuzzyScorer"]
        Usage["UsageStore (data/usage.json)"] -.->|Bounded Boost <=0.03| Scorer
        Scorer -->|Ranked Results + Badges| UI
    end

    subgraph Pipeline ["Decision & Execution Pipeline"]
        UI -->|Committed Request| Router["DeterministicRouter"]
        Router -->|Score >= 0.75| Dec["Decision Object"]
        Router -->|Score < 0.75| Unknown["Unknown Decision"]
        Dec -->|Log Event| Telemetry["Telemetry Collector (Redacted)"]
        Dec -->|Validation & Policy| Reg["Tool Registry"]
        Reg -->|Dispatched Handler| Tool["Registered Tool (open_app / open_folder / open_url / refresh_apps)"]
        Reg -->|Record Success| Usage
    end

    subgraph OS ["Operating System Layer"]
        Tool -->|os.startfile / subprocess argv| WinOS["Windows OS"]
    end
```

---

## Keyboard Controls

| Shortcut / Key | Context | Action |
| :--- | :--- | :--- |
| **`Alt + Space`** | Global (Anywhere) | Toggle / summon AstraRun command bar |
| **`Up / Down Arrow`** | Command Bar Active | Navigate through ranked suggestions |
| **`Tab`** | Command Bar Active | Autocomplete input with selected suggestion title |
| **`Enter`** | Suggestion Selected | Immediately execute selected suggestion |
| **`Enter`** | Raw Input (No selection) | Route query through deterministic & fuzzy engine (score >= 0.75) |
| **`Escape`** | Command Bar Active | Dismiss AstraRun without executing |
| **`Click Outside`** | Command Bar Active | Auto-dismisses window (configurable) |

---

## Supported Commands

### Applications & Discovered Software (~400 apps)
```text
open notepad          # or 'launch notepad', 'notepad', 'editor'
notpad                # Typo-tolerant: automatically resolves to Notepad
open calculator       # or 'calc'
open vscode           # or 'code', 'vs code'
open vivaldi          # or 'browser'
open terminal         # or 'wt', 'windows terminal'
open powershell       # or 'pwsh'
open cmd              # or 'prompt'
open explorer         # or 'files'
refresh apps          # Internal command: re-scans application caches
```

### Folders & Workspaces
```text
open downloads        # opens User Downloads
open documents        # opens User Documents
open desktop          # opens User Desktop
open pictures         # opens User Pictures
open videos           # opens User Videos
open workspace        # opens E:\Workspace
open active projects  # opens E:\Workspace\Active
```

### Web & URLs
```text
open github           # opens https://github.com
open youtube          # opens https://youtube.com
open google           # opens https://google.com
open reddit           # opens https://reddit.com
open https://news.ycombinator.com
```

---

## Performance & Benchmark Metrics

Empirical measurements gathered on Windows 11 host (Python 3.13):

### 1. Interactive Runtime Latencies
| Metric | Measured Value | Target Standard |
| :--- | :--- | :--- |
| **Hotkey-to-Visible Latency** | **4.51 ms** | < 50 ms |
| **Fuzzy Search Latency (Mean)** | **3.03 ms** (~411 candidates) | < 15 ms |
| **Fuzzy Search Latency (p50)** | **21.7 µs** | < 1 ms |
| **Direct Route Latency** | **4.61 µs** | < 1 ms |
| **Startup to Pre-warmed Ready** | **1.27 s** | < 3 s |
| **Resident Idle Memory** | **~4 MB - 50 MB** | < 100 MB |
| **Idle CPU Utilization** | **0.0%** (Kernel Wait) | 0.0% |

### 2. Routing Intelligence Benchmark (88 Queries)
| Benchmark Metric | Result | Target Standard |
| :--- | :--- | :--- |
| **Overall Accuracy** | **100.0%** (88 / 88) | >= 95.0% |
| **Exact Resolution Accuracy** | **100.0%** (20 / 20) | 100.0% |
| **Fuzzy Resolution Accuracy** | **100.0%** (20 / 20) | >= 95.0% |
| **Unresolved Rejection Accuracy** | **100.0%** (18 / 18) | >= 95.0% |
| **FALSE EXECUTION RATE** | **0.0%** (0 / 18 false triggers) | <= 1.0% |

---

## Installation & Setup

AstraRun uses a project-local virtual environment (`.venv`).

### 1. Requirements
- Windows 10 or 11 (64-bit)
- Python 3.11+ (Python 3.13 recommended)
- `uv` (recommended) or standard `pip`

### 2. Virtual Environment Setup
```powershell
# Navigate to AstraRun directory
cd E:\Workspace\Active\AstraRun

# Create isolated virtual environment
uv venv .venv --python 3.13

# Install dependencies in editable mode
uv pip install -e . --python .venv\Scripts\python.exe
uv pip install pytest --python .venv\Scripts\python.exe
```

---

## Running AstraRun

### Start the Resident Background Daemon
```powershell
.venv\Scripts\python src\astrarun\main.py
```
AstraRun will pre-warm its interface, register `Alt+Space`, and remain resident in the background. Press `Alt+Space` to summon it.

### Launch and Show Immediately (Debug / Direct)
```powershell
.venv\Scripts\python src\astrarun\main.py --show-now
```

### Execute a Command Headless (CLI / Testing)
```powershell
.venv\Scripts\python src\astrarun\main.py --run-command "open notepad"
.venv\Scripts\python src\astrarun\main.py --run-command "open downloads"
```

---

## Configuration

Configuration files are stored under `config/`:
- **`config/settings.json`**: Global hotkey, UI dimensions, theme, max suggestions, telemetry, and logging.
- **`config/apps.json`**: Custom application definitions and paths.
- **`config/aliases.json`**: Natural language aliases (`calculator` -> `calc`, `vscode` -> `code`).
- **`config/urls.json`**: Web aliases (`github` -> `https://github.com`).

---

## Testing & Benchmarks

Run the complete automated test suite (52 tests):
```powershell
.venv\Scripts\pytest -v
```

Run the deterministic regression benchmark (88 queries):
```powershell
.venv\Scripts\python benchmarks\routing\run_benchmark.py
```

Run the Laya semantic routing benchmark (325 queries):
```powershell
.venv\Scripts\python benchmarks\routing\run_semantic_benchmark.py
```

---

## Project Structure

```text
AstraRun/
|-- AGENTS.md                  # Project operating contract
|-- README.md                  # System documentation
|-- requirements.txt           # Pinned dependencies
|-- pyproject.toml             # Package metadata & build definition
|-- .gitignore                 # Environment & build ignores
|-- benchmarks/                # Evaluation suites & harnesses
|   `-- routing/
|       |-- routing_dataset.json  # 88 curated deterministic evaluation queries
|       |-- run_benchmark.py      # Deterministic evaluation runner
|       |-- semantic_dataset.json # 325 curated semantic evaluation queries (15 categories)
|       `-- run_semantic_benchmark.py # Semantic benchmark runner (System A vs B vs C)
|-- config/                    # Human-editable configuration files
|   |-- settings.json          # Hotkey, UI, telemetry, and Laya shadow config
|   |-- apps.json              # Custom application definitions
|   |-- aliases.json           # Natural language aliases
|   `-- urls.json              # Web aliases
|-- data/                      # Local-only runtime storage (git-ignored)
|   |-- routing_events.jsonl   # Redacted telemetry event stream
|   |-- laya_shadow_events.jsonl # Paired production vs. Laya shadow evaluation stream
|   `-- usage.json             # Usage frequency & recency store
|-- docs/                      # Engineering documentation
|   |-- ARCHITECTURE.md        # Architecture specification & diagrams (v0.3)
|   |-- DECISIONS.md           # Architecture Decision Records (ADRs 001-014)
|   |-- SECURITY.md            # Security boundaries, privacy & risk model
|   |-- ROADMAP.md             # Evolutionary roadmap (v0.1 -> Workstation Daemon)
|   |-- LAYA_RESEARCH.md       # Upstream Laya architecture & capabilities
|   |-- LAYA_RUNTIME.md        # Hardware, PyTorch packaging & runtime specs
|   |-- INTENT_TAXONOMY.md     # 10-class mutual exclusive intent taxonomy
|   |-- LAYA_BENCHMARK.md      # Semantic benchmark 3-way evaluation report
|   |-- LAYA_CALIBRATION.md    # ECE, Brier score, and automation trade-off curve
|   |-- LAYA_KEV_INTEGRATION.md # Multi-tier cascaded architecture spec
|   |-- TESTING.md             # Automated test report & verification matrix
|   `-- STATUS.md              # Current milestone status report (v0.3)
|-- logs/                      # Rotating application logs
|   `-- astrarun.log
|-- scripts/                   # Developer utilities & test scripts
|   |-- test_laya_model.py     # Standalone Laya weight load & inference test
|   `-- benchmark.py
|-- src/
|   `-- astrarun/
|       |-- __init__.py
|       |-- main.py            # Main entrypoint & daemon orchestration
|       |-- core/              # Models, enums, structured logging
|       |-- search/            # Fuzzy search engine, scorer, matcher, index
|       |-- routing/           # Base router, deterministic router & LayaRouter
|       |   |-- __init__.py
|       |   |-- base.py
|       |   |-- deterministic.py
|       |   `-- laya.py        # Laya ModernBERT-large shadow router
|       |-- tools/             # Tool registry & safe execution handlers
|       |-- discovery/         # App Paths, Start Menu shortcuts, Known Folders
|       |-- hotkeys/           # Win32 RegisterHotKey background listener
|       |-- telemetry/         # Local privacy-preserving event logger & redactor
|       |   |-- collector.py
|       |   |-- redactor.py
|       |   `-- shadow_collector.py # Thread-safe Laya shadow event collector
|       |-- usage/             # Atomic usage store for frequency ranking
|       |-- config/            # Resilient JSON configuration loader
|       `-- ui/                # PySide6 launcher window & positioning engine
`-- tests/                     # 52 automated unit, UI, and integration tests
    |-- test_laya_router.py    # Laya safety, resilience & shadow isolation tests
    `-- ...
```

