# AstraRun Memory Provenance & Audit Trail

> **Document**: `docs/MEMORY_PROVENANCE.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Status**: APPROVED AUDIT SPECIFICATION  

---

## 1. Prime Invariant: No Provenance = No Memory

In AstraRun, **an unbacked memory is considered an invalid hallucination**. Every single `SemanticMemory` record must link directly to verifiable historical evidence pointers.

### 1.1 `EvidenceReference` Contract
```python
@dataclass(frozen=True)
class EvidenceReference:
    task_id: str
    conversation_id: str
    event_id: Optional[str] = None
    evidence_type: EvidenceType = EvidenceType.SUCCESSFUL_EXECUTION
    timestamp: float = field(default_factory=time.time)
    weight: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)
```

1. **`task_id`**: Foreign key to the specific task execution in `data/astra_history.db`.
2. **`conversation_id`**: Conversation context in which the interaction occurred.
3. **`event_id`**: Specific runtime event (e.g. `ev_confirmation_accepted_...`).
4. **`evidence_type`**: Exact classification of machine ground truth.
5. **`details`**: Sanitized telemetry attributes (e.g. capability parameters, candidate rankings).

---

## 2. Retention Independence & Safe Pruning

A major flaw in naive agent architectures is tight coupling between log retention and memory. If a user runs a "Clean History" command:
- Raw task logs are purged.
- But durable semantic preferences (e.g. "code is my editor") should **not** be lost.

AstraRun solves this via **Two-Tier Provenance Tracking**:
1. When a task in `data/astra_history.db` is pruned after 30 days, `data/astra_learning.db` retains the `evidence_records` table entry.
2. The `evidence_records` row preserves:
   - Original `task_id` and `timestamp`.
   - Aggregate support count contribution.
   - Cryptographic query hash.
3. If the user inspects provenance in the `MemoryView` UI, the entry displays:
   `Task ID: 4f98a1... [HISTORICAL TASK LOG PRUNED VIA RETENTION POLICY]`.
4. Full inspectability and mathematical confidence are preserved without keeping gigabytes of raw historical logs indefinitely.

---

## 3. Append-Only Audit Trail

All mutations across memory, skills, and aliases emit an immutable record to the `audit_events` table:

```sql
CREATE TABLE audit_events (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
```

Actions audited include:
- `MEMORY_CREATED`, `MEMORY_UPDATED`, `MEMORY_PROMOTED`, `MEMORY_DEPRECATED`, `MEMORY_DELETED`
- `SKILL_PROPOSED`, `SKILL_APPROVED`, `SKILL_REJECTED`, `SKILL_DEPRECATED`
- `CONFLICT_DETECTED`, `CONFLICT_RESOLVED`
- `DATA_PRUNED`, `DATA_CLEARED`
