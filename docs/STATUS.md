# AstraRun v0.6.5 Status Report

> **Date**: 2026-09-27  
> **Status**: STABLE / VERIFIED / MILESTONE COMPLETE  
> **Milestone**: v0.6.5 Complete (Hybrid NLP Understanding Engine & Workflow Compiler)  
> **Git Milestone Commit**: `5954a33` (v0.6) -> `feat(astrarun): v0.6.5`  
  

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

7. **Natural Language Understanding Engine (`astrarun.nlp`)**:
   - Multi-layer hybrid NLU architecture combining deterministic extractors, clause decomposition, negation scoping, local temporal engine, and optional non-blocking spaCy linguistic parsing.
   - Decomposes compound requests into typed `StructuredUtterance` IR containing clauses, typed entity spans, directed relations, temporal intervals, coreference references, and constraints.
   - Deterministic evidence precedence: exact patterns override statistical inferences.
   - Scoped negation safety: completely omits negated clauses from execution proposals (**0.00% Negated Action Leakage Rate**).
   - Local workstation timezone temporal calculations (`datetime.now().astimezone()`).
   - Syntactic coreference extraction with `WorkstationContextEngine` machine state binding.

8. **Workflow Compiler (`astrarun.workflows.compiler`)**:
   - Translates `StructuredUtterance` into `WorkflowProposal` without execution authority.
   - Capability-bounded: only maps to verified registered tools.
   - Conservative multi-clause policy: any blocked clause blocks the entire request (`status="BLOCKED"`).
   - Mixed-risk requests elevate overall risk to `ToolRisk.HIGH` and mandate confirmation.
   - Distinguishes `PARTIALLY_SUPPORTED` requests and reports itemized capabilities.
   - Developer debugger CLI (`python -m astrarun.nlp.debugger "<utterance>"`).
   - AI Bridge escalation envelope (`ReasoningRequired`) for complex activity restoration and diagnostic questions.

9. **Benchmark Suites & Test Coverage**:
   - **Automated Tests**: **126 passing tests** (97 baseline + 29 v0.6.5 NLP tests) in ~6.4s.
   - **NLP Benchmark V1**: 620 cases (310 Dev + 310 Locked Test, SHA256: `41f1ad1b6a29d071dad3ea93a8390961c41c136b15365586cd48ad3a61211c82`):
     - Intent Accuracy: **100.0%**
     - Clause Segmentation: **95.2%**
     - Multi-Action Match: **100.0%**
     - Negation Accuracy: **100.0%**
     - Negated Action Leakage: **0.00%** (Prime Safety Invariant)
     - Block Recall: **100.0%**
     - Mean Latency: **0.394 ms** (rules) / **7.157 ms** (spaCy hybrid)
   - **Action Benchmark V1**: 330 cases, **100% Gate Accuracy**, **0.00% FER**, **100% Block Recall**, **100% Confirmation Recall**.
   - **Platform Health**: `wsctl doctor` passed (39/39 OK, 0 errors, 0 warnings).

---

## 2. Key Empirical Findings (v0.6.5)

1. **Deterministic Grammar Substantially Outperforms Neural Models for Workstation Commands**:
   - Pretrained news-corpus models (like spaCy's `en_core_web_sm`) frequently misclassify imperative verbs (*"open"*, *"run"*, *"stop"*) as adjectives and misattach numeric port tokens.
   - The deterministic grammar and domain lexicon pipeline achieves **100% precision on structured syntax, runs in 0.39 ms (18x faster than spaCy's 7.16 ms), and consumes < 1 MB RAM vs. spaCy's 269 MB**.
2. **Negation Scoping Must Be Attributed Per-Clause**:
   - Contrastive commands like *"don't kill node, just inspect it"* require clause-level polarity isolation. Binding `source_clause_idx` to each proposal step guarantees that negated actions are never scheduled.
3. **Conservative Multi-Clause Policy Preempts Sneak-In Attacks**:
   - Evaluating both individual clauses and the holistic utterance against security policies ensures that adversarial requests combining safe and destructive clauses (*"open AstraRun and delete system32"*) are blocked entirely rather than partially executed.

---

## 3. What Does Not Work (By Design in v0.6.5)

- **Arbitrary Shell Execution**: Zero shell access is exposed; commands like `dir`, `echo`, `cat`, or powershell piping are rejected.
- **Unrestricted Autonomous Agent Loops**: AstraRun does not loop autonomously with an LLM to take arbitrary workstation actions.
- **Direct Cloud LLM Invocations**: AstraRun contains zero direct cloud API calls; reasoning integration is confined to the `ReasoningRequired` escalation boundary.
- **Modification of Catalog Files**: `workspace.json` is never mutated or written to by AstraRun.

---

## 4. Next Recommended Step

**Milestone v0.7: AI Bridge Reasoning Integration**:
- Connect `ReasoningProvider` and `ReasoningRequired` escalation envelopes to local AI Bridge sidecar service over IPC / localhost HTTP.
- Implement background context synthesis for complex activity restoration (`"get me back to whatever I was doing before AstraRun"`).
- Diagnostic error and port collision analysis through local LLM reasoning.
- Output from AI Bridge strictly re-enters `EntityResolver` -> `ActionGate` -> `ToolRegistry`.

