# Centralized Motion System & Tokens

> **Module**: `astrarun.ui.motion`  
> **Status**: APPROVED & VERIFIED  
> **Platform**: Windows 11 x64  

---

## 1. Overview

The `MotionTokens` system centralizes all animation durations and easing curves across AstraRun UI components (Command Bar Launcher, Live Task HUD V2, Action Cards).

---

## 2. Token Definitions

- `ENTER_DURATION_MS = 200`: Entrance duration for launcher and floating cards.
- `EXIT_DURATION_MS = 150`: Exit dismissal duration.
- `EXPAND_DURATION_MS = 220`: Container expansion duration.
- `COLLAPSE_DURATION_MS = 180`: Container collapse duration.
- `STEP_TRANSITION_MS = 120`: Step state transition duration.
- `EASING_ENTER = OutCubic`: Deceleration curve for incoming elements.
- `EASING_EXIT = InCubic`: Acceleration curve for exiting elements.

---

## 3. Windows Reduced-Motion Compliance

AstraRun queries the Windows system accessibility setting via Win32 `SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION)`. If animations are turned off in Windows Settings, all animation durations collapse to $0\,\text{ms}$ instantly.
