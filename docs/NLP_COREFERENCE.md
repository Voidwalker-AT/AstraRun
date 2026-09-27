# AstraRun v0.6.5 — Coreference & Context Resolution Boundary

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Source Module**: `src/astrarun/nlp/coreference.py`  

---

## 1. Architectural Boundary

In an operating system controller, neural coreference models frequently hallucinate or bind ambiguous pronouns to unintended system entities. AstraRun enforces a strict separation:

$$\text{User Utterance} \longrightarrow \text{NLP (Detect Pronouns)} \longrightarrow \text{ContextEngine (Bind Machine State)} \longrightarrow \text{ActionGate}$$

- **NLP Role**: Detects syntactic anaphoric tokens (`"it"`, `"that"`, `"that process"`, `"same project"`, `"the previous one"`), extracts their character spans, and determines target entity class (`process`, `project`, `window`, `generic`).
- **Context Engine Role**: Binds the token to actual verified workstation state (`WorkstationContext`).
- **Zero Hallucination Guarantee**: NLP never invents what `"it"` means.

---

## 2. Binding Algorithms & Ambiguity Arbitration

### Process Coreference (`target_type="process"`)
- The Context Engine scans recent inspection actions (`inspect_process`, `inspect_port`) and active listening dev ports.
- If **exactly 1** candidate exists: Binds unambiguously (e.g. `PID: 14236`).
- If **multiple candidates** exist:
  - Sets `ambiguous = True`.
  - Populates `candidate_ids = [pid1, pid2, ...]`.
  - ActionGate triggers `DecisionDisposition.CLARIFY`.
  - **Never** binds to the newest candidate without explicit user confirmation.

### Project Coreference (`target_type="project"`)
- Bound via `RecentProjectsManager` in `src/astrarun/context/projects.py`.
- Resolves `"the last project"` or `"that project"` to the most recently active cataloged project.
