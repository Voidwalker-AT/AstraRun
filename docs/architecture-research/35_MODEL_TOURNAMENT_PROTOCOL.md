# 35 — Model Tournament & Expanded Adversarial Torture Protocol

> **Scope**: Phase 17 Lab A, Lab B, and Lab J Specification  
> **Status**: APPROVED BENCHMARK, TORTURE & SKILL PROTOCOL (Updated Post-Mining Pass)  
> **Core Principle**: Test roles independently; separate model-agnostic agent harnesses from model weights; measure cross-model skill portability; DO NOT pick one universal winner.  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Candidate Models & Role Allocation Matrix

### Critical Architectural Principle: Decoupling Harness from Model
Upstream mining of `NousResearch/Hermes-Agent` demonstrated that its core innovations—progressive skill disclosure, `SKILL.md` format, `skill_manager_tool`, AST security linting, and trajectory compression—constitute a **model-agnostic agent software layer**. The Hermes Agent harness connects to local endpoints (`llama.cpp`, `Ollama`, `vLLM`) via its `plugins/model-providers/custom/` profile.

However, architectural compatibility must not be conflated with empirical model reliability:
- **`PROTOCOL_COMPATIBLE`**: The endpoint can technically connect via OpenAI-compatible `/v1/chat/completions` wire format.
- **`TOOL_FORMAT_COMPATIBLE`**: The model and runtime expose and accept the expected function calling schemas (`tools` parameter and/or XML `<tool_call>` blocks).
- **`EMPIRICALLY_RELIABLE`**: The model consistently emits valid, syntactically correct, and semantically sound Hermes-compatible calls under adversarial torture tests.

Spark-X2.5-1.7B and Qwen2.5-Coder-1.5B are currently **`PROTOCOL_COMPATIBLE`** candidates. Actual tool-call validity, schema adherence, `skill_view` invocation, argument correctness, multi-turn tool behavior, and malformed tool recovery **must be empirically measured in Stage 2**.

Therefore, **Hermes-3-Llama-3.2-3B is NOT required as a mandatory download**. The 3.2B parameter model would consume ~2.0 GB of storage and severely constrain VRAM on our 4 GB RTX 2050 (leaving $<1.4\,\text{GB}$ for KV cache), while testing faculties already evaluated by `Qwen2.5-Coder-1.5B` and `Spark-X2.5-1.7B`. By evaluating the Hermes Agent harness across Spark and Qwen, we eliminate 2.0 GB of download volume without sacrificing any architectural insight.

### Streamlined Candidate Models (Stage 2 Download Portfolio: ~3.72 GB Total)

| Candidate Model | Parameter Count | Quantization | Expected Size | Tested Cognitive Roles | Primary Investigation Question |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **Qwen2.5-Coder-1.5B-Instruct** | 1.54B | `Q4_K_M` | ~1.12 GB | Code Generation, DAG Planning, Argument Binding, Tool Calling | Can 1.5B maintain syntax integrity and DAG correctness without external cloud models? |
| **Qwen2.5-Coder-1.5B-Instruct** | 1.54B | `Q5_K_M` | ~1.27 GB | High-Precision Reasoning, Micro-Execution | Does the higher quantization tier prevent syntax slips on nested schemas? |
| **Spark-X2.5-1.7B** | 1.70B | `Q4_K_M` | ~1.20 GB | Fast Intent Routing, Parameter Binding, Deep Context Needle | Does Spark's hybrid attention maintain low latency and context stability under load? |
| **bge-small-en-v1.5** | 33M | ONNX Int8 | ~0.13 GB | Dense Semantic Retrieval Embedder | Provides the dense retrieval arm for hybrid skill and tool matching (Lab F). |

---

## 2. Model-Agnostic Hermes Harness Testing Protocol

To ensure rigorous, fair comparison, all candidate models are evaluated under the **identical agent harness environment** across four distinct operational modes:

```
                            TEST A: RAW MODEL
                    [Goal] ────► [Model] ────► [Raw Plan]

                     TEST B: HERMES-STYLE SKILL HEADERS
       [Goal + 20 Headers] ────► [Model] ────► [Skill Selection: ID]

                      TEST C: FULL VALIDATED SKILL
     [Goal + Full SKILL.md] ────► [Model] ────► [Parameter Binding & DAG]

                        TEST D: SKILL FAILURE & REPLAN
    [Skill Failed in Env] ────► [Model] ────► [Observation Diagnostic & Replan]
```

### Sub-Test A: Raw Model (Zero In-Context Demonstration)
- **Input**: User goal + raw capability catalog.
- **Model Task**: Decompose the goal from scratch into an executable Plan DAG with dependencies.
- **Measures**: Raw topological planning accuracy, hallucinated tool count, syntax validity.

### Sub-Test B: Hermes-Style Progressive Skill Headers
- **Input**: User goal + 20 candidate skill headers (name + 1-sentence description, ~20 tokens each).
- **Model Task**: Identify whether an existing skill satisfies the goal and output the exact skill identifier, or output `NONE` if no skill applies.
- **Measures**: Skill-selection Recall@1, Recall@3, False Skill Activation Rate (activating a skill when goal requires a custom plan).

