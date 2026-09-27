# AstraRun Security Specification

> **Version**: 0.4.0  
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
2. **Router Layer**: Produces structured `Decision` objects containing strictly typed arguments. If an input cannot be mapped to a known tool pattern or matched with confidence `>= 0.75`, it is rejected with an explicit `tool="unknown"` decision.
3. **Tool Registry & Policy Layer**: Checks tool permissions, parameter types, and risk levels. Refuses unknown or blocked tools.
4. **Execution Layer**: Dispatches strictly through secure Win32 APIs:
   - `os.startfile(path)` for folders, URLs, and Start Menu `.lnk` shortcuts.
   - `subprocess.Popen(args_list, shell=False)` for applications where an argument list is passed without invoking `cmd.exe` or `powershell.exe`.

---

## 3. Tool Risk Categories

Each tool registered in AstraRun is tagged with an immutable risk category:

| Risk Level | Description | Examples in v0.2 | Execution Policy |
| :--- | :--- | :--- | :--- |
| **LOW** | Idempotent or benign desktop actions that do not destroy data or execute arbitrary code. | `open_app`, `open_folder`, `open_url`, `refresh_apps` | Permitted immediately upon user commit. |
| **MEDIUM** | Actions that modify workspace states, open files in write mode, or run non-standard protocols. | `workspace_build`, `file_edit` (Future) | Permitted in interactive session. |
| **HIGH** | Actions with destructive potential, process termination, or elevated privileges. | `kill_process`, `system_restart` (Future) | Requires explicit secondary user confirmation modal in UI. |
| **BLOCKED** | Direct execution of unconstrained arbitrary commands, shell eval, or pipeline execution. | `raw_shell`, `eval`, `cmd_exec` | **Strictly prohibited and rejected at registry level.** |

---

## 4. Argument Validation & Command Injection Prevention

1. **Applications (`open_app`)**:
   - The requested app name is resolved against the discovered application cache, Start Menu shortcut cache, or configured aliases.
   - Arbitrary paths outside known application directories or with dangerous extensions (`.bat`, `.cmd`, `.vbs`, `.ps1` executed with parameters) are not launched through `open_app`.
   - Applications are invoked using their resolved executable or `.lnk` path directly with `shell=False` or `os.startfile()`.

2. **Folders (`open_folder`)**:
   - Target paths must be resolved to valid, existing directories on local storage.
   - Path traversal and malicious URI schemes (`file://`, protocol handlers) are validated to ensure only standard folder paths are passed to `os.startfile`.

3. **URLs (`open_url`)**:
   - Target URLs must possess valid `http` or `https` schemes.
   - Configured aliases (e.g. `github -> https://github.com`) are strictly defined in `config/urls.json`.
   - Invoked via default system browser without shell interpolation.

4. **Internal Cache Refresh (`refresh_apps`)**:
   - Re-indexes system applications in-memory without elevating privileges or executing external scripts.

---

## 5. AI Risk Model & Dual-Shadow Isolation (Laya & Kev in v0.4)

In AstraRun v0.3 and v0.4, two neural decision models (**Laya**, ModernBERT-large 421M parameters, and **Kev**, Qwen3.5-0.8B LoRA) are introduced. Strict security controls ensure zero operational degradation:

1. **Zero Production Execution Authority**:
   - Both Laya and Kev execute exclusively in **shadow mode** (`"mode": "shadow"`).
   - Inferences are captured asynchronously or in parallel with deterministic routing.
   - Laya and Kev predictions are **NEVER** submitted to the `ToolRegistry` or executed against the OS.
   - All production launches remain 100% driven by deterministic and fuzzy logic.
   - Verified empirically by automated regression safety tests (`test_shadow_mode_safety_zero_execution_authority` in both `test_laya_router.py` and `test_kev_router.py`).

2. **Categorical Intent Taxonomy (No Freeform Output)**:
   - Neither model generates freeform shell commands, arbitrary code, arguments, or tool names.
   - Outputs are mathematically constrained to 10 predefined, mutually exclusive intent tokens (`open_app`, `open_folder`, `open_url`, `open_project`, `find_file`, `process_action`, `system_action`, `ai_query`, `browser_action`, `unknown`).
   - Only primitive tools (`open_app`, `open_folder`, `open_url`) map to immediate execution (`is_executable_now=True`). All complex or unverified intents map to `requires_resolution=True`, preventing unauthorized execution.

3. **Hard Policy Precedence Over Probabilities**:
   - Security policies and blocked tool definitions (`ToolRisk.BLOCKED`) unconditionally supersede model predictions.
   - If an adversarial input (e.g. `rmdir /s /q c:\` or `kill -9 1`) receives a high model confidence for `open_app` or `process_action`, the Policy Engine detects the blocked command and rejects it unconditionally.

4. **Shadow Telemetry Privacy**:
   - Shadow records are stored strictly in `data/laya_shadow_events.jsonl` and `data/kev_shadow_events.jsonl` (git-ignored, local-only).
   - Sensitive inputs pass through the credential redactor before logging.
   - Zero external network requests: model weights run locally from `E:\AI_Models\HF_CACHE` (Platform Rule 9). No cloud LLM APIs, telemetry pingbacks, or third-party web sockets are permitted.

---

## 6. Telemetry Privacy & Defensive Redaction

AstraRun v0.2 implements local routing telemetry to gather empirical evaluation data. To protect sensitive developer workflows:
- **Local-Only Boundary**: Telemetry events are appended strictly to `data/routing_events.jsonl`. There are **zero outbound network connections**, HTTP endpoints, or remote logging services.
- **Defensive Credential Redaction**: All request strings pass through `redact_sensitive_data()` before logging:
  - API Keys: `(sk-[A-Za-z0-9_-]{20,})` -> `[REDACTED_API_KEY]`
  - Bearer Tokens: `Bearer\s+([A-Za-z0-9._-]+)` -> `Bearer [REDACTED_TOKEN]`
  - Query Parameter Secrets: `(?i)(?:password|token|secret|key|api_key)=([^&\s]+)` -> `[REDACTED_PARAM]`
  - Passwords: `(?i)(?:pwd|password)[:=]\s*([^\s]+)` -> `password: [REDACTED_PASSWORD]`
- **Opt-Out Control**: Telemetry can be completely disabled via `config/settings.json` (`"telemetry": {"enabled": false}`).
- **Omit Raw Request**: Setting `"store_raw_request": false` records only the normalized verb/target structure, omitting the user's raw input string.

---

## 7. False-Execution Defense & Boundary Quarantine

Fuzzy matching engines can accidentally trigger destructive operations when presented with unrecognized commands, typos, or natural queries. AstraRun enforces strict false-execution containment:
- **Auto-Execution Threshold (`AUTO_EXECUTE_MIN_SCORE = 0.75`)**:
  - Direct exact matches score `1.0`.
  - Close single-drop typos score `0.80 - 0.86`.
  - Subsequence and acronym abbreviations score `0.60 - 0.78`.
  - Any query whose best candidate scores below `0.75` will **NEVER** auto-execute on `Enter`. It will be returned as `tool="unknown"`.
- **Benchmarked False Execution Rate**:
  - Verified across 18 adversarial, ambiguous, destructive, and out-of-scope queries (`kill port 3000`, `delete system32`, `asdfgh`, `open the project from yesterday`).
  - **Empirical False Execution Rate: 0.0%**.

