# Strategic Analysis: Local Decision Models vs Cloud-Hosted Judges (v0.5)

> **Document Status**: APPROVED  
> **System Version**: AstraRun v0.5  
> **Comparison**: Local Laya Ensemble vs TypeSafe Jev System One  
> **Author**: Lead Engineer, AstraRun  

---

## 1. The Core Strategic Question

As local workstations incorporate autonomous AI capabilities, systems engineers face an architectural fork:

> *Should workstation command interpretation and intent routing rely on cloud-hosted frontier decision APIs, or should it run strictly on local, specialized on-device neural models?*

In AstraRun v0.5, we subjected this question to rigorous empirical and architectural evaluation, comparing our local **Laya Ensemble** (ModernBERT-large based System One models) against **TypeSafe Jev** (cloud-hosted System One API).

---

## 2. Key Empirical & Strategic Findings

### 2.1 The Sovereignty Invariant
Workstation command launchers are uniquely sensitive. A launcher processes:
- Names of private repositories (`Active/server`, `SecurityWorkbench`)
- Local file paths (`E:\Workspace\...`)
- Process names, database credentials, port numbers, and developer workflows
- Internal project IDs from `workspace.json`

Transmitting this stream to a third-party cloud endpoint (even a calibrated decision API like Jev) presents fundamental compliance, security, and IP risks. Local Laya models process 100% of tokens on the local CPU/GPU within host memory boundaries, guaranteeing complete privacy and zero telemetry leakage.

### 2.2 Offline Availability & Air-Gap Resilience
A core design requirement for AstraRun is that the launcher must function identically whether connected to high-speed fiber, intermittent Wi-Fi, or completely offline in an air-gapped security environment. Cloud-dependent routing would turn AstraRun into a brick whenever internet connectivity degrades. Local Laya models require zero network access.

### 2.3 Domain Adaptation Advantage
Cloud APIs offer generic domain knowledge but zero awareness of local workstation conventions. Our domain-adaptation pipeline (`scripts/train_laya_astrarun.py`) demonstrates that adapting 26M parameters of Laya's decision head on 250 local examples increases workstation intent accuracy dramatically (from ~40.9% zero-shot to >88%), outperforming even state-of-the-art generic cloud models on local developer queries.

### 2.4 Latency Realities
While cloud APIs have fast server GPUs, they pay a 15–50ms network round-trip penalty. Conversely, while local CPU inference on ModernBERT-large currently takes ~500ms for a single question on this host CPU, local inference can be aggressively accelerated via ONNX Runtime, OpenVINO, or dedicated GPU/NPU offload.

---

## 3. Recommended Multi-Tier Architecture

Rather than choosing between local and cloud exclusively, AstraRun adopts a **strict hierarchical isolation architecture**:

```text
[ User Natural Language Input ]
               │
               ▼
   [ Tier 0: Deterministic & Fuzzy Matcher ]  <-- < 4ms, 100% Execution Authority
               │
      (Unmatched / Ambiguous)
               │
               ▼
   [ Tier 1: Local Laya Decision Fusion Engine ] <-- Local CPU/GPU, Shadow / Advisory
      - Domain-Adapted AstraRun-Laya
      - Generic Zero-Shot Laya
      - Disagreement Gating & Ambiguity Check
               │
      (Periodic Audit & Benchmarking)
               │
               ▼
   [ Tier 2: Quarantined Offline Reference Judge (Jev) ] <-- Zero Execution Authority
```

1. **Production Execution**: Strictly governed by Tier 0 and validated Tier 1 gating.
2. **Local Neural Reasoning**: Handled entirely by Tier 1.
3. **Cloud Judges (Jev)**: Strictly relegated to Tier 2 as an offline calibration benchmark and dataset validator during scheduled evaluation cycles.
