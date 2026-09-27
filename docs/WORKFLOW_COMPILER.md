# AstraRun v0.6.5 — Workflow Compiler Specification

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Source Module**: `src/astrarun/workflows/compiler.py`  

---

## 1. Overview & Core Invariants

The `WorkflowCompiler` bridges parsed linguistic structures (`StructuredUtterance`) to execution-ready proposals (`WorkflowProposal`) while strictly enforcing safety boundaries:

1. **Zero Execution Authority**: Compiling produces a plan proposal data structure. It never initiates subprocesses, tools, or shell commands.
2. **Strict Capability Boundary**: Steps may only be mapped to verified tools in `ToolRegistry`. No code generation or arbitrary command execution.
3. **Absolute Negation Safety**: Negated clauses (`negated=True`) are completely omitted from executable steps.
4. **Conservative Multi-Clause Policy**: If any clause within an utterance is blocked by hard policy (e.g., targeting system processes, malicious script injection), **the entire proposal is blocked (`status="BLOCKED"`)**.
5. **Mixed-Risk Propagation**: If any step in a multi-step request is `ToolRisk.HIGH` (e.g. `terminate_process`), the entire workflow's `overall_risk` is elevated to `ToolRisk.HIGH` and requires explicit confirmation.
6. **Partial Support Transparency**: Requests combining supported and unsupported capabilities emit `status="PARTIALLY_SUPPORTED"` with an itemized explanation.

---

## 2. Proposal Lifecycle States

```text
                  StructuredUtterance
                          │
                          ▼
                  WorkflowCompiler
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
      BLOCKED          CLARIFY        UNSUPPORTED
   (Policy Risk)     (Ambiguity)    (No Capability)
                          │
                          ▼
                 PARTIALLY_SUPPORTED
               (Some Steps Executable)
                          │
                          ▼
                        READY
                (All Steps Validated)
```

| Proposal Status | Trigger Condition | Downstream Action |
| :--- | :--- | :--- |
| `READY` | All clauses map to valid registered capabilities | Passed to ActionGate for confirmation / execution |
| `PARTIALLY_SUPPORTED` | Supported steps present alongside unsupported clauses | User prompted with preview of executable subset |
| `CLARIFY` | Entities or coreferences are ambiguous | Disambiguation card displayed in UI |
| `BLOCKED` | Any clause targets protected resources or shell injection | Hard refusal; 0 steps executed |
| `UNSUPPORTED` | No requested action maps to registered tools | User informed capability is not implemented |
| `EMPTY` | All actions were negated (e.g. `"don't open anything"`) | No action required |
