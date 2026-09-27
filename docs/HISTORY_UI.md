# AstraRun History & Audit UI

## 1. Overview
The History UI (`HistoryView` in `src/astrarun/ui/history.py`) provides an interactive split-view for exploring past tasks, reviewing detailed event timelines, and triggering safe semantic re-runs.

---

## 2. Key Features
- **Split-View Layout**:
  - Left pane: Chronological list of past tasks with title, timestamp, and colored status chips.
  - Right pane (`TaskDetailWidget`): Detailed metadata, execution summary, complete step timeline, and re-run controls.
- **Real-Time Substring Search**:
  - Queries SQLite with parameterized `LIKE %query%` across request text, summary, and capability names.
  - Sub-millisecond response times even across thousands of records.
- **Quick Filter Chips**:
  - `All`: Unfiltered list.
  - `Today`: Tasks created since midnight.
  - `Yesterday`: Tasks created during the previous calendar day.
  - `Completed`: Only successful tasks (`status == 'COMPLETED'`).
  - `Blocked/Failed`: Only interrupted, failed, or security-blocked tasks.
- **Safe Semantic Re-Run**:
  - Clicking "Re-run Task" emits `task_rerun_requested(task_id)`.
  - Dispatches `task_manager.re_run_task(task_id)`, enforcing real-time re-evaluation without stale arguments.
- **Clear History**:
  - Confirmation dialog prompts before executing `ledger.clear_history()`.
