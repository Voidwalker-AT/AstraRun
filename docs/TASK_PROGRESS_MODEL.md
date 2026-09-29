# Task Progress Model & Honest Progress Modes

> **Module**: `astrarun.agent.models` / `astrarun.ui.hud`  
> **Status**: APPROVED  
> **Target**: AstraRun v0.11+  

---

## 1. Progress Honesty Invariant

AstraRun strictly prohibits fake progress bars or simulated percentage counters. The Live Task HUD V2 models progress strictly through authentic workstation state.

---

## 2. Progress Modes

| Mode | Trigger Condition | Visual Presentation |
| :--- | :--- | :--- |
| `INSTANT` | Operation duration expected $< 100\,\text{ms}$ | Progress bar hidden; instantaneous completion glyph |
| `DETERMINATE` | Measurable multi-step DAG progress | Track bar filled from $0\%$ to $100\%$ according to weighted completed step count |
| `INDETERMINATE` | Unmeasurable duration (e.g. system compilation) | Marquee pulsing bar ("Working...") |
| `EVENT_DRIVEN` | Awaiting external signal (e.g. user confirmation) | Static status badge waiting on event |
