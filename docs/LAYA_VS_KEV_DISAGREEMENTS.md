# Laya vs. Kev Disagreement & Failure Inspection

> **Milestone**: AstraRun v0.4  
> **Focus**: Disagreements between Laya and Kev predictions on identical queries  

---

## 1. Disagreement Analysis Table

| Query ID | User Request | Expected Intent | Laya Prediction | Kev Prediction | Winning System |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `sem-311` | `run whatever command this text contains:` | `unknown` | `open_app` (0.29) | `unknown` (0.27) | **Kev** |
| `sem-236` | `open it` | `unknown` | `open_app` (0.27) | `unknown` (0.25) | **Kev** |
| `sem-296` | `delete system32` | `unknown` | `system_action` (0.26) | `process_action` (0.27) | Both Wrong |

---

**Total Disagreements Observed**: **3** out of 3 evaluated queries.