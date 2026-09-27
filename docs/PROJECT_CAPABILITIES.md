# Project Capabilities — AstraRun v0.7

> **Scope**: Workspace project inspection, Git telemetry, process isolation, and IDE launching  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Subsystem Architecture

The Project Capability Subsystem (`src/astrarun/projects/service.py`) bridges AstraRun with developer repositories registered in `ProjectRegistry` and the global `workspace.json`.

### Key Capabilities:
- `project_status`: Unified inspection of a project (path, category, git status, running processes, bound ports).
- `project_git_status`: Query active branch, count of modified files, and untracked files.
- `project_running_processes`: Detect running processes whose working directory or script path originates inside the project root.
- `project_ports`: Detect network ports bound by processes executing within the project directory.
- `open_project_folder`: Open the repository directory in Windows File Explorer.
- `open_project_in_vscode`: Launch the project workspace in Visual Studio Code (`code <path>`).

---

## 2. Secure Git Telemetry

Many developer tools query git status by running shell commands like `os.system("git status")` or interpolating branch names into bash scripts.

### 2.1 Structured Subprocess Execution
AstraRun queries git status strictly through structured argument lists with `shell=False`:
1. **Branch Detection**:
   ```python
   subprocess.run(["git", "branch", "--show-current"], cwd=project_path, capture_output=True, text=True)
   ```
2. **Porcelain Status Inspection**:
   ```python
   subprocess.run(["git", "status", "--porcelain"], cwd=project_path, capture_output=True, text=True)
   ```
3. **Structured Parsing**:
   - Lines starting with ` M ` or `M ` denote modified files.
   - Lines starting with `??` denote untracked files.
   - Outputs a typed `GitStatus` dataclass:
     ```python
     GitStatus(branch="main", is_dirty=True, modified_count=3, untracked_count=1)
     ```

### 2.2 Security Guarantees
- Zero shell interpolation prevents command injection via malicious branch names or file paths.
- Execution is strictly read-only; Git mutations (`commit`, `push`, `rebase`, `reset`) are never performed.

---

## 3. Project Process & Port Isolation

Developers frequently ask:
- *"Is AstraRun running right now?"*
- *"What port is my server on?"*
- *"Stop the local server running in this project"*

AstraRun links processes and ports directly to project paths:
1. **Process Discovery**: Iterates running processes and inspects their Current Working Directory (`proc.cwd()`). If `proc.cwd()` is within `project.path`, the process is attributed to the project.
2. **Port Mapping**: For every process belonging to the project, AstraRun queries `proc.net_connections()`.
3. **Structured Output**: Emits a combined map of project health, active dev servers, and listening ports in under 5 ms.
