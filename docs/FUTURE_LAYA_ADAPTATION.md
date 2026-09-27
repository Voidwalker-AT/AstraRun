# Future Laya Domain Adaptation & Offline Fine-Tuning Strategy

> **Document**: `docs/FUTURE_LAYA_ADAPTATION.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Status**: APPROVED ROADMAP & STRATEGY  

---

## 1. Context: Zero Online Weight Updates

AstraRun v0.8.5 strictly enforces:
> **Zero online gradient descent, zero dynamic LoRA hot-patching, and zero live model mutation.**

Live weight updates in a desktop launcher introduce severe instability:
- Catastrophic forgetting on common vocabulary.
- Vulnerability to adversarial prompt injection poisoning model weights.
- Unpredictable GPU/CPU memory spikes during interactive usage.

---

## 2. The Offline Distillation Pipeline

Future milestones (v0.9+) will support periodic, offline adaptation of local semantic models (Laya 0.5B) via the following controlled pipeline:

```mermaid
flowchart TD
    Ledger["TaskLedger & MemoryStore\n(Verified 100% Local Data)"] --> Check{"allow_training_dataset_export\n== True?"}
    Check -- No --> Block["Export Gated (Default)"]
    Check -- Yes --> Sanitizer["DatasetBuilder\n(Redact Tokens & Passwords)"]
    Sanitizer --> JSONL["Sanitized Dataset\n(data/learning_dataset.jsonl)"]
    JSONL --> OfflineHarness["Offline Training Harness\n(External Environment / Scheduled Job)"]
    OfflineHarness --> Eval["Holdout Benchmark Set V3\n(Regression & Safety Gating)"]
    Eval --> Gate{"Benchmark Score > Prior Model\nAND Zero Safety Regressions?"}
    Gate -- No --> Reject["Discard Checkpoint"]
    Gate -- Yes --> Promote["Promote as AstraRun-Laya-v2\n(Subject to User Review)"]
```

---

## 3. Holdout Benchmark Gating & Safeguards

Before any new model checkpoint can be deployed into AstraRun:
1. **Safety Evaluation**: Evaluated against the 330-case Action Benchmark, 620-case NLP Benchmark, and 320-case Learning Benchmark.
2. **Regression Ceiling**:
   - False Execution Rate must remain strictly **0.00%**.
   - Negated Action Leakage Rate must remain strictly **0.00%**.
   - Security Block Recall must remain strictly **100.0%**.
3. **Rollback Guarantee**: Previous model weights (`convaiinnovations/laya`) remain pinned and accessible for instantaneous one-click rollback in settings.
