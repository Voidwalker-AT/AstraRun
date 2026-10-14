# F0-25F.6 Routing Architecture Specification

> **Phase**: F0-25F.6 — Routing Generalization, Intelligent Fallback, Security & Intelligence Certification  
> **Status**: APPROVED & ACTIVE  
> **Component**: Intelligence Routing Hierarchy & Context-Sufficiency Model  

---

## 1. Architectural Principles

AstraRun's intelligence routing operates on strict capability grounding and context sufficiency, eliminating fragile exact-phrase heuristics while guaranteeing deterministic security boundaries.

The core routing pipeline adheres to:
$$\text{UNDERSTAND} \longrightarrow \text{ROUTE} \longrightarrow \text{PLAN} \longrightarrow \text{GOVERN} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE} \longrightarrow \text{VERIFY}$$

```
                           User Prompt
                                |
                                v
               +--------------------------------+
               |     Security Policy Gate       | ---> SECURITY_REJECTION (Fail-Closed)
               +--------------------------------+
                                |
                                v
               +--------------------------------+
               |     External AI Delegation     | ---> DELEGATE_EXTERNAL_AI
               +--------------------------------+
                                |
                                v
               +--------------------------------+
               |   Conversational / Inquiry     | ---> CONVERSATIONAL
               +--------------------------------+
                                |
                                v
               +--------------------------------+
               |   Dynamic Computation & Code   | ---> DYNAMIC_COMPUTATION
               +--------------------------------+
                                |
                                v
               +--------------------------------+
               |   Multi-Step Composition DAG   | ---> COMPOSITE
               +--------------------------------+
                                |
                                v
               +--------------------------------+
               |   Capability-Grounded Matching | ---> KNOWN_CAPABILITY (Sufficient)
               +--------------------------------+
                                |
                                v
               +--------------------------------+
               |  Context Sufficiency Gate      | ---> CLARIFICATION_REQUIRED (Missing Info)
               +--------------------------------+
```

---

## 2. Capability Grounding

Routing must know what AstraRun can physically execute by consulting the authoritative `CapabilityRegistry` (88+ typed capabilities) and `AUTHORITATIVE_CAPABILITY_MANIFEST`.

### Capability Grounding Invariants
1. **Zero-Argument Capabilities**:
   Capabilities requiring 0 required arguments (e.g., `list_windows`, `system_summary`, `cpu_status`, `memory_status`, `battery_status`, `gpu_status`, `audio_status`, `wifi_status`, `wifi_scan`, `list_processes`, `list_listening_ports`, `lock_workstation`, `take_screenshot`, `foreground_window`) are fully grounded by active machine state. Prompts addressing these domains must **never** be classified as `CLARIFICATION_REQUIRED` due to missing targets.
2. **Parameterized Capabilities**:
   Capabilities requiring specific targets (e.g., `kill_process_by_pid`, `open_file`, `wifi_connect`) check for parameter presence or active context grounding.
   - If parameter is provided: `KNOWN_CAPABILITY`.
   - If parameter is grounded in context: `KNOWN_CAPABILITY`.
   - If parameter is an ungrounded pronoun ("it", "that file") without context: `CLARIFICATION_REQUIRED`.
3. **Safe Desktop Query Grounding**:
   Natural inquiries regarding machine state (e.g., "what processes are running?", "is notepad running?", "do i have vivaldi installed?") are operational queries mapped to `list_processes`, `is_application_running`, or `find_application`, **not** conversational trivia.

---

## 3. Context Sufficiency Assessment

Explicitly differentiates:
- **UNKNOWN LANGUAGE / NONSENSE / BARE NOUNS**: Non-operational input requiring intent clarification.
- **MISSING EXECUTION INFORMATION**: Operational intent exists, but mandatory arguments (file path, PID, target) are omitted and ungrounded.
- **SUFFICIENTLY SPECIFIED**: Either zero-argument capability, or required arguments are extracted or present in active context.

### Classification Categories
1. `DYNAMIC_COMPUTATION`: Algorithmic synthesis, mathematical simulations, data parsing pipelines, scientific computing, procedural graphics requiring sandbox execution.
2. `KNOWN_CAPABILITY`: Direct invocation of a single registered workstation capability with sufficient arguments.
3. `COMPOSITE`: Multi-step operational workflow combining 2 or more discrete capabilities via sequential or DAG execution.
4. `CONVERSATIONAL`: General knowledge, advice, greetings, literary/trivia discussions, troubleshooting complaints without command verbs.
5. `CLARIFICATION_REQUIRED`: Bare nouns, bare verbs without operands, ungrounded pronouns, underspecified operations missing mandatory parameters.
6. `DELEGATE_EXTERNAL_AI`: Explicit delegation to external advisors (ChatGPT, Claude, external models).
7. `SECURITY_REJECTION`: Hard policy violations (destructive disk wiping, OS deletion, malware).

---

## 4. Composition vs Dynamic Computation Boundary

- **Dynamic Computation** takes precedence when complex programmatic transformation of data is requested (e.g., "parse postgresql slow query log and aggregate mean execution duration by query pattern into pg_slow_summary.json"), even if conjunctions ("and") are present.
- **Composite Workflows** apply when distinct operational capabilities are chained sequentially (e.g., "open notepad then maximize active window", "open downloads folder and check disk space").

---

## 5. Security & Verification Invariants

- **BLOCK remains BLOCK**: No fallback or routing transformation may bypass security policy.
- **CONFIRM remains CONFIRM**: Confirmation requirements are strictly inherited through all routing paths.
- **Zero False Destructive Executions**: Destructive requests fail closed immediately.
- **Zero Ungrounded Executions**: Referential pronouns without context fail closed to clarification.
