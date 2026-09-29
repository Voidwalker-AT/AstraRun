# Windows Battery Report Capability (`generate_battery_report`)

> **Module**: `astrarun.tools.system_adapter`  
> **Status**: APPROVED & VERIFIED  
> **Platform**: Windows 11 x64  

---

## 1. Overview

The `generate_battery_report` capability allows the user to generate a full Windows battery life and health diagnostic report using `powercfg.exe /batteryreport /output "<path>"`.

---

## 2. Capability Metadata

- **Capability ID**: `generate_battery_report`
- **Family**: `SYSTEM_DIAGNOSTICS`
- **Category**: `SYSTEM`
- **Interaction Tier**: `TIER_B_STRUCTURED_CLI`
- **Verifier Strategy**: `VerifierStrategy.FILE_NON_EMPTY`
- **Risk**: `LOW`
- **Side Effect**: `CREATES_FILE`

---

## 3. Path Resolution & Verification

1. **Portable Path Resolution**:
   - If user specifies `Downloads/astra-battery.html` or bare `astra-battery.html`, the adapter resolves the destination portably via `PowerCfgAdapter.get_downloads_directory()`.
2. **Empirical Verification**:
   - Post-execution verification confirms target HTML file exists on disk and has non-zero size (`stat().st_size > 0`).
