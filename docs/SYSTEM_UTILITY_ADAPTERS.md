# System Utility Adapters (Tier B)

> **Module**: `astrarun.tools.system_adapter`  
> **Status**: APPROVED & VERIFIED  
> **Platform**: Windows 11 x64  

---

## 1. Overview

Tier B adapters provide strictly typed, validated wrappers around standard Windows administrative executables where programmatic Win32 C APIs do not exist.

---

## 2. Invariants & Security Guardrails

1. **`shell=False` Strict Mandate**:
   - `subprocess.run` is invoked exclusively with `shell=False`.
2. **Prohibited Character Filtering**:
   - Arguments are inspected for shell metacharacters (`;`, `&`, `|`, `` ` ``, `$`, `>`, `<`).
3. **Executable Resolution**:
   - Executables are resolved strictly from `%SystemRoot%\System32\` or verified system PATH locations.
4. **Deterministic Exit Code & Output Parsing**:
   - Standard output and standard error are parsed and mapped into typed `CapabilityResult` objects.
