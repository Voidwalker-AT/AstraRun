# Agent Runtime Security Architecture

> **Module**: `astrarun.agent` / `astrarun.security`  
> **Status**: APPROVED  
> **Target**: AstraRun v0.11+  

---

## 1. Security Invariants

1. **Zero Raw Shell Execution**:
   - The agent runtime never constructs raw shell commands or executes `os.system` / `eval`.
   - All capabilities execute through typed Python adapters (`SystemUtilityAdapter`, Win32 C APIs).
2. **Authority Boundary**:
   - Neural and linguistic models propose plans and structure user goals; the deterministic `ActionGate` enforces privilege checks and blocks restricted operations.
3. **Zero Credential Exposure**:
   - Wi-Fi connections use pre-existing Windows profiles. Passwords and secret tokens are never logged or stored.
4. **Data Preservation Mandate**:
   - The runtime strictly protects user session files, unsaved editor tabs, and application state (`%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState`).
