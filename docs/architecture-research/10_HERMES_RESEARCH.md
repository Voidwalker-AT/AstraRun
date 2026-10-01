# 10 — Hermes Agent & "Skills as Compute Optimization" Research

> **Status**: APPROVED RESEARCH ARTIFACT  
> **Phase**: 4 — Deep-Dive Competitor & Upstream Framework Studies  
> **Focus**: Nous Hermes Agent Architecture, Tool Calling Conventions, Skills as Compute Optimization, and Self-Improving Workstation Agent Workflows  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Executive Summary & Core Philosophy

| Principle | Traditional Autonomous Agent | Hermes / Skill-Centric Philosophy | AstraRun Adaptation |
| :--- | :--- | :--- | :--- |
| **Execution Model** | Every request invokes multi-step, multi-turn LLM reasoning from scratch `[UPSTREAM_PRIMARY_SOURCE]` | First encounter reasons; subsequent encounters execute compiled skill `[UPSTREAM_PRIMARY_SOURCE]` | **Skills as Compute Optimization**: Compile verified workflows into deterministic capabilities `[TARGET]` |
| **Compute Cost** | High latency (3–10s per step), repetitive token waste `[MEASURED]` | $O(1)$ fast-path execution with zero or minimal model invocation `[UPSTREAM_PRIMARY_SOURCE]` | Critical for RTX 2050 4GB / 3.3 GB RAM environment `[TARGET]` |
| **Format** | Opaque vector memory or ad-hoc prompts `[INFERENCE]` | Standardized `SKILL.md` with YAML frontmatter + scripts `[UPSTREAM_PRIMARY_SOURCE]` | Human-readable, git-trackable skill bundles in `E:\Workspace\Active\AstraRun\.skills/` `[TARGET]` |
| **Lifecycle Safety** | Autonomous prompt mutation without guardrails `[INFERENCE]` | Self-improving generation + verification loops `[UPSTREAM_PRIMARY_SOURCE]` | **5-Stage Gate**: Synthesize $\to$ Sandbox $\to$ ActionGate $\to$ User Approval $\to$ Deterministic Activation `[USER_REQUIREMENT]` |

---

## 2. Upstream Architecture: Hermes Tool-Calling & Execution Paradigm

### 2.1 The Hermes Standard (Nous Research)
`[UPSTREAM_PRIMARY_SOURCE]` Hermes 2 and Hermes 3 established the standard for open-source model function calling:
- XML-encapsulated invocation:
  ```xml
  <tool_call>
  {"name": "execute_command", "arguments": {"cmd": "git status"}}
  </tool_call>
  ```
- Tool response encapsulation:
  ```xml
  <tool_response>
  {"returncode": 0, "stdout": "On branch master\nnothing to commit"}
  </tool_response>
  ```
- **Strengths**: High parser resilience, clear boundary separation from natural text, and zero confusion between markdown backticks and execution payloads.

### 2.2 "Skills as Compute Optimization"
The central insight of the Hermes Agent initiative is that **an agent should not perpetually re-solve solved problems**:

```mermaid
flowchart TD
    subgraph First Encounter (Compute Heavy)
        U1[User Goal:\n'Export monthly git stats to CSV'] --> Plan[Dynamic Planner\nMulti-turn Reasoning]
        Plan --> Act1[Discover repos\nRun git log]
        Act1 --> Act2[Parse dates\nFilter commits]
        Act2 --> Act3[Format CSV\nVerify output]
        Act3 --> Success[Goal Verified\nCost: 15s, 4,500 tokens]
    end

    subgraph Compilation & Verification
        Success --> Synth[Skill Synthesizer\nExtract generalized script + schema]
        Synth --> Sandbox[Sandbox Dry-Run\nVerify on dummy repo]
        Sandbox --> ActionGate[ActionGate Audit &\nUser Approval]
        ActionGate --> Store[Persist to .skills/git-stats-export]
    end

    subgraph Subsequent Encounters (Compute Optimized)
        U2[User Goal:\n'Export git stats for last week'] --> Match[Fast-Path Skill Matcher\nDeterministic Schema Check]
        Match --> Exec[Direct Execution via DynamicRuntime\nCost: 80ms, 0 tokens]
        Exec --> Done[Output Ready]
    end
```

---

## 3. The AstraRun Skill Lifecycle Specification

