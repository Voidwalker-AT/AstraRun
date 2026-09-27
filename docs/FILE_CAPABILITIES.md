# File Capabilities — AstraRun v0.7

> **Scope**: Bounded file indexing, search, recent files, metadata, and security guardrails  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Subsystem Architecture

The File Capability Subsystem (`src/astrarun/files/service.py` and `src/astrarun/files/index.py`) provides fast, secure access to user documents, assets, and project files.

### Key Capabilities:
- `find_file`: Search files matching wildcard or substring patterns within bounded roots.
- `find_latest_file`: Retrieve the most recently modified file (e.g. screenshots, downloads, notes).
- `list_recent_files`: Enumerate recently modified files across user workspaces.
- `open_file`: Open document files with their registered system handler.
- `reveal_file`: Open Windows File Explorer with the target file highlighted (`/select`).
- `file_metadata`: Inspect file size, created/modified timestamps, extension, and permissions.

---

## 2. Bounded Metadata Indexing

### 2.1 Safe User Roots
AstraRun strictly bounds file operations to explicit user directories:
- `E:\Workspace` (Primary engineering workspace)
- User `Downloads` (`%USERPROFILE%\Downloads`)
- User `Documents` (`%USERPROFILE%\Documents`)
- User `Desktop` (`%USERPROFILE%\Desktop`)
- User `Pictures` (`%USERPROFILE%\Pictures`)

System directories (`C:\Windows`, `C:\Program Files`, `C:\System32`) and heavy build caches (`node_modules`, `.venv`, `.git`, `dist`, `target`) are explicitly excluded from indexing and recursive search.

### 2.2 Symlink & Reparse Point Safety
Windows NTFS directory junctions and symbolic links can create infinite traversal loops or lead into sensitive system partitions.
- AstraRun sets `follow_symlinks=False` on all recursive directory walkers.
- Junction reparse points are identified and pruned from indexing.

---

## 3. High-Value File Discovery

### 3.1 Recent Screenshots
Users frequently ask *"open my latest screenshot"* or *"show me the last picture I took"*.
- `find_latest_file(pattern="screenshot", root="pictures")` searches `Pictures\Screenshots` and the user Desktop for image files (`.png`, `.jpg`).
- Returns the newest matching candidate based on `os.path.getmtime`.

### 3.2 Recent Downloads & Reports
Queries such as *"where is the pdf I just downloaded"* or *"open the report"* resolve to bounded scans across `Downloads` and `Documents` with extension filters (`.pdf`, `.docx`, `.xlsx`, `.md`).

---

## 4. Security Guardrails

### 4.1 Executable Script Open Prohibition (Anti-Drive-By Invariant)
Generic `open_file` invocations can be weaponized if an attacker tricks the launcher into executing a script file.
AstraRun strictly prohibits opening files with the following executable extensions:
- `.bat`, `.cmd` (Batch files)
- `.ps1`, `.psm1` (PowerShell scripts)
- `.vbs`, `.js`, `.wsf` (Windows Script Host)
- `.exe`, `.msi`, `.dll`, `.scr`, `.com` (Binaries and installers)

When a user or query requests opening an executable script:
```python
if ext in BLOCKED_SCRIPT_EXTENSIONS:
    return CapabilityResult.fail(
        capability="open_file",
        message=f"Directly opening executable script '{path}' is blocked for security. Use 'reveal_file' instead.",
        error_code=CapabilityErrorCode.PERMISSION_DENIED,
    )
```

### 4.2 Safe Alternative: `reveal_file`
Instead of executing an untrusted script, AstraRun provides `reveal_file(path=...)`.
This launches Windows File Explorer with the file selected in its directory:
```python
subprocess.Popen(["explorer.exe", f"/select,{os.path.abspath(path)}"])
```
This safely grants the developer full file visibility without triggering automatic code execution.

### 4.3 Path Traversal Defense
Paths containing `..` or attempting to traverse outside permitted user roots are rejected immediately with `CapabilityErrorCode.PERMISSION_DENIED`.
