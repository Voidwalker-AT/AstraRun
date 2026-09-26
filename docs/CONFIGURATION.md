# AstraRun Configuration Guide

> **Version**: 0.2.0  
> **Location**: `config/`  

AstraRun is configured via human-readable JSON files in the `config/` directory. No code modifications are required to add custom applications, aliases, URLs, or adjust keyboard shortcuts.

---

## 1. `config/settings.json`

Global runtime settings, hotkeys, UI preferences, telemetry options, and logging options.

```json
{
  "hotkey": {
    "modifiers": ["Alt"],
    "key": "Space"
  },
  "ui": {
    "width": 640,
    "height": 56,
    "theme": "dark",
    "placeholder": "What do you want to do?",
    "hide_on_focus_loss": true,
    "opacity": 0.98,
    "max_suggestions": 5
  },
  "telemetry": {
    "enabled": true,
    "file": "data/routing_events.jsonl",
    "store_raw_request": true
  },
  "logging": {
    "level": "INFO",
    "file": "logs/astrarun.log",
    "max_bytes": 10485760,
    "backup_count": 3
  }
}
```

### Hotkey Options
- **`modifiers`**: List of modifier keys. Supported: `"Alt"`, `"Ctrl"`, `"Shift"`, `"Win"`.
- **`key`**: Activation key. Default is `"Space"`. Can be any letter (`"A"`-`"Z"`), number (`"0"`-`"9"`), or key name (`"Space"`, `"F1"`-`"F12"`).

### UI Options
- **`width`**: Horizontal width of launcher window in pixels (default: `640`).
- **`height`**: Base height of single-line input bar in pixels (default: `56`).
- **`theme`**: Color palette (`"dark"`).
- **`placeholder`**: Placeholder text in input line.
- **`hide_on_focus_loss`**: Whether to automatically dismiss the window if user clicks elsewhere.
- **`opacity`**: Window opacity from `0.1` to `1.0` (default: `0.98`).
- **`max_suggestions`**: Maximum number of ranked suggestion rows to display beneath input (default: `5`).

### Telemetry Options
- **`enabled`**: Whether to log local routing events to disk (default: `true`).
- **`file`**: Path to local append-only JSONL event file (default: `"data/routing_events.jsonl"`).
- **`store_raw_request`**: If `false`, omits the raw query text and records only verb and target structures (default: `true`). All requests undergo regex-based credential redaction before persistence.


---

## 2. `config/apps.json`

Defines explicit application definitions, paths, and default launch arguments. These augment or override applications discovered automatically via Windows App Paths and PATH.

```json
{
  "notepad": {
    "name": "Notepad",
    "path": "C:\\Windows\\System32\\notepad.exe",
    "description": "Windows Text Editor"
  },
  "calc": {
    "name": "Calculator",
    "path": "C:\\Windows\\System32\\calc.exe",
    "description": "Windows Calculator"
  },
  "code": {
    "name": "Visual Studio Code",
    "path": "C:\\Users\\hp\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
    "description": "VS Code Editor"
  },
  "vivaldi": {
    "name": "Vivaldi Browser",
    "path": "E:\\vivaldi\\Application\\vivaldi.exe",
    "description": "Vivaldi Web Browser"
  }
}
```

---

## 3. `config/aliases.json`

Maps natural-language synonyms and abbreviations to target applications or folder names.

```json
{
  "calculator": "calc",
  "editor": "notepad",
  "text": "notepad",
  "vscode": "code",
  "vs code": "code",
  "browser": "vivaldi",
  "terminal": "wt",
  "powershell": "pwsh",
  "cmd": "cmd",
  "explorer": "explorer"
}
```

---

## 4. `config/urls.json`

Maps web shorthand aliases to complete HTTP/HTTPS URLs.

```json
{
  "github": "https://github.com",
  "youtube": "https://youtube.com",
  "google": "https://google.com",
  "reddit": "https://reddit.com",
  "duckduckgo": "https://duckduckgo.com"
}
```
