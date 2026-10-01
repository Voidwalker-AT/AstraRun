# 32 — Structured Open Questions Catalog & Phase 17 Validation Tracker

> **Scope**: Pre-Implementation Architecture Discovery & Empirical Validation Tracker  
> **Status Taxonomy**: `RESOLVED_MEASURED`, `RESOLVED_REPOSITORY`, `RESOLVED_UPSTREAM`, `HYPOTHESIS`, `EXPERIMENT_REQUIRED`, `SCHEDULED`, `BLOCKED`  
> **Status**: ACTIVE & TRACKED FOR PHASE 17  
> **Last Updated**: 2026-09-30  

---

## 1. Questions Classified by Evidence Source & Status

### Category A: `ASK_MACHINE` (Live Machine & OS Reality)
| ID | Question | Hypothesis / Target | Target Validation Method | Status |
| :---: | :--- | :--- | :--- | :---: |
| **Q-M01** | Can Windows WinRT `Windows.Media.Ocr` run directly in Python on Windows 11 Build 26100 without heavy dependencies? | WinRT OCR provides zero-VRAM text extraction in < 50ms. | Phase 17 Lab E: Run isolated WinRT OCR script against test screenshots. | **EXPERIMENT_REQUIRED** |
| **Q-M02** | What is the exact RAM footprint and handle count of PySide6 resident idle over 100 show/hide cycles? | Resident UI occupies $\le 80\,\text{MB}$ RAM with zero handle leaks. | Phase 17 Lab C: Track handle count and working set via `psutil` over 100 cycles. | **EXPERIMENT_REQUIRED** |
| **Q-M03** | Can an existing running Vivaldi browser instance be attached to via CDP (`--remote-debugging-port=9222`) without restarting? | Browser sessions and tabs can be accessed non-disruptively. | Phase 17 Lab D: Probe active Vivaldi ports and test CDP attachment flags. | **EXPERIMENT_REQUIRED** |
| **Q-M04** | When an external inference worker unloads or is terminated on the RTX 2050, does Windows reclaim 100% of VRAM? | OS kernel reclaims 100% of VRAM and driver contexts on worker kill. | Phase 17 Lab C: Query `pynvml` memory counters before, during, and 1s after process kill. | **EXPERIMENT_REQUIRED** |

---

### Category B: `ASK_WEB` (Literature, Competitor & Upstream Framework Studies)
| ID | Question | Empirical Finding / Upstream Evidence | Primary Reference | Status |
| :---: | :--- | :--- | :--- | :---: |
| **Q-W01** | What is Microsoft UFO's multi-agent action server protocol and does its license permit commercial/local adaptation? | Upstream confirms UFO is MIT-licensed. Demonstrates dual-agent (HostAgent + AppAgent) architecture and WinCOM for Office. | `07_UFO_DEEP_DIVE.md` | **RESOLVED_UPSTREAM** |
| **Q-W02** | How does Browser Use manage session persistence and DOM element grounding without sending full HTML to the model? | Upstream confirms accessibility tree (`a11y-tree`) extraction with `@e1` tokens, but attaching to default profile often requires dedicated launch flags. | `09_BROWSER_RESEARCH.md` | **RESOLVED_UPSTREAM** |
| **Q-W03** | What are the exact architectural specifications, context window, and quantization formats for `XHToken/Spark-X2.5`? | Upstream confirms 1:3 Hybrid Attention, native 1M context, Apache 2.0 license. GGUF available on Hugging Face; supported in recent Ollama/LM Studio. | `16_SPARK_X25_RESEARCH.md` | **RESOLVED_UPSTREAM** |
| **Q-W04** | How does Hermes Agent represent procedural skills and what is its tool-calling schema? | Upstream confirms XML `<tool_call>` standard; "Skills as Compute Optimization" compiles verified workflows into reusable markdown + script bundles. | `10_HERMES_RESEARCH.md` | **RESOLVED_UPSTREAM** |

---

### Category C: `ASK_EXPERIMENT` (Controlled Benchmarks & Torture Studies)
| ID | Question | Hypothesis | Experimental Setup | Status |
| :---: | :--- | :--- | :--- | :---: |
| **Q-E01** | Can `Spark-X2.5-1.7B` at Q4_K_M reliably output strictly valid JSON/DAGs without hallucinating tool parameters? | Spark 1.7B maintains $\ge 90\%$ schema validity under tool load. | Phase 17 Lab A/B: Model Tournament & Torture Suite (Vectors 2 & 5). | **SCHEDULED** |
| **Q-E02** | Does thinking mode (`<think>...</think>`) in small reasoning models improve multi-step planning accuracy or merely increase latency? | Thinking tokens improve planning depth on $>3$ step DAGs. | Phase 17 Lab A: Comparative latency/accuracy runs with thinking on/off. | **SCHEDULED** |
| **Q-E03** | How much does tool distraction (inserting 100/250/500 tools) degrade small model retrieval accuracy? | Hybrid FTS5 + ONNX retrieval mitigates distraction by filtering to top-6 tools. | Phase 17 Lab F: Retrieval recall benchmarks across 5, 25, 100, 500 tool sets. | **SCHEDULED** |

---

### Category D: `ASK_SELF_REDTEAM` (Adversarial Architectural Challenges)
| ID | Question | Empirical Finding / Red-Team Finding | Primary Reference | Status |
| :---: | :--- | :--- | :--- | :---: |
| **Q-R01** | Is the current 100% score on the Generality Benchmark an artifact of synthetic simplicity? | Confirmed: `GoalPlanner._extract_arguments_for_capability` contained hardcoded regex checks matching held-out test tool names. | `01_CURRENT_REALITY.md` | **RESOLVED_REPOSITORY** |
| **Q-R02** | Can a webpage or message trick Astra into executing a malicious command disguised as helpful data? | Quarantined envelope `<untrusted_web_observation>` must be tested against 20 adversarial injection payloads. | Phase 17 Lab D & Model Torture Vector 3. | **EXPERIMENT_REQUIRED** |
| **Q-R03** | What happens to AstraRun when the host machine hits 95% RAM and starts heavy pagefile thrashing? | Windows Job Objects must enforce process ceilings before OS swap thrashing occurs. | Phase 17 Lab G: Quota stress test in isolated sandbox. | **EXPERIMENT_REQUIRED** |
