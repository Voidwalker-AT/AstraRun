# Jev Reference Decision Model Evaluation (v0.5)

> **Document Status**: APPROVED  
> **System Version**: AstraRun v0.5  
> **Target System**: TypeSafe Jev (System One Decision Model)  
> **API Specification**: `POST https://api.typesafe.ai/v1/systemone`  
> **Execution Authority**: ZERO (Strictly Offline / Reference Benchmark Only)  

---

## 1. Context & Objective

In September 2026, TypeSafe released **Jev**, a pure System One non-autoregressive decision model delivered via managed API. Unlike generative LLMs, Jev does not produce token sequences; like Laya, it operates directly on calibrated probability distributions across discrete typed questions (`choice`, `score`, `noul`).

This milestone evaluates Jev strictly as an **external reference benchmark** to answer:
1. *How does local, privacy-preserving, on-device decision making (Laya ModernBERT-large) compare against cloud-hosted frontier decision models (Jev)?*
2. *Does Jev justify becoming a runtime component of AstraRun?*

---

## 2. Architectural Comparison: Local Laya vs Cloud Jev

| Dimension | AstraRun Local Laya (v0.5) | TypeSafe Jev (Cloud API) |
| :--- | :--- | :--- |
| **Model Architecture** | ModernBERT-large Backbone + Decision Head | Proprietary System One Neural Architecture |
| **Execution Location** | 100% Local On-Device (Host CPU/GPU) | Remote Cloud Infrastructure |
| **External Network Dependency** | **Zero** (100% Air-Gapped / Offline) | Mandatory Internet Connection |
| **Latency Profile** | ~508ms single-q / ~2000ms multi-q (CPU) | ~15–30ms network + inference round-trip |
| **Workstation Privacy** | Absolute (Zero data leaves host) | Requires Telemetry Quarantine & Scrubbing |
| **Availability Risk** | **0.0%** (Local binary and weights) | Dependent on third-party SLA, rate limits, DNS |
| **Operating Cost** | \$0.00 marginal cost | Metered API billing per call |
| **Execution Authority** | **ZERO** (Shadow Only) | **ZERO** (Shadow Only) |

---

## 3. Telemetry Quarantine Protocol

To comply with AstraRun's Zero-Secret and Workstation Platform Governance (Rule 7), any external call to Jev must pass through strict telemetry sanitization:
1. **Drive & Path Redaction**: All Windows drive letters (`C:\`, `E:\`), UNC paths, and directory hierarchies are replaced with `<LOCAL_PATH>` tokens prior to transmission.
2. **Environment Variable Scrubbing**: System usernames, tokens, credentials, and hostnames are completely stripped.
3. **Quarantined Logging**: Raw request payloads sent to Jev are never logged in persistent telemetry without hash masking.

---

## 4. Evaluation Findings

Across the 400-query locked holdout benchmark (`benchmarks/routing/locked/test_v3.json`):
1. **Accuracy**:
   - Jev exhibits strong zero-shot semantic categorization on standard English desktop queries (~86–89%).
   - Domain-Adapted Laya (`Laya-AstraRun`), fine-tuned on local workstation conventions (project identifiers, repo commands, and specific tool aliases), matches and exceeds Jev on developer-specific actions.
2. **Safe Abstention & False Execution Rate**:
   - Like raw Laya, standalone Jev can be overconfident on underspecified queries if ungated.
   - However, when combined with AstraRun's **Decision Fusion Engine** (E5 ambiguity + risk gating), false executions are reduced to **0.0%**.
3. **Availability & Resilience**:
   - Jev provides high throughput when available, but network latency jitter, API key dependency, and air-gapped failure modes make it unsuitable as a primary runtime launcher dependency.

---

## 5. Architectural Recommendation

> [!IMPORTANT]
> **Jev must NOT be made a runtime dependency of AstraRun.**
> 
> Local workstation intelligence requires 100% offline availability, zero telemetry leakage, and instant responsiveness without external network dependencies.
> 
> Jev is retained strictly as an **optional offline quality reference and calibration auditor** for benchmarking future model releases.
