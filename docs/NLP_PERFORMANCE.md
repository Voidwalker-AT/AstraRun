# AstraRun v0.6.5 — NLP Performance & Profiling Report

> **Host Environment**: 12th Gen Intel Core i5-12450H, 16 GB RAM, Windows 11 x64  
> **Python Version**: 3.13.0 (64-bit)  
> **Milestone**: AstraRun v0.6.5  
> **Status**: APPROVED  

---

## 1. Latency & Throughput Profile

AstraRun's NLP architecture separates interactive keystroke filtering from committed natural language parsing:

```text
User Typing (Keystrokes) ──────────> Existing Fuzzy Index (< 0.1 ms)
User Commit (Enter / Voice) ───────> NLU Engine & Workflow Compiler (< 1.0 ms)
```

### Measured Latency Percentiles (Test Set V1, 310 cases)

| Pipeline Configuration | Mean Latency | Median ($p_{50}$) | 95th Percentile ($p_{95}$) | 99th Percentile ($p_{99}$) | Budget Target |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **LRU Cache Hit** | **0.0004 ms** | **0.0004 ms** | **0.0006 ms** | **0.0009 ms** | $< 0.1\text{ ms}$ |
| **Deterministic Rules + Grammar** | **0.394 ms** | **0.378 ms** | **0.501 ms** | **0.824 ms** | $< 5.0\text{ ms}$ |
| **Hybrid (Rules + spaCy)** | **7.157 ms** | **7.019 ms** | **10.429 ms** | **14.281 ms** | $< 100.0\text{ ms}$ |

---

## 2. Memory Footprint Profile

| Component | Resident Set Size (RSS) | Memory Delta |
| :--- | :--- | :--- |
| **Python Baseline Process** | 26.2 MB | — |
| **NLPEngine (Deterministic Rules)** | 26.5 MB | **+0.3 MB** |
| **ProjectRegistry Loaded (28 Projects)**| 27.1 MB | **+0.6 MB** |
| **spaCy 3.8.16 + `en_core_web_sm`** | 296.4 MB | **+269.3 MB** |

---

## 3. Cold Start & Initialization Timings

- **NLPEngine Initialization (Deterministic)**: **4.68 ms**
- **ProjectRegistry Disk Load**: **2.15 ms**
- **WorkflowCompiler Initialization**: **0.85 ms**
- **spaCy Cold Import & Model Load**: **8,438.2 ms** (Kept optional / lazy-loaded to prevent launcher startup delays)
