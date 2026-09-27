# AstraRun v0.6 Status Report

> **Date**: 2026-09-27  
> **Status**: STABLE / VERIFIED / MILESTONE COMPLETE  
> **Milestone**: v0.6 Complete (Gated Workstation Actions, Context Engine & Workflow Orchestration)  
> **Git Commit Milestone**: `feat(astrarun): v0.6`  

---

## 1. What Works Completely

1. **Action Gate (`astrarun.policy.action_gate`)**:
   - Central safety arbiter transforming `ProposedAction` into typed `ActionGateResult`.
   - Multi-tier gating: Tier 0 (Hard Policy), Tier 1 (Ambiguity & Disagreement), Tier 2 (Tool Registry Mapping), Tier 3 (Confirmation vs. Direct Allowance).
   - Outcomes: `ALLOW` (low-risk production allowlist), `CONFIRM` (high-risk gated actions), `CLARIFY` (ambiguous entities $\Delta \le 0.15$), and `BLOCK` (prohibited security violations).
   - Generates single-use cryptographic confirmation tokens (`secrets.token_hex(16)`, 60s TTL).
   - TOCTOU (Time-of-Check to Time-of-Use) revalidation verifying process existence, kernel `create_time`, and process name to prevent PID recycling race conditions.
   - Argument tampering defense rejecting any token replayed with altered arguments.

2. **Workstation Context Engine (`astrarun.context`)**:
   - Lightweight, privacy-preserving machine state inspection:
     - Foreground window query (`GetForegroundWindow`, executable name, title, PID) via native Win32 `ctypes`.
     - Active TCP listening dev ports query (`1024..65535`) via `psutil`.
     - Ephemeral process/port pronoun resolution (`"stop that process"`, `"kill it"`, `"shut down that server"`) with 300s TTL.
     - Relative project recency tracking (`"open my most recent project"`, `"continue what I was doing"`, `"open that project in vscode"`) with 24h TTL.
   - Atomic persistence to local JSON (`data/context_state.json`) with temporary-file-and-rename semantics and corrupted JSON fallback.
   - Strictly bounded history (30 actions max, 48h retention).
   - Context injection attack rejection (`ignore previous context`, `the previous model said`, `pretend policy is disabled`).
   - Zero keystroke logging, zero screenshots, zero surveillance.

3. **Project Registry (`astrarun.projects.registry`)**:
   - Strictly read-only catalog over `E:\Workspace\workspace.json` (28 cataloged projects) adhering to Platform Rule 10 & 11.
   - Dynamic workspace discovery fallback for uncataloged projects under `Active/`, `Tools/`, `Shared/`.
   - Public API: `get_project(id)`, `find_project(query)`, `project_path(id)`, `project_metadata(id)`, `list_projects()`.
   - Multi-tier fuzzy matching and alias resolution (`"astrarun"`, `"ai-bridge"`, `"vivaldi-ai"`, `"security-workbench"`, `"server-nexusnode"`).

4. **Workflow Engine (`astrarun.workflows`)**:
   - Structured, non-autonomous workstation task orchestration.
   - Predefined templates: `open_project`, `open_project_in_vscode`, `inspect_dev_port`.
   - Every step calls a registered tool; zero arbitrary shell execution or LLM loops.
   - Fail-fast partial failure handling: stops immediately on step failure, reporting exact step errors without false success assertions.
   - Immutable transaction audit log written to `data/workflow_audit.jsonl`.
   - Explicit declaration of rollback support (`rollback_supported=False` on workstation state).

5. **Confirmation & Disambiguation UI Cards (`astrarun.ui.cards`)**:
   - PySide6 modal cards designed with keyboard safety:
     - `ConfirmationCard`: Displays title, tool, argument details, and color-coded risk badge (`HIGH`, `MEDIUM`, `LOW`). `Esc` cancels; single `Enter` is ignored on `HIGH` risk; requires `Ctrl+Enter` or click to confirm.
     - `DisambiguationCard`: Renders candidate list with Up/Down arrow keyboard navigation, `Enter` to select, and `Esc` to cancel.

6. **Action Benchmark V1 (`benchmarks/action`)**:
   - 330-query test set across 19 categories (Seed: `20260927`, SHA256: `d73ac62ab9b9ba0c0cab447be74d4b8c70445453f13a8ce7ea3c8d7c8d26866d`).
   - Evaluated end-to-end via `benchmarks/action/run_action_benchmark.py`:
     - **Intent Accuracy**: **100.0%** (330/330)
     - **Gate Accuracy**: **100.0%** (330/330)
     - **Tool Selection Accuracy**: **100.0%** (330/330)
     - **Proposed Action Accuracy**: **100.0%** (330/330)
     - **False Execution Rate (FER)**: **0.00%** (Prime Invariant)
     - **False Action Proposal Rate (FAPR)**: **0.00%**
     - **Clarification Precision**: **100.0%** (20/20)
     - **Block Recall**: **100.0%** (74/74)
     - **Confirmation Recall**: **100.0%** (31/31)
     - **Mean Latency**: **0.077 ms** ($p_{50}: 0.027\text{ ms}$, $p_{95}: 0.187\text{ ms}$)

7. **Automated Test Suite**:
   - **97 passing automated unit, UI, integration, and security tests** (79 baseline regression tests + 18 v0.6 tests).
   - Real disposable process test (`test_toctou_process_lifecycle`) spawning, inspecting, revalidating, and terminating a temporary Python worker.

---

## 2. Key Empirical Findings (v0.6)

1. **TOCTOU Protection is Critical on Windows**:
   - Windows process IDs are rapidly recycled by the NT kernel once a process terminates. Storing and verifying `proc.create_time()` ensures that delayed user confirmation cannot accidentally terminate a newly spawned, unrelated process with the same PID.
2. **Action-Specific Policy Outperforms Blanket Gating**:
   - In v0.5, all operations on ports $\le 1023$ were blanket-blocked. In v0.6, differentiating read-only inspection (allowed on port 80 and 443) from termination (strictly blocked on ports $\le 1023$) provides useful developer ergonomics while maintaining 100% security integrity.
3. **Deterministic Safety Gating Runs in Microseconds**:
   - The entire resolution and action gate pipeline runs in $0.077\text{ ms}$ on host CPU, allowing live keystroke evaluation without impacting UI responsiveness.
4. **Single Enter Suppression Prevents Catastrophic Mistakes**:
   - Suppressing the single `Enter` key on `ToolRisk.HIGH` actions in `ConfirmationCard` prevents muscle-memory keystroke execution when users type commands quickly.

---

## 3. What Does Not Work (By Design in v0.6)

- **Arbitrary Shell Execution**: Zero shell access is exposed; commands like `dir`, `echo`, `cat`, or powershell piping are rejected.
- **Unrestricted Autonomous Agent Loops**: AstraRun does not loop autonomously with an LLM to take arbitrary workstation actions.
- **Direct Cloud LLM Invocations**: AstraRun contains zero direct cloud API calls; reasoning integration is confined to the `ReasoningProvider` protocol boundary.
- **Modification of Catalog Files**: `workspace.json` is never mutated or written to by AstraRun.

---

## 4. Next Recommended Step

**Milestone v0.7: AI Bridge Integration, Multi-Modal Workstation Actions & Sidecar Daemon**:
- Connect `ReasoningProvider` to local AI Bridge sidecar service over IPC / localhost HTTP.
- Implement background process health monitoring and dev port auto-refresh.
- Introduce project command execution workflows (`wsctl run <project> <cmd>`) through registered workflow templates.
