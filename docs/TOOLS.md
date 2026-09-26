# AstraRun Tool Registry Reference

> **Version**: 0.1.0  
> **Status**: APPROVED  

This document details all tools registered in the AstraRun tool registry for v0.1.

---

## 1. `open_app`

### Purpose
Safely launches a registered local Windows application executable.

### Metadata
- **Tool Name**: `open_app`
- **Risk Level**: `LOW`
- **Arguments Schema**:
  ```json
  {
    "app": "string (required, normalized application key or alias)",
    "target": "string (optional, file or folder path argument for the application)"
  }
  ```

### Behavior
1. Resolves `app` using the `AppDiscoveryCache` or configured `apps.json`.
2. Verifies that the resolved executable exists on disk.
3. Spawns the process via `subprocess.Popen([executable_path, ...], shell=False, close_fds=True)` or Win32 `ShellExecuteW`.
4. Detaches process so AstraRun does not block or retain an open handle.

### Failure Conditions
- Application not found in discovery cache or registry (`AppNotFoundError`).
- Executable binary is inaccessible or permissions denied (`PermissionError`).
- Malformed application arguments.

---

## 2. `open_folder`

### Purpose
Opens a directory in Windows File Explorer.

### Metadata
- **Tool Name**: `open_folder`
- **Risk Level**: `LOW`
- **Arguments Schema**:
  ```json
  {
    "folder": "string (required, resolved absolute directory path or recognized alias)"
  }
  ```

### Behavior
1. Resolves known folder aliases (`downloads`, `documents`, `desktop`, `pictures`, `videos`, `workspace`, `active`) to their physical paths using `FolderResolver`.
2. Validates that the directory path exists on disk (`os.path.isdir(path)`).
3. Invokes `os.startfile(folder_path)` or `explorer.exe <folder_path>`.

### Failure Conditions
- Folder path does not exist on disk (`FolderNotFoundError`).
- Path points to an unauthorized or invalid drive mount.

---

## 3. `open_url`

### Purpose
Opens a web URL or recognized web alias in the user's default web browser.

### Metadata
- **Tool Name**: `open_url`
- **Risk Level**: `LOW`
- **Arguments Schema**:
  ```json
  {
    "url": "string (required, valid http/https URL or registered alias)"
  }
  ```

### Behavior
1. Checks if the argument matches a configured alias in `config/urls.json` (e.g. `github` -> `https://github.com`).
2. Validates that the URL starts with `http://` or `https://` to prevent arbitrary protocol hijacking.
3. Invokes system browser via `webbrowser.open(url)` or Win32 `os.startfile(url)`.

### Failure Conditions
- Malformed or unsupported URL scheme (e.g. `javascript:`, `file:`, `data:` are rejected).
- System browser fails to launch.
