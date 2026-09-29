# AstraRun Neural NLP Architecture & Pipeline Flow

> **Milestone**: AstraRun v0.10.3  
> **Status**: APPROVED  
> **Date**: 2026-09-28  

---

## 1. System Components & Layers

The AstraRun v0.10.3 architecture partitions language understanding from OS execution authority:

```
+-------------------------------------------------------------------------+
|                              USER QUERY                                 |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                  TIER 0: DETERMINISTIC FAST-PATH                        |
|  - Exact app launches ("notepad", "calc")                                |
|  - System queries ("cpu status", "mute volume")                         |
|  - Fast regex (< 15 ms, p95 < 50 ms)                                    |
+-------------------------------------------------------------------------+
                                    |
            +-----------------------+-----------------------+
            | (Fast-Path Hit)                               | (Complex / Unknown)
            v                                               v
+-----------------------+               +---------------------------------+
| DIRECT CAPABILITY     |               |      NEURAL NLP SANDWICH        |
| EXECUTION             |               |                                 |
+-----------------------+               |  +---------------------------+  |
                                        |  | Laya A: Semantic Pre-Gate |  |
                                        |  +---------------------------+  |
                                        |                |                |
                                        |                v                |
                                        |  +---------------------------+  |
                                        |  | Neural Structure Engine   |  |
                                        |  | (spaCy span & deps)       |  |
                                        |  +---------------------------+  |
                                        |                |                |
                                        |                v                |
                                        |  +---------------------------+  |
                                        |  | Laya B: Semantic Verifier |  |
                                        |  +---------------------------+  |
                                        |                |                |
                                        |                v                |
                                        |  +---------------------------+  |
                                        |  | Decision Fusion Engine    |  |
                                        |  +---------------------------+  |
                                        +---------------------------------+
                                                        |
                                                        v
+-------------------------------------------------------------------------+
|               WORKFLOW COMPILER (Deterministic Plan Synthesizer)         |
|  - Entity Resolution (Resolves "notepad" -> "C:\Windows\notepad.exe")    |
|  - Dependency Binding (Injects wait_for_window & resolve_editable)      |
|  - Payload Binding (Preserves verbatim literal string offsets)           |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               ACTION GATE (Security & Safety Boundary)                  |
|  - High-risk action verification & user confirmation tokens             |
|  - System process protection (blocks termination of csrss, smss)        |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|           TASK MANAGER & NATIVE OS EXECUTION RUNTIME                     |
|  - Win32 SendInput (Unicode synthetic typing)                           |
|  - UI Automation (Editable control resolution)                          |
|  - Process lifecycle management & floating task HUD status               |
+-------------------------------------------------------------------------+
```

---

## 2. Asynchronous Lazy Initialization Invariant

To ensure that starting AstraRun is instantaneous (< 2 seconds to `READY` status in `data/astrarun_state.json`), heavy neural dependencies:
1. Are **NOT** loaded synchronously during startup.
2. Are initialized asynchronously in a daemon background worker thread after the Alt+Space hotkey and tray icon are registered and active.
3. Fast-path commands and search index lookups remain functional immediately upon process spawn.

---

## 3. Resilience & Fallback Hierarchy

If a neural component encounters a tensor error, timeout, or OOM:
1. **Laya Timeout / Failure**: Gracefully falls back to deterministic clause decomposition + IR entity resolver.
2. **spaCy Parser Failure**: Falls back to regex-based `ClauseDecomposer`.
3. **Laya B Verifier Failure**: Relies on deterministic ActionGate schema validation.
4. **ActionGate Failure**: Fails closed (`ActionGateOutcome.BLOCKED`).
