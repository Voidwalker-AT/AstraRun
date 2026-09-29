# AstraRun v0.11 Dynamic Goal Planner

> **Module**: `astrarun.agent.planner`  
> **Status**: APPROVED  
> **Target**: AstraRun v0.11+  

---

## 1. Goal Interpretation & Planning Philosophy

The `GoalPlanner` bridges natural-language requests and the structured `ExecutionGraph`.

### Core Invariant: Zero Arbitrary Shell Generation
Large Language Models or autonomous agents that synthesize raw PowerShell, cmd.exe, or Bash strings pose severe workstation safety risks (command injection, accidental deletion, syntax hallucination).

In AstraRun v0.11, the planner is **strictly constrained** to composing plans exclusively from:
1. Typed registered capabilities in `CapabilityRegistry`.
2. Strictly validated arguments matching declared `ParameterSchema`.
3. Predefined interaction tiers and verification strategies.

---

## 2. Planning Pipeline

1. **Utterance Normalization**:
   - Cleans input whitespace, strips trailing punctuation, and evaluates regex patterns and semantic markers.
2. **Intent & Parameter Extraction**:
   - Maps requests into structured domains:
     - Battery health: `run a battery report and save it in Downloads as astra-battery.html` -> `generate_battery_report` with target path.
     - Wi-Fi operations: `scan wifi`, `check wifi status`, `connect to wifi <ssid>`, `disconnect wifi`.
     - App lifecycle & typing: `open <app> and type <text>`.
     - Window control: `snap <app> to <position>`.
3. **Plan DAG Construction**:
   - Instantiates `Plan` with dependency relationships.
   - For compound tasks, assigns explicit dependencies (e.g. `step_type_text` depends on `step_open_app`).
   - Assigns verification strategies (`FILE_NON_EMPTY`, `WINDOW_READY`, `NETWORK_SSID`).