To satisfy `[USER_REQUIREMENT]` (transparency, user control, reversible operations), AstraRun cannot autonomously rewrite its own production codebase. Instead, it must follow a rigorous 5-stage promotion pipeline:

```
Stage 1: SYNTHESIZE  ──►  Stage 2: SANDBOX  ──►  Stage 3: AUDIT  ──►  Stage 4: APPROVE  ──►  Stage 5: ACTIVATE
(Analyze trace)          (Test in isolation)    (ActionGate)          (User prompt)        (Deterministic)
```

### Stage 1: Synthesis
- When a complex task completes with $> 2$ tool steps and passes all verification gates:
- The synthesizer analyzes the trajectory, extracts invariant logic, parameterizes inputs (e.g., date ranges, directory paths), and drafts:
  1. A metadata file: `SKILL.md` (name, description, input schema, output schema, safety classification).
  2. An execution script: `run.py` or `run.ps1`.

### Stage 2: Sandbox Validation
- The synthesized skill is executed inside an **Ephemeral Sandbox** (`Sandbox A`) against a mock or temporary environment.
- Verifications:
  - Exits with return code 0.
  - Matches output schema.
  - Does not exceed execution time limit (default 10s).
  - Does not attempt network access unless declared in metadata.

### Stage 3: ActionGate Security Audit
- Automated static analysis checks:
  - No secret leaks.
  - No destructive filesystem actions outside permitted project paths.
  - No unauthorized system utility invocations.
  - Risk tier assigned: `READ_ONLY`, `REVERSIBLE_MUTATION`, or `ELEVATED`.

### Stage 4: User Approval Prompt
- The user is notified via HUD or terminal:
  ```
  ✦ Astra discovered a reusable skill: [git-monthly-stats]
    Replaces 4 LLM planning steps with 1 deterministic script.
    Inspect: E:\Workspace\Active\AstraRun\.skills\staging\git-monthly-stats\
    [Approve / Reject / Inspect]
  ```
- No skill is promoted without explicit user sanction.

### Stage 5: Deterministic Activation
- Approved skills are indexed into the local `SkillRegistry`.
- When a future user goal matches the skill's trigger intent, Astra bypasses the dynamic LLM planning DAG entirely, binding arguments directly to the compiled script.

---

## 4. Canonical `SKILL.md` Specification for AstraRun

```yaml
---
name: git-commit-summary
version: 1.0.0
description: Summarizes Git commit history across local repositories within a specified timeframe.
author: astra-synthesizer
created_at: 2026-09-30T00:50:00Z
risk_tier: READ_ONLY
inputs:
  repo_path:
    type: string
    description: Absolute path to local git repository
    required: true
  since_days:
    type: integer
    description: Number of days to look back
    default: 7
outputs:
  summary_text:
    type: string
  commit_count:
    type: integer
entrypoint: run.py
runtime: python_project
timeout_seconds: 15
---

# Git Commit Summary Skill

## Instructions
1. Validates that `repo_path` contains a valid `.git` folder.
2. Runs `git log --since="X days ago" --oneline`.
3. Parses authors, commit messages, and formats a markdown summary.
```

---

## 5. Algorithmic Self-Improvement: GEPA (Generative Evolution of Prompt Architecture)

`[UPSTREAM_PRIMARY_SOURCE]` GEPA applies evolutionary algorithms to agent instructions:
1. **Mutation**: Generate slight variations in tool descriptions or system instructions.
2. **Evaluation**: Benchmark against the North-Star task suite (`05_NORTH_STAR_TASKS.md`).
3. **Selection**: Adopt instructions that reduce token usage, lower step counts, or eliminate failure modes.

### AstraRun Adaptation & Constraints
- **Constraint**: AstraRun must **never** run autonomous prompt mutations during live user sessions.
- **Allowed Scope**: GEPA-style prompt optimization is strictly an offline development or test harness process, evaluated against the 25 North-Star tasks before any release tag.

---

## 6. Synthesis & Next Step Directives

1. **Adopt XML Tool Calling Format**: Standardize on Hermes-compatible XML tags (`<tool_call>`, `<tool_response>`) for local model parsing. This eliminates JSON backtick escaping errors common in small open-source models.
2. **Implement Skill Registry Architecture**: Design `SkillRegistry` as a first-class citizen alongside `CapabilityRegistry`.
3. **Compile Repeat Workflows**: The path to sub-second workstation reactivity on an RTX 2050 is not a bigger LLM—it is aggressive compilation of successful workflows into verified skills.
