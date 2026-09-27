# Observation Architecture & Store — AstraRun v0.7

> **Scope**: Structured OS fact observation, in-memory buffering, and sensory state recording  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. The Observation Model

In cognitive agent architectures, an intelligent system requires a clean distinction between:
1. **Sensory Observations**: Deterministic, factual readings of the environment (e.g. *"Process 14592 is using 1.2 GB of RAM"*).
2. **Context**: Ephemeral working memory tracking recency and user focus (e.g. *"The user just inspected process 14592"*).
3. **Reasoning**: Higher-level planning, diagnosis, and inference (e.g. *"Process 14592 appears to have a memory leak; recommend termination"*).

AstraRun v0.7 implements the first layer: the **Observation Subsystem** (`src/astrarun/capabilities/store.py` and `models.py`).

Deep System-2 reasoning is deferred to v0.12. In v0.7, read-only capabilities automatically record structured `Observation` facts into an in-memory buffer without requiring any LLM involvement.

---

## 2. Typed Observation Contract

Every recorded observation adheres to a strict schema:

```python
@dataclass
class Observation:
    id: str                          # Unique UUID
    timestamp: float                 # Unix Epoch Timestamp
    type: str                        # Category fact type (e.g. "system_fact", "process_fact")
    source: str                      # Capability ID that generated observation (e.g. "inspect_port")
    data: dict[str, Any]             # Structured payload
```

---

## 3. `ObservationStore` Implementation

The `ObservationStore` maintains an in-memory, bounded ring buffer of recent workstation facts:

### Key Characteristics:
- **Bounded Buffer**: Default maximum 200 observations (`collections.deque(maxlen=200)`). Prevents unbounded memory growth.
- **In-Memory Zero-Disk Overhead**: No sqlite or disk locks required for ephemeral facts.
- **Thread-Safe**: Safe for concurrent capability dispatch threads.
- **Query APIs**:
  - `record(obs_type, source, data) -> Observation`: Log a new fact.
  - `get_recent(limit=10) -> list[Observation]`: Fetch newest observations.
  - `get_by_type(obs_type, limit=10) -> list[Observation]`: Filter by fact category.
  - `get_latest(obs_type) -> Optional[Observation]`: Retrieve the most recent fact of a given type.
  - `clear() -> None`: Flush memory.

---

## 4. Preparation for Future Reasoning Handoffs (v0.12)

When external reasoning providers (e.g. local LLM or cloud API) are integrated in v0.12:
- The reasoning engine will **not** need to scan the entire operating system on every prompt.
- It will simply query `ObservationStore.get_recent()` and receive a clean, structured JSON bundle of verified OS facts.
- This guarantees that any future reasoning operates on verified ground-truth data, eliminating hallucination about workstation state.
