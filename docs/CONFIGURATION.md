# AstraRun Configuration Guide

> **Version**: 0.1.0  
> **Location**: `config/`  

AstraRun is configured via human-readable JSON files in the `config/` directory. No code modifications are required to add custom applications, aliases, URLs, or adjust keyboard shortcuts.

---

## 1. `config/settings.json`

Global runtime settings, hotkeys, UI preferences, and logging options.

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
    "opacity": 0.98
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
