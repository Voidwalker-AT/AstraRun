---
name: battery_health_report
description: Generate comprehensive battery degradation and cycle report via powercfg.
version: 1.0.0
author: AstraRun Engine
tags: [hardware, battery, power, report]
inputs: [output_format, target_dir, include_history]
platforms: [windows]
---

# Battery Health & Degradation Diagnostic Skill

## Overview
Generates a comprehensive diagnostic report analyzing hardware battery health, wear level, design capacity versus full-charge capacity, and discharge cycle count on Windows workstations.

## When to Use
- When diagnosing power depletion or battery performance degradation.
- When generating hardware inventory audits or device health reports.
- When instructed to inspect battery cycle counts or charge wear level.

## Required Parameters
- `output_format` (string, optional): Format of report: 'json', 'html', or 'summary' (default: 'json').
- `target_dir` (string, optional): Destination directory for generated report (default: current working directory).
- `include_history` (boolean, optional): Whether to parse multi-day usage history records (default: false).

## Procedure
1. Inspect host power subsystem using Windows Power Management APIs.
2. Query hardware battery capabilities and current charge status via `powercfg /batteryreport`.
3. Parse the generated output to extract:
   - Design Capacity (mWh)
   - Full Charge Capacity (mWh)
   - Cycle Count
   - Current Battery Health Percentage: `(Full Charge / Design) * 100`
4. Formulate structured JSON diagnostic artifact containing health metrics.
5. Save artifact to target directory and return machine-readable execution summary.

## Verification Steps
- Verify output file exists on disk and is non-empty.
- Verify health percentage is between 0.0% and 100.0%.
- Ensure exit code 0 on successful generation.

## Error Handling
- If host is a desktop machine without a physical battery, return exit code 1 with status `NO_BATTERY_PRESENT`.
- If powercfg fails to execute due to privilege constraints, return status `INSUFFICIENT_PRIVILEGES`.

