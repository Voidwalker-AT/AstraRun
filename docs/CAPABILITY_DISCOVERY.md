# AstraRun v0.11 Dynamic Capability Discovery

> **Module**: `astrarun.capabilities.registry`  
> **Status**: APPROVED  
> **Target**: AstraRun v0.11+  

---

## 1. Dynamic Discovery Architecture

In AstraRun v0.11, the capability registry exposes 77 registered workstation capabilities as discoverable schemas:
- `registry.get_capability_schema(capability_id)`
- `registry.get_capability_schemas()`

The `GoalPlanner` and future cognitive models query this catalog dynamically rather than relying on hardcoded router tables.

---

## 2. Invariants & Guarantees

1. **Deterministic Dispatch**:
   - Capability execution is strictly checked against the system `ActionGate`.
   - Blocked actions (`risk=BLOCKED` or `permission=BLOCK`) are rejected with `CapabilityErrorCode.BLOCKED`.
2. **Standardized Return Type**:
   - All executions emit a typed `CapabilityResult` containing `success`, `message`, `data`, `latency_ms`, and `context_updates`.
3. **Structured Observation Integration**:
   - Read-only queries automatically write fact observations to the local `ObservationStore` for multi-step reasoning.
