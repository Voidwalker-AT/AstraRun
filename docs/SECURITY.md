# AstraRun Security Specification

> **Version**: 0.1.0  
> **Status**: APPROVED  

---

## 1. Core Security Philosophy

AstraRun is designed from the ground up as an AI-ready workstation control interface. The fundamental architectural tenet is:

> **Natural-language user input must NEVER be directly evaluated as shell code.**

In many naive command bar implementations, user input is passed directly to `os.system()`, `subprocess.Popen(cmd, shell=True)`, or PowerShell `Invoke-Expression`. When AI agents or natural language parsers are layered on top of such architectures, prompt injection, hallucinations, and unescaped characters can result in catastrophic system damage (e.g., unintended file deletion, secret exfiltration, or malicious process execution).

---

## 2. Trust Boundaries

```
[ Unstrusted Input: User Text / Future LLM Response ]
                      │
                      ▼
            [ Router Boundary ]
         (Validates & Canonicalizes)
                      │
                      ▼
         [ Typed Decision (Data Only) ]
                      │
                      ▼
        [ Policy & Tool Registry ]
         (Risk & Argument Checks)
                      │
                      ▼
        [ Controlled OS Handlers ]
     (ShellExecuteW / Argument Lists)
                      │
                      ▼
              [ Windows Host ]
```

1. **User Input Layer**: Untrusted text. May contain shell metacharacters (`&`, `|`, `;`, `>`, `<`, `%`, `$`), unicode tricks, or malformed inputs.
2. **Router Layer**: Produces structured `Decision` objects containing strictly typed arguments. If an input cannot be mapped to a known tool pattern, it is rejected with an explicit `tool="unknown"` decision.
3. **Tool Registry & Policy Layer**: Checks tool permissions, parameter types, and risk levels. Refuses unknown or blocked tools.
4. **Execution Layer**: Dispatches strictly through secure Win32 APIs:
   - `os.startfile(path)` for folders and URLs.
   - `subprocess.Popen(args_list, shell=False)` for applications where an argument list is passed without invoking `cmd.exe` or `powershell.exe`.

---

## 3. Tool Risk Categories

Each tool registered in AstraRun is tagged with an immutable risk category:

| Risk Level | Description | Examples in v0.1 | Execution Policy |
| :--- | :--- | :--- | :--- |
| **LOW** | Idempotent or benign desktop actions that do not destroy data or execute arbitrary code. | `open_app`, `open_folder`, `open_url` | Permitted immediately upon user commit. |
| **MEDIUM** | Actions that modify workspace states, open files in write mode, or run non-standard protocols. | `workspace_build`, `file_edit` (Future) | Permitted in interactive session. |
| **HIGH** | Actions with destructive potential, process termination, or elevated privileges. | `kill_process`, `system_restart` (Future) | Requires explicit secondary user confirmation modal in UI. |
| **BLOCKED** | Direct execution of unconstrained arbitrary commands, shell eval, or pipeline execution. | `raw_shell`, `eval`, `cmd_exec` | **Strictly prohibited and rejected at registry level.** |

---

## 4. Argument Validation & Command Injection Prevention

1. **Applications (`open_app`)**:
   - The requested app name is resolved against the discovered application cache or configured aliases.
   - Arbitrary paths outside known application directories or with dangerous extensions (`.bat`, `.cmd`, `.vbs`, `.ps1` executed with parameters) are not launched through `open_app`.
   - Applications are invoked using their resolved executable path directly with `shell=False`.

2. **Folders (`open_folder`)**:
   - Target paths must be resolved to valid, existing directories on local storage.
   - Path traversal and malicious URI schemes (`file://`, protocol handlers) are validated to ensure only standard folder paths are passed to `os.startfile`.

3. **URLs (`open_url`)**:
   - Target URLs must possess valid `http` or `https` schemes.
   - Configured aliases (e.g. `github -> https://github.com`) are strictly defined in `config/urls.json`.
   - Invoked via default system browser without shell interpolation.

---

## 5. Future AI Risk Model (Laya & Kev Integration)

When Laya (fast classifier) and Kev (semantic router) are introduced:
- Neither model will possess execution capability.
- Models will only emit structured JSON conforming to the `Decision` schema.
- The Tool Registry and Policy Engine will remain the sole gatekeeper.
- If an AI decision suggests an action with risk `>= MEDIUM`, AstraRun will prompt the user with a confirmation badge before execution.
