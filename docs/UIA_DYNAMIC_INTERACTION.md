# Windows UI Automation (UIA) Dynamic Interaction (Tier C)

> **Module**: `astrarun.ui` / `astrarun.agent`  
> **Status**: APPROVED  
> **Platform**: Windows 11 x64  

---

## 1. Overview

Tier C UI Automation provides access to Windows accessibility trees for desktop applications without relying on brittle screen coordinate clicks.

---

## 2. Interaction Strategy

1. **Target Identification**:
   - Scope traversal using `TreeScope_Descendants`.
   - Matching against `AutomationId`, `ClassName`, or `ControlType`.
2. **Pattern-Based Manipulation**:
   - `ValuePattern`: Programmatic text injection without simulated keystrokes.
   - `InvokePattern`: Direct control activation without pointer movement.
3. **Graceful Degradation to Tier D**:
   - If modern AppX controls (such as Windows 11 Notepad `RichEditD2DPT`) reject `ValuePattern`, the runtime activates the target window, verifies focus, and dispatches Tier D `SendInput`.
4. **Data Protection Invariant**:
   - Interaction testing must never delete, clear, or touch pre-existing user windows or unsaved application recovery state.
