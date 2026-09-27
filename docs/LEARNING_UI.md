# AstraRun Learning & Memory UI Surfaces

> **Document**: `docs/LEARNING_UI.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Status**: APPROVED UI SPECIFICATION  

---

## 1. Overview of Interactive Surfaces

AstraRun v0.8.5 provides two primary PySide6 user interface surfaces for complete transparency, auditability, and control:
1. **`MemoryView`**: The Memory & Learning Inspector window.
2. **`SkillReviewWidget`**: The interactive Skill Approval modal dialog.

---

## 2. MemoryView (Memory & Learning Inspector)

```text
+-----------------------------------------------------------------------------------+
|  [Search learned memories...]                               [Clear All Learning]  |
+------------------------------------------+----------------------------------------+
| [OK] ALIAS: 'code' -> 'code.exe' (0.95)   | Memory Details: ALIAS 'code'           |
| [OK] PREF:  'editor' -> 'code' (0.92)    | Status: ACTIVE | Conf: 0.95 | Sup: 4   |
| [CAND] ALIAS: 'surf' -> 'vivaldi' (0.65) | [Confirm] [Reject] [Delete]            |
| [CONF] ALIAS: 'term' -> 'wt' (0.85)      |----------------------------------------|
| [CONF] ALIAS: 'term' -> 'cmd' (0.82)     | Verifiable Provenance & Evidence:      |
|                                          | #1 [CONFIRMATION_ACCEPTED] Weight: 2.0 |
|                                          |    Task ID: 4a9f81... | Event: ev_1    |
|                                          | #2 [SUCCESSFUL_EXECUTION]  Weight: 1.0 |
|                                          |    Task ID: 8c12e9... | Event: ev_2    |
+------------------------------------------+----------------------------------------+
```

### Features:
- **Search & Filter**: Real-time substring search across all memory keys and values.
- **Color-Coded Status Badges**:
  - Green (`[OK]`): `ACTIVE` facts and confirmed habits.
  - Orange (`[CONF]`): `CONFLICTED` aliases awaiting user disambiguation.
  - Cyan (`[CAND]`): `CANDIDATE` facts accumulating evidence.
  - Gray: `DEPRECATED` or `REJECTED` facts.
- **Detail & Provenance Pane**: Inspects exact historical task IDs, event IDs, timestamps, and weights backing the selected memory.
- **Instant Actions**:
  - **Confirm**: Force-promotes memory to `ACTIVE` with `user_confirmed=True`.
  - **Reject**: Deprecates memory, suppressing it from resolution.
  - **Delete**: Permanently removes memory from SQLite.
  - **Clear All Learning**: Danger-zoned button requiring explicit modal confirmation before wiping learned tables.

---

## 3. SkillReviewWidget (Skill Approval Dialog)

Rendered when `SkillManager` proposes a newly mined workflow candidate:
- **Header**: Skill title and natural language description.
- **Statistics**: Number of observed historical executions, calculated confidence, and maximum step risk.
- **Step List**: Scrollable card list of capability steps, each annotated with arguments, parameter bindings, and risk badges (`[LOW]`, `[MEDIUM]`, `[HIGH]`, `[BLOCKED]`).
- **Decision Controls**:
  - **"Approve & Activate"**: Transitions skill to `ACTIVE`, enabling launcher invocation.
  - **"Reject"**: Suppresses candidate from future proposals.
