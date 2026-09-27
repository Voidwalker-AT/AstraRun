# AstraRun Learning Privacy, Data Hygiene & Sanitization

> **Document**: `docs/LEARNING_PRIVACY.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Status**: APPROVED PRIVACY SPECIFICATION  

---

## 1. 100% Local Storage & Zero External Telemetry

Workstations host sensitive private code, proprietary repository structures, internal network ports, and personal documents. AstraRun guarantees:
- **Zero Cloud Sync**: All learned memories, aliases, preferences, and skills reside strictly on the local machine in `data/astra_learning.db`.
- **Zero Network Egress**: The learning subsystem contains zero telemetry, analytics beacons, or remote logging connections.
- **Local SQLite Isolation**: The database operates with standard local filesystem permissions under the user's local profile.

---

## 2. Redaction & Secret Sanitization

The `DatasetBuilder` and `EvidenceExtractor` enforce rigorous data sanitization:
1. **Secret & Token Detection**:
   - `TOKEN_PATTERNS` regex filters automatically detect and redact:
     - GitHub Personal Access Tokens (`ghp_[a-zA-Z0-9]{36}`)
     - OpenAI API keys (`sk-[a-zA-Z0-9_-]{20,}`)
     - Generic Bearer tokens (`bearer [a-zA-Z0-9_\-\.]{20,}`)
     - Password assignments (`password = ...`)
     - High-entropy base64 chunks
   - Redacted tokens are permanently replaced with `[REDACTED_SECRET]` before storage or export.
2. **User Path Normalization**:
   - Personal user profile directories (e.g. `C:\Users\john_doe\...`) are normalized to `C:\Users\User\...` in dataset exports.

---

## 3. Explicit Export Authorization

Offline JSONL dataset generation (for future Laya fine-tuning evaluation) is strictly gated:
- `allow_training_dataset_export` in `config/settings.json` defaults to `false`.
- Calling `DatasetBuilder.build_dataset()` without `allow_export=True` or `force=True` raises an immediate `PermissionError`.
- AstraRun **never** automatically uploads or transmits exported training sets.
