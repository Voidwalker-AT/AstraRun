# AstraRun Preference Learning & Default Tools

> **Document**: `docs/PREFERENCE_LEARNING.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Status**: APPROVED PREFERENCE SPECIFICATION  

---

## 1. Scope & Categories

Workstation tasks frequently refer to conceptual functional roles rather than explicit applications:
- `"open my editor"` ➔ Which editor? (VS Code, Cursor, Notepad, Neovim)
- `"open browser"` ➔ Which browser? (Vivaldi, Chrome, Edge, Firefox)
- `"launch terminal"` ➔ Which shell? (Windows Terminal, PowerShell, Git Bash)

AstraRun manages these via the **`PREFERENCE`** namespace in `data/astra_learning.db`.

---

## 2. Preference Extraction & Teaching

### 2.1 Explicit Teaching Statements
Users can explicitly establish preferences using natural language:
- `"my editor is vscode"`
- `"my default browser is vivaldi"`
- `"my terminal is wt"`

These statements are parsed by `EvidenceExtractor.extract_teaching()`, generating a `SemanticMemory` record with:
- `namespace = MemoryNamespace.PREFERENCE`
- `target_type = "preference"`
- `confidence = 1.0`
- `user_confirmed = True`
- `pinned = True`

### 2.2 Implicit Habit Formation
If a user frequently launches Vivaldi whenever they request web-related capabilities, the `EvidenceExtractor` accumulates `CONFIRMATION_ACCEPTED` and `SUCCESSFUL_EXECUTION` events:
- After 3 consistent interactions without contradiction, $C \ge 0.85$, promoting `"browser" = "vivaldi"` to an active preference candidate.

---

## 3. Interaction with OS Default Handlers

- If a preference is active in AstraRun, it guides intent routing for generic verbs ("browse", "edit", "code").
- However, AstraRun **never alters host Windows registry or default app associations** (`HKCU\Software\Microsoft\Windows\Shell\Associations`). Preferences remain strictly internal to AstraRun's routing layer, preserving platform safety.