### Sub-Test C: Full Validated Skill Execution
- **Input**: User goal + full target `SKILL.md` (instructions, input arguments, script interface).
- **Model Task**: Extract goal parameters into `args.json`, bind file paths/options, and generate the concrete invocation plan.
- **Measures**: Parameter-binding accuracy, schema adherence, token consumption, execution latency.

### Sub-Test D: Injected Skill Failure & Dynamic Adaptation
- **Input**: An executing skill encounters an environmental failure (e.g. target file locked, network interface down, CLI utility returns exit code 1) yielding a structured `StepObservation`.
- **Model Task**: Ingest the error observation, diagnose the root cause, and emit an adapted recovery DAG rather than blindly repeating the failed step.
- **Measures**: Failure detection rate, replanning success rate, infinite-loop avoidance.

---

## 3. Cross-Model Skill Portability Matrix

A central hypothesis of AstraRun Architecture B+ is:
> **Hypothesis**: A strong model (or external teacher) can discover and author a procedure once; AstraRun can validate, lint, and compile it; and a much smaller local model (1.5B–1.7B) can execute, bind, and run it cheaply thereafter.

The tournament explicitly benchmarks cross-model portability:

| Skill Author (Generator) | Skill Executor (Runtime) | Tested Faculty | Success Metric |
| :--- | :--- | :--- | :--- |
| **Strong External Teacher** | **Qwen2.5-Coder-1.5B** | Execution of high-quality standard skills | Parameter binding & execution success |
| **Strong External Teacher** | **Spark-X2.5-1.7B** | Ultra-fast execution of standard skills | Latency, VRAM, parameter accuracy |
| **Qwen2.5-Coder-1.5B** | **Spark-X2.5-1.7B** | Local authoring ➔ Local reflex execution | End-to-end local generation & execution |
| **Spark-X2.5-1.7B** | **Qwen2.5-Coder-1.5B** | Reflex draft ➔ Precision execution | Syntactic compliance of generated code |

---

## 4. Architectural Taxonomy: Where Astra Intelligence Lives

AstraRun avoids the trap of attempting to fine-tune every workstation workflow directly into model weights. Intelligence is partitioned into five distinct, specialized knowledge layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        WHERE KNOWLEDGE LIVES                           │
├─────────────────────────┬──────────────────────────────────────────────┤
│ 1. MODEL WEIGHTS        │ Generalized linguistic reasoning, DAG logic, │
│    (Qwen / Spark)       │ code syntax, tool calling grammar.           │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 2. PROCEDURAL SKILLS    │ Reusable multi-step workflows (SKILL.md +    │
│    (Hermes Harness)     │ scripts/run.py). Modular, editable, linted.  │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 3. SEMANTIC MEMORY      │ User preferences, machine topology, entity   │
│    (SQLite WAL + FTS5)  │ paths, configuration constants.              │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 4. EPISODIC MEMORY      │ Execution traces, observation histories,     │
│    (Trajectory Store)   │ past error reflections, session logs.        │
├─────────────────────────┼──────────────────────────────────────────────┤
│ 5. DETERMINISTIC        │ Trusted machine operations: ActionGate,      │
│    CAPABILITIES (Core)  │ SecretBroker, Job Object sandbox, Win32/CDP. │
└─────────────────────────┴──────────────────────────────────────────────┘
```

### Empirical Storage & Fine-Tuning Rules:
1. **Use Procedural Skills** when the workflow is deterministic, repeatable, and multi-step (e.g. battery report generation, invoice extraction, project scaffolding). Procedural workflows themselves should normally remain externalized as validated skills rather than being baked into model weights.
2. **Use Semantic/Episodic Memory** when the data is declarative, user-specific, or historical (e.g. default download directory, preferred editor, previous failure causes).
3. **Fine-Tuning Policy**:
   **Fine-tuning is reserved for generalized, repeatedly observed model-level failure modes that cannot be solved more cheaply/reliably through deterministic logic, retrieval, memory, skills, prompting, or runtime validation.**
   
   Possible fine-tuning targets may include:
   - Structured output and JSON schema adherence
   - DAG planning and topological dependency ordering
   - Argument binding under messy user constraints
   - Tool selection from large candidate sets
   - Progressive skill selection from header lists
   - Abstention and clarification triggering on ambiguous goals
   - Failure diagnosis from error observations
   - Replanning and recovery graph synthesis
   - Compact UI representation understanding (`@e{id} {type} "{name}" [{bbox}]`)
   - Safety classification and ActionGate compliance
   
   **Any fine-tuning decision must be strictly justified by the frozen vanilla-model failure profile.**

---

## 5. Lab J Specification: Complete Procedural Skill Lifecycle

Lab J tests the entire procedural skill lifecycle in complete isolation from production `src/astrarun/`:

```
[Execution Trajectory] ──► [Generalize to SKILL Candidate] ──► [AST Security Lint]
                                                                      │ (Pass)
