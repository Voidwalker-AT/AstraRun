# Agent Self-Evolution & GEPA Research Specification

> **Document**: `docs/SELF_EVOLUTION_RESEARCH.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Scope**: Genetic Evolution of Prompt Architectures (GEPA), DSPy, and Controlled Evolution  
> **Status**: APPROVED RESEARCH SPECIFICATION  

---

## 1. Upstream Evolutionary Mechanics

Research into NousResearch `hermes-agent-self-evolution` revealed powerful methods for optimizing agent reasoning:
1. **Genetic Prompt Evolution (GEPA)**:
   - Uses evolutionary algorithms (mutation, crossover, selection) over candidate prompt architectures.
   - Evaluates prompts against objective task benchmarks.
   - Selects Pareto-optimal candidates balancing task accuracy and token cost.
2. **DSPy Integration**:
   - Declarative optimization of multi-stage LM programs.
   - Automatically teleprompts few-shot exemplars and compiles optimal chain-of-thought signatures.
3. **Trajectory Compression**:
   - Compresses long multi-turn execution sessions into compact, canonical workflow traces.

---

## 2. AstraRun Adaptation vs. Rejection

| Upstream Feature | Autonomous Risk | AstraRun v0.8.5 Adaptation |
| :--- | :--- | :--- |
| **Self-Modifying Python Code** | Agent writes arbitrary `.py` files to disk and runs them | **REJECTED**. Skills are composed strictly of registered `WorkstationCapability` identifiers. |
| **Online Prompt Mutation** | Agent modifies system prompt on live interactions | **REJECTED**. Core policies and system prompts are immutable compiled code. |
| **GEPA Prompt Search** | Uncontrolled search over prompt strings | **ADAPTED FOR OFFLINE**. Only used in offline benchmarking environments to evaluate prompt robustness. |
| **Trajectory Distillation** | Extracts successful sequences from execution logs | **ADOPTED**. `PatternMiner` extracts recurring capability n-grams with parameter bindings. |
| **Human Gating via Diff** | Emits git PRs for human approval | **ADOPTED**. `SkillReviewWidget` presents a visual review dialog before any skill is activated. |

---

## 3. Conclusions for Workstation Agent Design

Self-evolution in a desktop operating system cannot rely on unconstrained generative code execution. By anchoring evolution in **strongly-typed capability vocabularies, empirical support thresholds, and mandatory human review**, AstraRun captures the benefits of adaptive workflow learning while guaranteeing deterministic safety.
