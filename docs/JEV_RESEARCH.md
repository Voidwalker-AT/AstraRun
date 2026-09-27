# Jev Upstream Research & Architecture Specification

> **Document Status**: APPROVED SPECIFICATION  
> **Vendor / Organization**: TypeSafe AI (Released September 2026)  
> **Evaluation Role**: External Reference Decision Model (Zero Production Authority)  
> **Date**: 2026-09-27  

---

## 1. Upstream Product Profile

- **Product Name**: Jev (Hosted "System One" Decision Model)
- **Developer**: TypeSafe AI
- **Official API Endpoint**: `POST https://api.typesafe.ai/v1/systemone`
- **Official Python SDK**: `typesafe-sdk` (`from typesafe_sdk import TypeSafeClient`)
- **API Authentication**: Environment variable `TYPESAFE_API_KEY` (passed via `Authorization: Bearer <API_KEY>`)
- **License / Delivery**: Proprietary hosted SaaS API; OpenRouter compatible endpoint available.

---

## 2. Core Philosophy & "System One" Architectural Role

Unlike general-purpose generative Large Language Models (LLMs) that output conversational prose or code via token-by-token autoregression, Jev is specifically engineered for **schema-constrained decision classification**:
- **State In, Structured Judgment Out**: Accepts input `state` (plain text or structured JSON) alongside a schema of typed questions.
- **Zero Hallucination of Text**: Does not generate rationales, conversational markdown, or unconstrained command strings.
- **Decision Primitives**:
  1. `choice`: Multi-class probability distribution over candidate labels with normalized softmax calibration.
  2. `noul`: Calibrated Boolean proposition probability $P(\text{true}) \in [0.0, 1.0]$.
  3. `score`: Bounded ordinal scale evaluation (returning expected numeric value and probability per discrete level).
- **Multi-Question Parity**: Supports evaluating multiple typed questions (`intent`, `ambiguity`, `risk`) in a single HTTP request payload.

---

## 3. API Payload & Question Parity with Laya

Jev uses question structures identical in concept to Laya's decision schema:

```json
{
  "state": "open visual studio code",
  "questions": {
    "intent": {
      "type": "choice",
      "instructions": "Which workstation action does the user intend?",
      "criteria": {
        "open_app": "Launch an installed desktop application",
        "open_folder": "Open a local filesystem folder",
        "open_url": "Navigate to a website URL",
        "open_project": "Open a software development workspace",
        "find_file": "Search for a document or source file",
        "process_action": "Inspect or terminate a running process",
        "system_action": "System setting, volume, power, or restart",
        "ai_query": "Ask a question to an AI assistant",
        "browser_action": "Browser tab, history, or web control",
        "unknown": "Ambiguous, out-of-scope, or unsupported"
      }
    },
    "ambiguity": {
      "type": "choice",
      "instructions": "Does the request contain sufficient information to execute, or is it ambiguous?",
      "criteria": {
        "safe_to_resolve": "Request contains clear target entity and specific action",
        "ambiguous": "Request uses unclear pronouns or lacks target information",
        "unknown": "Request is gibberish or unsupported"
      }
    },
    "risk": {
      "type": "choice",
      "instructions": "What is the consequence risk of executing this request?",
      "criteria": {
        "low": "Benign desktop application or read-only navigation",
        "medium": "Modifies project or workspace configuration",
        "high": "Terminates process, deletes file, or changes system setting",
        "blocked": "Destructive system modification or dangerous command"
      }
    }
  }
}
```

---

## 4. Latency, Cost & Performance Expectations

- **Latency Profile**: Upstream documentation reports 70ms to 500ms server-side inference latency. Over public WAN with TLS handshake, round-trip latency typically measures 150ms – 650ms.
- **Pricing & Token Accounting**: Billed per decision request + input token volume.
- **Calibration**: Trained via proper scoring rules for well-calibrated confidence scores.

---

## 5. Security & Privacy Boundaries for AstraRun

1. **Zero Production Authority**: Jev operates exclusively as an **offline reference benchmark model**. No output from Jev can directly reach the `ToolRegistry` or execute against the Windows OS.
2. **Strict Telemetry Quarantine**: Real workstation telemetry (`data/laya_shadow_events.jsonl`, user typing streams) must **NEVER** be sent to Jev. Only pre-sanitized evaluation benchmarks (`benchmarks/routing/`) are permitted for reference comparison.
3. **Graceful Degraded Mode (Zero Dependency)**:
   - If `TYPESAFE_API_KEY` is not present, AstraRun skips Jev evaluation cleanly without logging warnings or stalling startup.
   - All tests mock external API calls; live network calls are prohibited during automated CI / `pytest`.
