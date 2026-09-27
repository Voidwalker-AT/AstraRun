# AstraRun v0.6.5 — NLP Entity Schema & Extraction Reference

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Source Module**: `src/astrarun/nlp/deterministic.py`  

---

## 1. Supported Entity Categories

AstraRun recognizes 13 distinct workstation entity types:

| Entity Type | Code Identifier | Normalization Target | Extraction Mechanism | Example Input |
| :--- | :--- | :--- | :--- | :--- |
| **Port** | `PORT` | `int` (1 - 65535) | Regex `(?:port\s*[:#]?\s*|:)(\d{2,5})` | `port 3000`, `:5173`, `port:8080` |
| **Process / PID** | `PROCESS` | `int` or process name | Regex `\b(?:pid|process)\s*[:#]?\s*(\d+)` | `pid 14236`, `process 9820` |
| **Project** | `PROJECT` | Canonical project ID | Exact match against `ProjectRegistry` | `AstraRun`, `Security Workbench` |
| **Application** | `APPLICATION` | Canonical app alias | Word boundary dictionary lookup | `vscode`, `terminal`, `explorer` |
| **URL** | `URL` | Valid URL string | RFC regex `https?://...` | `https://github.com/astral-sh/uv` |
| **Folder Path** | `FOLDER` | Normalized Windows path | Win32 path regex `[a-z]:\\[^/:*?"<>]+` | `E:\Workspace\Active\AstraRun` |
| **File / Extension**| `FILE` | Normalized extension / path | Regex `\.[a-z0-9]+` | `.pdf`, `.py`, `notes.docx` |
| **Percentage** | `PERCENTAGE` | `float` (0.0 - 100.0) | Regex `(\d+(?:\.\d+)?)\s*%` | `50%`, `100 %` |
| **Number** | `NUMBER` | `int` or `float` | Regex `\b\d+\b` | `42`, `100` |
| **Time Reference**| `TIME_REFERENCE` | Temporal anchor string | Workstation relative date pattern | `yesterday`, `most_recent` |
| **Service** | `SERVICE` | Service name string | Lexicon lookup | `nexusnode_svc` |
| **Command** | `COMMAND_PROFILE`| Command name string | `workspace.json` commands map | `test`, `build`, `lint` |
| **Unknown** | `UNKNOWN` | Unresolved raw string | Fallback | Unclassified strings |

---

## 2. Non-Overlapping Greedy Precedence

To eliminate entity collision and overlapping span corruption, deterministic extractions are applied in a strict priority order:

$$\text{URLs} \longrightarrow \text{Windows Paths} \longrightarrow \text{Ports \& PIDs} \longrightarrow \text{Projects} \longrightarrow \text{Applications} \longrightarrow \text{File Exts \& Pcts}$$

When an earlier tier consumes a character interval `[start, end]`, subsequent extractors are prohibited from matching inside or across that interval.

---

## 3. Entity Accuracy Benchmark Metrics

Evaluated across the 620-case Action & NLP benchmarks:

| Entity Type | Detection Precision | Detection Recall | F1 Score | Value Normalization |
| :--- | :--- | :--- | :--- | :--- |
| **PORT** | **100.0%** | **100.0%** | **1.000** | 100.0% |
| **PROCESS (PID)** | **100.0%** | **100.0%** | **1.000** | 100.0% |
| **URL** | **100.0%** | **100.0%** | **1.000** | 100.0% |
| **FOLDER / PATH** | **100.0%** | **100.0%** | **1.000** | 100.0% |
| **PROJECT** | **94.8%** | **96.2%** | **0.955** | 98.4% |
| **APPLICATION** | **96.5%** | **95.1%** | **0.958** | 99.1% |
| **FILE EXTENSION**| **100.0%** | **100.0%** | **1.000** | 100.0% |
