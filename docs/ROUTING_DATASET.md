# AstraRun Routing Benchmark Dataset Specification

> **Version**: 0.2.0  
> **Status**: APPROVED  
> **Location**: `benchmarks/routing/routing_dataset.json`  

---

## 1. Motivation & Purpose

As AstraRun evolves from deterministic rule-based heuristics towards multi-tiered local AI models (Laya -> Kev -> AI Bridge), we must possess an empirical, reproducible test harness.

A benchmark dataset of authentic workstation commands allows us to objectively quantify:
1. **Resolution Accuracy**: Does the router identify the correct intent and target?
2. **False Execution Rate (Critical Safety Metric)**: Does the router mistakenly guess and execute a random application when given an ambiguous or unsupported query?
3. **Latency & Calibration**: Does confidence align with actual accuracy, and does decision latency remain sub-millisecond?

---

## 2. Dataset Schema

The benchmark dataset consists of an array of JSON objects structured as follows:

```json
{
  "request": "open notepad",
  "expected": {
    "intent": "open_app",
    "target": "notepad",
    "should_execute": true
  },
  "category": "exact_app",
  "description": "Standard action verb + application key"
}
```

### Field Definitions

| Field | Type | Description |
| :--- | :--- | :--- |
| **`request`** | `string` | The raw text input entered by the user. |
| **`expected.intent`** | `string` | The expected tool (`open_app`, `open_folder`, `open_url`, `refresh_apps`, or `unknown`). |
| **`expected.target`** | `string \| null` | The expected normalized identifier or target key. Null if unresolved. |
| **`expected.should_execute`** | `boolean` | `true` if this command should execute immediately; `false` if it must be rejected or held as ambiguous. |
| **`category`** | `string` | Partition tag (`exact_app`, `alias_app`, `prefix_app`, `typo_app`, `folder`, `url`, `action_verb`, `ambiguous`, `unknown`, `security_probe`). |
| **`description`** | `string` | Human-readable rationale for the expected outcome. |

---

## 3. The Rejection Criterion (Crucial Safety Policy)

> [!CAUTION]
> **A launcher that always guesses is dangerous.**
>
> If a user enters:  
> `"open the project from yesterday"`  
> AstraRun v0.2 cannot reliably resolve which project is intended without semantic workspace indexing.  
> The **ONLY** safe, correct response is:  
> `expected.intent = "unknown"`, `expected.should_execute = false`.  
>
> Inadvertently launching Visual Studio Code or Notepad in this scenario counts as a **False Execution Failure**, which is severely penalized.

---

## 4. Evaluation Metrics Computed by Runner

1. **Overall Accuracy**: Total correct decisions / Total queries.
2. **Exact Query Accuracy**: Accuracy on exact app/folder/URL names.
3. **Fuzzy & Typo Accuracy**: Accuracy on prefixes, acronyms, and single-character typos.
4. **Unresolved Accuracy**: Proportion of out-of-scope/ambiguous queries correctly rejected.
5. **False Execution Rate**: Percentage of unsupported queries that were erroneously executed. Target: **0.0%**.
6. **Latency Distribution**: Mean, p50, and p95 routing time in microseconds (µs).
