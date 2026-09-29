# Task ETA Estimation Engine (`TaskETAEstimator`)

> **Module**: `astrarun.ui.hud`  
> **Status**: APPROVED & VERIFIED  
> **Target**: AstraRun v0.11+  

---

## 1. Overview

The `TaskETAEstimator` computes remaining execution time for multi-step tasks based on measured step execution times.

---

## 2. Estimation Algorithm

1. **Step Timing**:
   - `record_step_start(step_id)`: Records $t_{\text{start}}$ when step enters `RUNNING`.
   - `record_step_end(step_id)`: Computes step duration $d_i = t_{\text{end}} - t_{\text{start}}$ and stores in `completed_durations`.
2. **Remaining Estimation**:
   $$\text{Remaining Steps} = N_{\text{total}} - N_{\text{completed}}$$
   $$\text{Avg Duration} = \frac{1}{k} \sum_{i=1}^{k} d_i$$
   $$\text{ETA} = \text{Avg Duration} \times \text{Remaining Steps}$$
3. **Format Ergonomics**:
   - Displays as `~1.5s`, `~12.0s`, or `~1m 30s`.
   - Suppresses ETA display when completed steps $< 1$ or remaining steps $= 0$.
