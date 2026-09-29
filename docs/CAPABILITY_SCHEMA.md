# AstraRun v0.11 Capability Schema Specification

> **Module**: `astrarun.capabilities.schema`  
> **Status**: APPROVED  
> **Target**: AstraRun v0.11+  

---

## 1. Machine-Readable Schema Contract

To enable autonomous planning and strict security sandboxing, all capabilities export machine-readable `CapabilitySchema` contracts.

### Schema Fields:
- `id`: Globally unique capability identifier (e.g. `generate_battery_report`, `wifi_scan`).
- `family`: High-level domain family (`SYSTEM_DIAGNOSTICS`, `NETWORK_MANAGEMENT`, `WINDOW_CONTROL`, etc.).
- `category`: Functional subsystem (`SYSTEM`, `NETWORK`, `WINDOW`, `APPLICATION`, `FILE`).
- `interaction_tier`: Interaction surface tier (`TIER_A_NATIVE`, `TIER_B_STRUCTURED_CLI`, `TIER_C_UI_AUTOMATION`, `TIER_D_INPUT_EMULATION`, `TIER_E_VISUAL_FALLBACK`).
- `description`: Human and model-readable capability summary.
- `parameters`: List of typed `ParameterSchema` entries (name, type, description, required, default, pattern).
- `side_effects`: Declared side-effects (`READ_ONLY`, `CREATES_FILE`, `MODIFIES_WINDOW`, `NETWORK_STATE`).
- `privilege_level`: Required user privilege (`STANDARD_USER`, `ELEVATED_ADMIN`).
- `risk`: Security risk evaluation (`LOW`, `MEDIUM`, `HIGH`, `BLOCKED`).
- `reversibility`: Boolean flag indicating whether the action can be undone.
- `verifier_strategy`: Expected verification method (`FILE_NON_EMPTY`, `WINDOW_READY`, `NETWORK_SSID`, etc.).
- `retry_policy`: Configured retry attempts, backoff factors, and timeout.

---

## 2. Parameter Validation

Every capability validates arguments against its parameter schema prior to execution:
- Checks presence of required parameters.
- Validates parameter data types.
- Blocks prohibited characters or malicious path sequences.
