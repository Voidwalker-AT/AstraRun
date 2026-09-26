# AGENTS.md — AstraRun Operating Contract

> **Scope**: `E:\Workspace\Active\AstraRun\`  
> **Parent Contract**: `E:\Workspace\Active\AGENTS.md` -> `E:\Workspace\AGENTS.md`  
> **Role**: Windows Intelligent Command Launcher (v0.1)  
> **Status**: ACTIVE  

---

## 1. Project Invariants & Principles

1. **Security / No Raw Shell Execution**: Never execute raw natural-language user input via `shell=True`, `os.system()`, `eval()`, or `Invoke-Expression`. All interactions must pass through `Request -> Router -> Structured Decision -> Tool Registry -> Executor`.
2. **Deterministic & Extensible**: v0.1 uses deterministic routing without external LLMs. Future models (Laya, Kev, AI Bridge) plug into the router abstraction without rewriting UI or execution layers.
3. **Isolated Python Runtime**: Use only project-local `.venv`. Never install global packages or modify host Python installations.
4. **Desktop Integration & Hotkeys**: Alt+Space is the default hotkey, backed by native Win32 `RegisterHotKey`. Hotkey listener must run asynchronously and be cleanly cancelable.
5. **No Blind Dependency Churn**: Lock/pin dependencies in `requirements.txt`.
6. **Empirical Verification**: Run test suite (`pytest tests/`) and manual UI verification before declaring success.
7. **Windows Portability**: Do not hardcode user profile paths (e.g. `C:\Users\username`); use Windows Known Folders / Registry / standard library APIs.

---

## 2. Testing & Running

- Run unit tests: `.venv\Scripts\pytest tests/`
- Run application: `.venv\Scripts\python src/astrarun/main.py`
