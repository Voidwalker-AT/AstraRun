# Structured Result UI — AstraRun v0.7

> **Scope**: Visual presentation cards for informational queries and selectable list results  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. User Interface Design Philosophy

AstraRun is a keyboard-first, native workstation launcher. In v0.6, interactive confirmation (`ConfirmationCard`) and entity disambiguation (`DisambiguationCard`) were introduced.

v0.7 expands the UI card suite to present structured results cleanly without dumping raw JSON or console text into the launcher window:
1. **`ResultCard`**: Compact key-value presentation for single-entity or summary queries (e.g. system health, file metadata, single process status).
2. **`ListResultCard`**: Interactive, keyboard-navigable list presentation for multi-entity queries (e.g. recent files, running processes, open ports).

Both cards adhere strictly to the **Catppuccin Mocha** dark design palette:
- Background: `#181825` (Crust / Mantle)
- Surface: `#1e1e2e` (Base)
- Borders: `#45475a` (Surface1)
- Accent: `#89b4fa` (Blue)
- Primary Text: `#cdd6f4` (Text)
- Subtext: `#a6adc8` (Subtext0)
- Success: `#a6e3a1` (Green)
- Warning: `#f9e2af` (Yellow)
- Danger: `#f38ba8` (Red)

---

## 2. `ResultCard` Component

`ResultCard` displays structured diagnostic summaries.

### Features:
- **Title Header**: Blue bold caption (`self.title_label`).
- **Status Badge**: Optional colored badge indicating health (`self.status_label`, e.g. `[ Optimal ]`, `[ Warning ]`).
- **Key-Value Grid**: Clean 2-column layout pairing labels with values.
- **Action Buttons**: Optional quick-action buttons at the bottom (e.g. `[ Inspect Process ]`, `[ Reveal File ]`) that emit typed capability dispatch signals.

### Example Visual Layout:
```text
+-------------------------------------------------------+
|  System Status                             [ Optimal ]|
|                                                       |
|  CPU Model:   12th Gen Intel Core i5-12450H           |
|  CPU Load:    18.5%                                   |
|  Memory:      11.2 / 15.7 GB (71.3%)                  |
|  GPU:         NVIDIA GeForce RTX 2050 (42°C)          |
|  Battery:     100% (AC Connected)                     |
|                                                       |
|                                    [ Inspect Memory ] |
+-------------------------------------------------------+
```

---

## 3. `ListResultCard` Component

`ListResultCard` displays bounded collections (processes, open ports, recent files).

### Features:
- **Keyboard Navigation**:
  - `Up` / `Down` arrows move selection.
  - `Enter` / `Return` selects the highlighted item and emits `item_selected(dict)`.
  - `Escape` dismisses the card and emits `dismissed()`.
- **Bounded Display**: Respects display limits (5, 10, 20 items) to prevent UI height explosion.
- **Custom Formatting**: Accepts an optional `display_fn` to format complex entity dictionaries into clear monospace lines.

### Example Visual Layout:
```text
+-------------------------------------------------------+
|  Top Processes by Memory (Top 5)                      |
|                                                       |
|  > [14592] Code.exe             1,240 MB  (CPU:  3.2%)|
|    [ 8920] chrome.exe             980 MB  (CPU:  1.1%)|
|    [ 3412] python.exe             420 MB  (CPU: 12.4%)|
|    [ 1204] vivaldi.exe            380 MB  (CPU:  0.8%)|
|    [  890] node.exe               310 MB  (CPU:  0.0%)|
+-------------------------------------------------------+
```