[Registered in Library] ◄── [Sandbox Dry-Run Test] ◄── [Job Object Sandbox]
          │
[Header Retrieval] ──► [Full Skill View] ──► [Parameter Binding] ──► [Execution]
                                                                          │ (Inject Fail)
                                                                          ▼
                                                                  [Adaptive Replan]
```

### Lab J Test Stages:
1. **Trajectory Ingestion**: Ingest a 6-step raw execution trace (e.g. WiFi scan, signal check, reconnect).
2. **Generalization**: Distill the trace into a generalized `SKILL.md` (metadata frontmatter, description, typed input schema) and a self-contained `run.py` script.
3. **AST Linting & Security Scan**: Parse `run.py` with Python's `ast`. Verify that no unauthorized modules (`socket`, `subprocess`, `ctypes`, `os.system`) or raw shell executions exist.
4. **Sandbox Dry-Run**: Execute `run.py` inside a Windows Job Object sandbox with mock environment variables and a 128 MB RAM limit.
5. **Registration**: Store the validated skill in the temporary test skill library.
6. **Progressive Retrieval**: Query the library with an ambiguous natural-language goal. Verify that header matching retrieves the skill without loading the full body.
7. **Parameter Binding & Execution**: Bind concrete runtime parameters from the prompt and execute the script.
8. **Injected Failure & Recovery**: Inject a simulated error (e.g. WiFi interface disabled); verify that the agent detects failure and emits an alternative recovery step rather than looping.

---

## 6. Defense-in-Depth: Hermes Linting vs Astra Security

> [!IMPORTANT]
> **Hermes AST skill linting is strictly a DEFENSE-IN-DEPTH pre-flight filter.**  
> It does **NOT** replace, bypass, or weaken AstraRun's deterministic security layer:
> - **ActionGate**: Every concrete action (file write, command run, process kill) must be cryptographically authorized by the ActionGate.
> - **SecretBroker**: In-memory token scrubbing and HMAC isolation cannot be bypassed by a skill.
> - **Windows Job Object Sandbox**: All skill scripts run within hard memory ceilings (128 MB), process tree kill-on-close, and execution timeouts.
> - **Filesystem & Network Scopes**: Skills have zero ambient system authority.

A skill that passes AST linting with zero warnings still possesses **zero runtime privileges** until AstraRun's deterministic policy layer authorizes each step.

---

## 7. The 26 Adversarial Failure-Boundary Torture Vectors

*(Retained from Baseline Specification)*
1. Literal vs Executable Payload
2. Negation Handling
3. Lexical Ambiguity
4. Pronoun Resolution
5. Malformed Observations
6. Stale Observations
7. Unseen Tools & Combinations
8. Distractor Tool Overload (100, 250, 500 tools)
9. Conditional & Parallel DAGs
10. Output-to-Input Parameter Bindings
11. Tool Failure Injection
12. Repeated Failure Loops (Infinite Loop Prevention)
13. Genuine Replan on Missing Primitives
14. Impossible Goals & Guardrail Refusals
15. Direct & Indirect Prompt Injections (100% rejection required)
16. Malicious Filenames, Paths, and SSIDs
17. Long-Horizon Trajectories (15+ turns)
18. Early-Step Poisoning
19. Verification Traps (Silent Failure Detection)
20. User Mid-Action Takeover & Cancellation
21. Partial Completion Checkpoint Resumption
22. Quantization Cliff (`Q8_0` $\to$ `Q5_K_M` $\to$ `Q4_K_M`)
23. Semantic Compact Indexing Adherence (`@e{id}`)
24. Progressive Skill Header Precision
25. Code Delegation Trigger Accuracy
26. Cross-Model Skill Execution Fidelity

---

## 8. Role Scorecard Format

```
ROLE SCORECARD (Per Model Candidate):
├── Macro Planning & DAG Generation:
│   ├── Topological DAG Validity:       [Pass Rate %]
│   ├── Edge Dependency Accuracy:       [Pass Rate %]
│   └── Deadlock / Cycle Rate:          [Rate %]
├── Hermes-Style Skill Harness:
│   ├── Header Selection Recall@1:      [Recall %]
│   ├── Header Selection Recall@3:      [Recall %]
│   ├── False Skill Activation Rate:    [Rate %]
│   └── Parameter Binding Accuracy:     [Pass Rate %]
├── Execution & Failure Adaptation:
│   ├── Code Delegation Trigger Rate:   [Pass Rate %]
│   ├── Injected Failure Recovery:      [Pass Rate %]
│   └── Infinite Loop Abort Rate:       [Pass Rate %]
├── Security & Safety:
│   ├── Prompt Injection Defense:       [100% Mandatory]
│   └── ActionGate Refusal Compliance:  [100% Mandatory]
└── Hardware & Latency:
    ├── Time to First Token (TTFT):     [Measured ms]
    ├── Generation Speed (TPS):         [Measured tok/s]
    ├── Peak VRAM Allocation:           [Measured MB]
    └── Host CPU RAM Overhead:          [Measured MB]
```
