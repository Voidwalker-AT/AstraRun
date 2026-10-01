# 23 — Human-in-the-Loop, ActionGate & Non-Blocking HUD Architecture

> **Status**: APPROVED RESEARCH & ARCHITECTURAL SPECIFICATION  
> **Phase**: 12 — Human-in-the-Loop, ActionGate & Permission Taxonomy  
> **Focus**: ActionGate Permission Tiers, Reversible Operations, Undo Journaling, Non-Blocking HUD Interaction Chips, and Task Parking  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Executive Summary & Core Philosophy

An autonomous agent operating on a physical workstation cannot adopt a binary security model (either completely manual approval for every command, or unchecked root execution).
- **Excessive Prompts**: Asking the user to approve `Get-Date` or `git status` creates prompt fatigue, leading users to blindly accept all prompts.
- **Unchecked Execution**: Permitting arbitrary shell commands risks data destruction, broken lockfiles, or process killing.

AstraRun implements a **4-Tier ActionGate** paired with an **Undo Journal** and a **Non-Blocking HUD**, providing frictionless velocity for safe tasks while enforcing strict gates on irreversible operations.

```mermaid
flowchart TD
    Action[Proposed Action Step] --> Gate[ActionGate Evaluation]

    Gate -->|Tier 1: Read-Only| T1[Tier 1: SAFE_READ\nAuto-Approved | Zero Prompt]
    Gate -->|Tier 2: Project Mutation| T2[Tier 2: REVERSIBLE_MUTATION\nAuto-Approved in Workspace\nUndo Journal Entry Recorded]
    Gate -->|Tier 3: Destructive| T3[Tier 3: IRREVERSIBLE_MUTATION\nNon-Blocking HUD Prompt Required\nPause task if no response]
    Gate -->|Tier 4: Privileged| T4[Tier 4: SYSTEM_ELEVATION\nModal Confirmation + UAC Check]

    T1 --> Exec[Execute in Sandbox]
    T2 --> Exec
    T3 -->|User Approved| Exec
    T3 -->|User Rejected| Replan[Replan or Cancel]
    T4 -->|User Approved| Exec
```

---

## 2. ActionGate Permission Taxonomy

| Tier | Category | Example Actions | Execution Policy | Reversibility Guarantee |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | `SAFE_READ` | `git status`, `Get-NetAdapter`, `powercfg /batteryreport`, read files | **Immediate Auto-Approval** | Zero host mutation |
| **Tier 2** | `REVERSIBLE_MUTATION` | Write new file in project, run build, move file to Windows Recycle Bin | **Auto-Approved within Workspace** | Logged to **Undo Journal** |
| **Tier 3** | `IRREVERSIBLE_MUTATION` | Permanent delete (`rm -rf`), `git reset --hard`, terminate foreign PID | **HUD User Approval Required** | Cannot be automatically undone |
| **Tier 4** | `SYSTEM_ELEVATION` | `winget install`, registry modification, firewall rule creation | **Explicit Modal Dialog Required** | System-wide impact |

---

## 3. Reversibility & The Undo Journal

`[USER_REQUIREMENT]` Mutations within approved project workspaces should prioritize reversibility:
1. **Recycle Bin Over Unlink**:
   - AstraRun never executes raw unlinks (`os.remove` / `Remove-Item -Force`) for user documents.
   - Deletions are routed through the Windows Shell Recycle Bin API (`SHFileOperation` / `FO_DELETE` with `FOF_ALLOWUNDO`).
2. **Git Auto-Stash / Working Tree Snapshots**:
   - Before applying automated code refactors, Astra records a Git reference point (`git stash create` or lightweight tag).
   - If verification fails, Astra can restore the exact working tree state in one step.
3. **Undo Journal (`.astrarun/undo_journal.jsonl`)**:
   - Records every file write, move, or rename with pre-mutation content hashes.
   - User can run `astrarun undo` to roll back the latest automated task.

---

## 4. Non-Blocking Floating HUD & Multi-Task Chips

`[USER_REQUIREMENT]` The user interface must never freeze or steal keyboard focus while waiting for confirmation.

```
+-------------------------------------------------------------+
|  ✦ AstraRun Active                                          |
|  [● Task 1: Audit repos]  [⏳ Task 2: Port 8080 Confirmed?] |
+-------------------------------------------------------------+
```

### 4.1 Non-Blocking Task Parking
- When a task requires Tier 3 confirmation (e.g., terminating process 8080):
  - Astra issues an interactive notification chip on the HUD:
    ```
    ✦ Task #2 requires confirmation:
      Terminate process python.exe (PID 9182) holding port 8080?
      [Approve]  [Reject]  [Details]
    ```
  - **Task State**: Transitions to `PAUSED_AWAITING_INPUT`.
  - **Engine Behavior**: The engine does **not** block. Task #1 and Task #3 continue executing concurrently.
  - **Timeout Rule**: If no user response is received within **120 seconds**, the task is parked indefinitely in the background queue. It never aborts destructively or assumes permission.

### 4.2 Focus Preservation Invariant
- The HUD is rendered as a non-activatable top-level window (`WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`).
- Clicking HUD interaction chips does **not** steal keyboard focus from the user's active coding editor or terminal.

---

## 5. Synthesis & Architectural Invariants

1. **Zero Prompts for Safe Reads**: Reading files and querying read-only system APIs must never prompt the user.
2. **Mandatory Recycle Bin for File Removal**: Destructive file deletion without recycle bin buffering is strictly banned.
3. **Non-Blocking Task Concurrency**: Waiting for human confirmation must never block independent parallel tasks.
4. **No Focus Snatching**: The HUD must strictly maintain `WS_EX_NOACTIVATE` window styling.
