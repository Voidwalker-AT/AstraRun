# AstraRun v0.11 Agent Runtime Specification

> **Module**: `astrarun.agent`  
> **Status**: ACTIVE & VERIFIED  
> **Milestone**: v0.11 Dynamic Workstation Agent Runtime  

---

## 1. Executive Summary

AstraRun v0.11 transforms the platform from a command matcher into a **Local Windows Workstation Agent Runtime**. Instead of matching input strings directly to static tool IDs or executing raw command lines, the runtime executes an autonomous closed-loop:

$$\text{UNDERSTAND GOAL} \longrightarrow \text{PLAN} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE} \longrightarrow \text{VERIFY} \longrightarrow \text{REPLAN} \longrightarrow \text{COMPLETED}$$

The core abstraction transitions from `Command` to `UserGoal`. All interactions are bound by strictly typed capability schemas, deterministic security verification, and workstation resource locking.

---

## 2. Architecture Overview

```
                               ┌──────────────────────────┐
                               │   User Natural Prompt    │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌──────────────────────────┐
                               │   GoalPlanner (Parse)    │
                               └────────────┬─────────────┘
                                            │ (Goal & Plan DAG)
                                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      AgentExecutionEngine (Closed Loop)                  │
│                                                                          │
│   ┌──────────────┐     ┌──────────────┐     ┌───────────────────────┐    │
│   │ Resource Lock│ ──> │     ACT      │ ──> │        OBSERVE        │    │
│   │ Acquisition  │     │(Registry Cap)│     │  (MachineObserver)    │    │
│   └──────────────┘     └──────────────┘     └───────────┬───────────┘    │
│                                                         │                │
│                                                         ▼                │
│   ┌──────────────┐     ┌──────────────┐     ┌───────────────────────┐    │
│   │ Lock Release │ <── │  NEXT STEP / │ <── │        VERIFY         │    │
│   │  & Progress  │     │    DONE      │     │(Empirical StepVerifier)│   │
│   └──────────────┘     └──────┬───────┘     └───────────┬───────────┘    │
│                               │                         │ (Failed)       │
│                               │                         ▼                │
│                               │             ┌───────────────────────┐    │
│                               └──────────── │  REPLAN / DEGRADE /   │    │
│                                             │         RETRY         │    │
│                                             └───────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                               ┌──────────────────────────┐
                               │     Live Task HUD V2     │
                               │ (ETA, Graph, Cancel, UI) │
                               └──────────────────────────┘
```

---

## 3. Core Engine Components

1. **`GoalPlanner` (`astrarun.agent.planner`)**:
   - Parses high-level natural language utterances into structured `Goal` objects.
   - Generates directed acyclic execution plans (`Plan`) consisting of typed `PlanStep` nodes.
   - Strictly prohibits arbitrary shell command synthesis.
2. **`ExecutionGraph` (`astrarun.agent.graph`)**:
   - Manages step dependencies, cycle detection via Kahn's algorithm, and dynamic topological step readiness.
   - Propagates output data from completed steps to dependent steps via `StepDependency.data_mapping`.
3. **`ResourceLockManager` (`astrarun.agent.locking`)**:
   - Manages mutual exclusion for workstation resources (`WINDOW:<hwnd>`, `FILE:<path>`, `NETWORK:WIFI`, `PROCESS:<pid>`).
   - Supports re-entrancy and atomic bulk release upon task completion.
4. **`MachineObserver` (`astrarun.agent.observer`)**:
   - Synchronously captures active foreground HWND, window title, power state (AC/battery), and native Wi-Fi connection.
5. **`StepVerifier` (`astrarun.agent.verifier`)**:
   - Evaluates empirical evidence after action execution according to `VerifierStrategy` (`FILE_NON_EMPTY`, `WINDOW_READY`, `NETWORK_SSID`, etc.).
6. **`AgentExecutionEngine` (`astrarun.agent.loop`)**:
   - Coordinates the closed-loop execution, retries, degradation, replanning, and event emission.
