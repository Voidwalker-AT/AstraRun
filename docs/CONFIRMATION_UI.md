# Confirmation & Disambiguation UI Specification (AstraRun v0.6)

> **Status**: PRODUCTION READY  
> **Package**: `astrarun.ui.cards`  
> **Last Verified**: 2026-09-27  

---

## 1. Overview & Safety-First Interaction Philosophy

In a high-speed command launcher, keyboard shortcuts can be executed faster than human cognitive verification. A stray `Enter` key must **never** be permitted to destroy workstation processes or execute high-risk operations.

AstraRun v0.6 implements two specialized, keyboard-safe UI components built on PySide6:
1. **`ConfirmationCard`**: An interactive safety modal rendered when an action requires explicit human confirmation (`terminate_process`, `system:shutdown`).
2. **`DisambiguationCard`**: An interactive selection card rendered when an entity or project query matches multiple close candidates ($\Delta \le 0.15$).

---

## 2. `ConfirmationCard` Specification

```
┌─────────────────────────────────────────────────────────────┐
│  Confirm Process Termination                   [ HIGH RISK ]│
│                                                             │
│  Terminate process 'node.exe' (PID: 14236)?                 │
│  Expected Create Time: 2026-09-27 16:45:32                  │
│                                                             │
│  [ Cancel (Esc) ]                  [ Proceed (Ctrl+Enter) ] │
└─────────────────────────────────────────────────────────────┘
```

### Safety & Keybinding Invariants
- **Escape Key (`Esc`)**: Immediately cancels the confirmation, revokes the confirmation token, and dismisses the launcher.
- **Single Enter Suppression for High Risk**: For actions classified as `ToolRisk.HIGH`, pressing `Enter` alone is **strictly ignored**. This prevents accidental muscle-memory keystroke execution when typing rapidly.
- **Explicit Confirmation Keybinding (`Ctrl+Enter`)**: The user must explicitly press `Ctrl+Enter` or click the `[Proceed]` button to execute.
- **Risk Badge Styling**:
  - `HIGH`: Crimson background (`#f38ba8`) with dark text (`#11111b`).
  - `MEDIUM`: Yellow-gold background (`#f9e2af`).
  - `LOW`: Emerald background (`#a6e3a1`).
- **Qt Signals**:
  - `confirmed(str, str, dict)`: Emitted with `(token, tool, arguments)`.
  - `cancelled()`: Emitted when dismissed.

---

## 3. `DisambiguationCard` Specification

```
┌─────────────────────────────────────────────────────────────┐
│  Which project did you mean?                                │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ > 1. AstraRun — Active/AstraRun                       │  │
│  │   2. AI Bridge — Active/AI-Bridge                     │  │
│  │   3. Vivaldi AI — Active/vivaldi-ai                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Use Up/Down arrows to navigate, Enter to select, Esc to exit│
└─────────────────────────────────────────────────────────────┘
```

### Navigation & Keybinding Invariants
- **Arrow Key Delegation**: Up and Down arrow keypresses update the highlighted item in `QListWidget` smoothly.
- **Enter Key (`Enter` / `Return`)**: Selects the currently highlighted candidate and feeds its metadata directly back into the `EntityResolutionEngine`.
- **Escape Key (`Esc`)**: Cancels disambiguation and dismisses the card.
- **Mouse / Click Activation**: Double-clicking or clicking any row immediately triggers selection.
- **Qt Signals**:
  - `candidate_selected(dict)`: Emitted with the full candidate dictionary payload.
  - `cancelled()`: Emitted when dismissed without selection.

---

## 4. Verification & Test Evidence

Verified in `tests/test_v06_actions.py`:
- `test_ui_confirmation_card`:
  - Confirms `Esc` emits `cancelled`.
  - Confirms single `Enter` on `ToolRisk.HIGH` does NOT confirm.
  - Confirms `Ctrl+Enter` emits `confirmed(token, tool, arguments)`.
- `test_ui_disambiguation_card`:
  - Confirms Down arrow key navigates to the next candidate.
  - Confirms `Enter` emits `candidate_selected` with the chosen entity payload.
