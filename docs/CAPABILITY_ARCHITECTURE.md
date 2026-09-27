# Capability Architecture — AstraRun v0.7

> **Scope**: AstraRun Workstation Capability Subsystem  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Executive Summary

AstraRun v0.7 introduces the **Workstation Capability Architecture**, establishing a unified, typed, policy-controlled execution boundary between higher-level intent understanding (NLP/routers) and low-level Windows OS operations.

In prior milestones (v0.1–v0.6), AstraRun relied on a flat `ToolRegistry` with a handful of hardcoded launchers (`open_app`, `open_folder`, `open_url`, `inspect_process`, `kill_process`). 

v0.7 fundamentally evolves this model:
1. **Multi-Category Abstraction**: 47 capabilities organized into 9 discrete OS categories.
2. **Strict Typed Contracts**: Every capability defines typed schemas, risk levels, auto/confirm/block permissions, and structured return envelopes (`CapabilityResult`).
3. **Observation Recording**: Read-only capabilities automatically emit typed OS facts into an in-memory `ObservationStore`, preparing the workstation context for future reasoning layers (v0.12).
4. **Zero Raw Shell Execution**: Natural language text is never passed to `cmd.exe`, PowerShell, or arbitrary subprocesses.
5. **Read-Only First**: Capabilities default to inspection and discovery before any mutation or termination.

```
+-------------------------------------------------------------------------+
|                  User Natural Language / Hotkey Input                   |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|              Hybrid NLP Understanding Engine (v0.6.5)                   |
|       - Clause Decomposition, Negation Scoping, Entity Resolution       |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                 ActionGate & Workflow Compiler (v0.6)                   |
|       - Hard Policy Evaluation, Disambiguation & Confirmation           |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                     CAPABILITY REGISTRY (v0.7)                          |
|  - 47 Typed Handlers across 9 OS Domains                                |
|  - Auto / Confirm / Block Permission Verification                       |
|  - Bounded Execution Latency (< 1 ms mean)                              |
+-------------------------------------------------------------------------+
       |                  |                  |                  |
       v                  v                  v                  v
+--------------+   +--------------+   +--------------+   +--------------+
| Applications |   |    Files     |   |  Processes   |   |   Network    |
+--------------+   +--------------+   +--------------+   +--------------+
       |                  |                  |                  |
       v                  v                  v                  v
+--------------+   +--------------+   +--------------+   +--------------+
|    System    |   |   Projects   |   |   Windows    |   |  Workflows   |
+--------------+   +--------------+   +--------------+   +--------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                     Structured Observation Store                        |
|  - In-Memory Bounded History of OS Facts & State Observations           |
+-------------------------------------------------------------------------+
```

---

## 2. Core Architectural Principles

### 2.1 The Body and Senses Invariant
v0.7 focuses strictly on giving AstraRun a robust, deterministic, safe "body and senses" (the ability to accurately see and safely touch the workstation environment). Deep System-2 reasoning and LLM loops are intentionally deferred to v0.12. An agent cannot safely reason about an environment it cannot reliably inspect or control through typed contracts.

### 2.2 Standard Return Contract: `CapabilityResult`
All 47 capability handlers return a uniform `CapabilityResult` dataclass:
- `capability`: String identifier of the executed capability.
- `success`: Boolean status flag.
- `message`: User-friendly descriptive outcome.
- `data`: Typed dictionary containing structured payload (e.g. process lists, system metrics, file matches).
- `error_code`: Optional `CapabilityErrorCode` (`NOT_FOUND`, `PERMISSION_DENIED`, `INVALID_ARGUMENT`, `AMBIGUOUS`, `OS_ERROR`).
- `latency_ms`: Execution duration in milliseconds.

### 2.3 Strict Category Partitioning
Capabilities are grouped into 9 categories:
1. `APPLICATION`: Discover, inspect, focus, launch, and gracefully close desktop applications.
2. `FILE`: Find, index, reveal, and inspect user files across bounded safe roots.
3. `PROCESS`: Inspect CPU/memory, tree relationships, listening ports, and TOCTOU-safe termination.
4. `NETWORK`: Inspect listening ports, network connections, and process-port bindings.
5. `SYSTEM`: Inspect CPU, memory, disk, GPU, battery, and lock the workstation.
6. `PROJECT`: Inspect repository status, git branches, dirty state, and project-bound processes.
7. `WINDOW`: Read-only discovery and enumeration of top-level application windows (prep for v0.8).
8. `AUDIO`: Inspect master volume and mute status (sound foundation).
9. `WORKFLOW`: Compose and execute multi-step verified operations.

---

## 3. Integration with Existing Workstation Subsystems

- **ActionGate**: Evaluates permission (`AUTO`, `CONFIRM`, `BLOCK`) before capability dispatch. High-risk operations (e.g. `terminate_process`) require explicit confirmation cards.
- **WorkstationContextEngine**: Ingests observations and updates recency buffers (`last_file`, `last_project`, `last_process`, `last_port`).
- **Hybrid NLP**: Maps decomposed clauses to capability targets using the expanded `nlp_lexicon.json` and `WorkflowCompiler`.
- **Reasoning Provider Boundary**: Remains completely unconfigured. If an utterance is structurally ambiguous or unsupported, AstraRun either triggers deterministic clarification or records `ReasoningRequired` without failing or calling external services.
