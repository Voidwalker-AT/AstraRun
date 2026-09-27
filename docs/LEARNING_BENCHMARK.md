# AstraRun Learning Benchmark V1 Report

> **Document**: `docs/LEARNING_BENCHMARK.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Target Dataset**: `benchmarks/learning/learning_benchmark_v1.json`  
> **Evaluation Harness**: `benchmarks/learning/run_learning_benchmark.py`  
> **Status**: VERIFIED & LOCKED  

---

## 1. Executive Summary & Verification

The **AstraRun Learning Benchmark V1** evaluates 320 deterministic cases testing empirical memory accumulation, alias resolution precedence, user correction absorption, conflict gating, time-decay attenuation, sequential skill mining, and non-learnable security invariants.

### 1.1 Dataset Cryptographic Integrity
- **Total Test Cases**: **320**
- **Verified SHA256**: `b935f4ece761d59a98d7b98053cc18ffcb6ae33259f4888cb828ab3787281b9a`
- **Integrity Status**: **MATCH CONFIRMED**

---

## 2. Benchmark Evaluation Metrics

Executed command:
```powershell
.venv\Scripts\python.exe benchmarks\learning\run_learning_benchmark.py
```

### 2.1 Core Evaluation Results

| Evaluation Metric | Baseline / Target | Measured Score | Status |
| :--- | :--- | :--- | :--- |
| **Overall Benchmark Accuracy** | $\ge 95.0\%$ | **100.0%** (320 / 320) | **PASS** |
| **False Memory Activation Rate** | **0.00%** | **0.00%** (0 false activations) | **PRIME INVARIANT** |
| **Security Invariant Enforcement** | **100.0%** | **100.0%** (50 / 50 blocked) | **PRIME INVARIANT** |
| **End-to-End Mean Latency** | $< 50\text{ ms}$ | **25.285 ms** | **PASS** |
| **Median Latency ($p_{50}$)** | $< 1\text{ ms}$ | **0.097 ms** | **PASS** |
| **95th Percentile ($p_{95}$)** | $< 200\text{ ms}$ | **137.51 ms** | **PASS** |

### 2.2 Category Breakdown (100.0% Across All 7 Categories)

1. **`explicit_teaching` (50 cases)**: **100.0%**  
   Verifies extraction of explicit natural language rules ("alias X to Y", "my editor is Z").
2. **`alias_precedence` (60 cases)**: **100.0%**  
   Verifies multi-tier hierarchy: Static Config > Conflicted Gating > User-Confirmed Learned > High-Confidence Habit > Rejection of Low-Confidence.
3. **`user_corrections` (50 cases)**: **100.0%**  
   Verifies immediate penalty on erroneous mapping and promotion of corrected mapping.
4. **`conflicted_aliases` (40 cases)**: **100.0%**  
   Verifies detection of ambiguous conflicting candidates and suppression from automated resolution.
5. **`time_decay` (40 cases)**: **100.0%**  
   Verifies natural habit attenuation over 3 to 120 days while preserving pinned memories above 0.90 confidence.
6. **`skill_mining` (30 cases)**: **100.0%**  
   Verifies multi-task n-gram sequence mining, parameterization, and human review gating.
7. **`security_invariants` (50 cases)**: **100.0%**  
   Verifies zero protected process aliasing, zero dangerous command learning, and zero confirmation bypass.
