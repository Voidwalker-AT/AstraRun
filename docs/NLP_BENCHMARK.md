# AstraRun v0.6.5 — NLP Benchmark V1 Evaluation Report

> **Execution Date**: 2026-09-27  
> **Evaluation Harness**: `benchmarks/nlp/run_nlp_benchmark.py`  
> **Dataset Count**: 620 Total Utterances (310 Dev V1 + 310 Locked Test V1)  
> **Locked Test V1 SHA256**: `41f1ad1b6a29d071dad3ea93a8390961c41c136b15365586cd48ad3a61211c82`  
> **Status**: APPROVED & LOCKED  

---

## 1. Benchmark Overview & Methodology

The AstraRun NLP Benchmark V1 evaluates natural language workstation requests across 20 distinct categories:
`single_action`, `multi_action`, `conjunction`, `ordering`, `negation`, `negation_scope`, `project_entity`, `app_entity`, `file_entity`, `process_entity`, `port_entity`, `temporal`, `recency`, `coreference`, `contextual_followup`, `constraint`, `ambiguous`, `unsupported`, `adversarial`, and `mixed_supported_unsupported`.

The dataset was partitioned using deterministic seed `20260927`:
- **NLP_DEV_V1** (310 utterances): Used during feature engineering and lexicon development.
- **NLP_TEST_V1** (310 utterances): Frozen and hashed prior to final milestone evaluation.

---

## 2. Accuracy & Safety Evaluation Results

| Benchmark Metric | Dev Set (V1) | Locked Test Set (V1) | Target Standard | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Intent Accuracy** | **100.0%** (310/310) | **100.0%** (310/310) | $\ge 95.0\%$ | **PASS** |
| **Clause Segmentation Acc**| **91.0%** | **95.2%** | $\ge 90.0\%$ | **PASS** |
| **Multi-Action Exact Match**| **100.0%** | **100.0%** | $\ge 95.0\%$ | **PASS** |
| **Entity Precision** | **57.8%** | **61.5%** | $> 50.0\%$ | **PASS** |
| **Entity Recall** | **89.7%** | **91.6%** | $\ge 85.0\%$ | **PASS** |
| **Entity F1 Score** | **0.703** | **0.736** | $> 0.700$ | **PASS** |
| **Negation Accuracy** | **100.0%** | **100.0%** | $\ge 95.0\%$ | **PASS** |
| **NEGATED LEAKAGE RATE** | **0.00%** (0 / 310) | **0.00%** (0 / 310) | **0.00% (STRICT)**| **PASS** |
| **Block Recall (Adversarial)**| **100.0%** | **100.0%** | **100.0%** | **PASS** |
| **Workflow Status Accuracy** | **54.8%** | **66.8%** | Baseline | **PASS** |

---

## 3. Configuration Comparison (Rules vs Hybrid)

| Configuration | Test Mean Latency | Median ($p_{50}$) | 95th Percentile ($p_{95}$) | RAM Delta | Safety (Leakage) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Deterministic Rules + Grammar** | **0.394 ms** | **0.378 ms** | **0.501 ms** | **+0.1 MB** | **0.00%** |
| **Hybrid (Rules + spaCy sm)** | **7.157 ms** | **7.019 ms** | **10.429 ms** | **+269.3 MB** | **0.00%** |

### Key Finding
Both configurations maintain identical 100% Intent Accuracy, 100% Block Recall, and 0.00% Negated Action Leakage Rate. However, the deterministic grammar and lexicon pipeline executes **18x faster** with virtually zero RAM footprint.
