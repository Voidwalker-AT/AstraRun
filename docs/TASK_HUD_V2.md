# Live Task HUD V2 Architecture

> **Module**: `astrarun.ui.hud`  
> **Status**: APPROVED & VERIFIED  
> **Platform**: Windows 11 x64  

---

## 1. Overview

Live Task HUD V2 is a persistent, non-focus-stealing floating indicator positioned in the upper-right corner of the active display.

---

## 2. Key Architectural Invariants

1. **Non-Focus-Stealing Invariant**:
   - Uses `Qt.WindowDoesNotAcceptFocus`, `WA_ShowWithoutActivating`, and Win32 extended style `WS_EX_NOACTIVATE` ($0x08000000$).
   - The HUD never steals keyboard focus from active user applications (VS Code, Notepad, terminal, browser).
2. **Dynamic Task Graph Visualization**:
   - Collapsible/expandable step list (`set_steps`) with real-time status glyphs:
     - `●` PENDING (Gray)
     - `►` RUNNING (Accent Blue)
     - `✓` COMPLETED (Green)
     - `✗` FAILED (Red)
     - `○` CANCELLED (Peach)
3. **Cooperative Cancellation**:
   - User clicking the close/cancel button during active execution emits `cancelled` signal, transitioning task state gracefully without process killing.
