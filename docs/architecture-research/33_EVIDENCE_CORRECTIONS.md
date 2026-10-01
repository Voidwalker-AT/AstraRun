# 33 — Evidence Corrections & Portfolio Audit Ledger

> **Scope**: Pre-Implementation Architecture Research Audit  
> **Status**: APPROVED AUDIT ARTIFACT  
> **Standard**: Every quantitative claim tagged as exactly one of:  
> `MEASURED_LOCAL`, `MEASURED_UPSTREAM`, `REPORTED_UPSTREAM`, `ESTIMATED`, `CALCULATED`, `HYPOTHESIS`, `TARGET`, `NOT_MEASURED`.  
> **Rule**: No architecture by vibes. No model by README. No percentage without a physical run. No "resolved" without empirical evidence.  

---

## 1. Audit Ledger: Quantitative Claim Corrections

The following table records every quantitative claim previously made in the research portfolio, its original representation, its audited correction, and its governing evidence classification:

| ID | Prior Formulation / Claim | Audited Status | Governing Evidence Tag | Detailed Correction & Justification |
| :---: | :--- | :---: | :---: | :--- |
| **C-01** | Architecture A/B/C/D North-Star pass rates: "72%", "96%", "88%", "80%" | **REMOVED** | `NOT_MEASURED` | No architecture has been run against the 25 North-Star tasks. These numbers were synthetic guesses. All benchmark pass rates set to `NOT_MEASURED`. |
| **C-02** | Model generation speed: "65–85 tokens/sec", "35–50 tokens/sec" | **RELABELED** | `ESTIMATED` | Based on general RTX 2050 mobile theoretical compute; not physically measured in AstraRun's runtime harness yet. |
| **C-03** | Model VRAM footprints: "1.02 GB", "1.18 GB", "1.95 GB", "2.45 GB" | **RELABELED** | `CALCULATED` (Weights) / `TARGET` (Runtime) | Weight sizes are mathematically calculated from parameter counts and bit-widths; operational VRAM (KV cache + CUDA buffers + context) is a `TARGET` pending Lab C measurement. |
| **C-04** | Schema adherence percentages: "96%", "81%", "54%" by quantization | **REMOVED** | `NOT_MEASURED` | Derived from generic open-source LLM quantization papers, not measured on AstraRun capability schemas. Converted to a Phase 17 hypothesis to be tested. |
| **C-05** | UI Automation (UIA) reliability: "92.0%", "99.5%" | **REMOVED** | `NOT_MEASURED` | Unmeasured on physical Windows 11 host across application classes. Relabeled as `NOT_MEASURED` pending empirical UIA benchmarks. |
| **C-06** | Windows COM latency: "< 20 ms", "99.5% reliable" | **RELABELED** | `ESTIMATED` | Estimated based on in-process COM dispatch; physical timing on Excel/Word automation will be measured in Phase 17. |
| **C-07** | Browser a11y token reduction: "> 92% reduction" | **RELABELED** | `REPORTED_UPSTREAM` | Cited from upstream Chromium / Browser-Use technical documentation. Physical reduction on target pages (WhatsApp Web, GitHub, LMS) must be measured in Lab D. |
| **C-08** | WinRT Native OCR latency & accuracy: "15–35 ms", "98.5% accuracy" | **RELABELED** | `ESTIMATED` / `NOT_MEASURED` | Based on Windows Runtime C++ API specifications. Local latency and word accuracy on anti-aliased desktop fonts are `NOT_MEASURED` on this machine until Lab E runs. |
| **C-09** | Worker memory reclamation: "100% OS reclamation guaranteed" | **RELABELED** | `HYPOTHESIS` | Architectural hypothesis based on Windows OS kernel process boundary semantics. Must be physically proven via `pynvml` in Lab C. |
| **C-10** | Vivaldi existing-session CDP attachment: "Zero duplicate RAM" | **RELABELED** | `HYPOTHESIS` / `EXPERIMENT_REQUIRED` | Chromium security policies often block CDP attachment to the active default profile without a restart or dedicated `--user-data-dir`. Must be empirically tested in Lab D. |
| **C-11** | Spark-X2.5 llama.cpp support: "Requires custom patch/branch" | **RELABELED** | `REPORTED_UPSTREAM` | Current upstream status: GGUF available on Hugging Face; community PRs exist; Ollama/LM Studio added support. Mainline master integration requires local verification. |
| **C-12** | bge-small-en-v1.5 retrieval MTEB score: "62.17" | **RELABELED** | `REPORTED_UPSTREAM` | 62.17 is the reported HuggingFace MTEB benchmark score. Performance on AstraRun's 28 workstation capability schemas is `NOT_MEASURED`. |
| **C-13** | 50,000 synthetic trajectory dataset sufficiency | **RELABELED** | `HYPOTHESIS` | 50k is an arbitrary target size. In accordance with the experimental ladder, dataset creation must begin small (100–500 curated traces) and scale only if learning curves justify it. |
| **C-14** | Full-parameter SFT superiority over LoRA / QLoRA | **RELABELED** | `HYPOTHESIS` | While full SFT modifies all attention heads, whether it significantly outperforms QLoRA on small 1.5B models for structured tool calling is unproven for AstraRun. Both must be evaluated comparatively. |

---

## 2. Updated Evidence Categories Defined

Every statement of fact throughout the architecture-research repository is governed by these exact tags:

1. **`MEASURED_LOCAL`**: Verified via physical command, script, or sensor execution on this exact workstation (`E:\Workspace\Active\AstraRun` / HP Victus i5 / RTX 2050).
2. **`MEASURED_UPSTREAM`**: Measured and published with reproducible benchmarks by primary framework authors (e.g., OSWorld benchmark results for Agent S).
3. **`REPORTED_UPSTREAM`**: Stated in official vendor documentation, model cards, or commit logs (e.g., Apache 2.0 license, native 1M context).
4. **`ESTIMATED`**: Engineering projection based on hardware specs and standard algorithmic complexity, clearly tagged as non-empirical.
5. **`CALCULATED`**: Mathematically derived from known parameters (e.g., weight bytes = params $\times$ bits / 8).
6. **`HYPOTHESIS`**: An architectural assumption or theoretical claim that is subject to falsification in Phase 17 experiments.
7. **`TARGET`**: An operational engineering goal or budget constraint (e.g., VRAM $\le 2.8\,\text{GB}$).
8. **`NOT_MEASURED`**: An empirical dimension where no physical data currently exists for this project.

---

## 3. Impact on Architectural Decisions

- **Architecture B+ is Provisional**: It is no longer described as the "winning" or "approved" architecture. It is an explicit hypothesis undergoing falsification testing.
- **North-Star Neutrality Restored**: Benchmark tasks specify observable outcomes only. No model or framework is assumed or privileged.
- **Training is Conditional**: No 50k dataset generation or 80GB lab training will occur until vanilla open models are proven to fail on the frozen holdout suite.
