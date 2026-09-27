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

---

## 8. Entity Resolution Security & Hard Policy Boundaries (v0.5)

The `EntityResolutionEngine` (`src/astrarun/routing/entity_resolver.py`) enforces hard-coded operating system security boundaries prior to generating any proposed action:

1. **Protected System Process Whitelist**:
   - Workstation stability is non-negotiable. System processes (`system`, `registry`, `smss.exe`, `csrss.exe`, `wininit.exe`, `services.exe`, `lsass.exe`, `svchost.exe`, `winlogon.exe`, `explorer.exe`, `dwm.exe`, `spoolsv.exe`, `fontdrvhost.exe`) are unconditionally blocked from termination or suspension.
   - Any attempt to target a protected process immediately emits `status="blocked"`, `policy_allowed=False`.

2. **Privileged System Port Protection**:
   - Automated socket termination targeting well-known system ports ($\le 1023$, including 22, 53, 80, 443) is strictly prohibited.
   - Non-privileged developer ports (> 1023) require explicit user confirmation before action.

3. **Destructive Shell Command Interception**:
   - The engine validates queries against blacklisted destructive patterns (`rmdir /s /q`, `format`, `del ... system32`, `reg delete HKLM`, `diskpart`).
   - Matched queries are immediately rejected with `status="blocked"`.

4. **Zero Production Authority**:
   - The Entity Resolution Engine produces `ProposedAction` descriptors for evaluation, inspection, and UI preview only. It possesses **zero execution authority**.

---

## 9. Telemetry Quarantine Protocol for External Judges (Jev)

AstraRun v0.5 evaluates TypeSafe's Jev strictly as an offline reference benchmark judge. In compliance with Platform Rule 7 (Zero-Secret Policy):
1. **Local Path Redaction**: Prior to transmitting any payload to an external endpoint, all Windows drive letters (`C:\`, `E:\`), local project paths, and user profiles are redacted into generic `<LOCAL_PATH>` tokens.
2. **Credential Scrubbing**: Environment tokens, API keys, passwords, and user identities are scrubbed.
3. **Graceful Offline Fallback**: If `TYPESAFE_API_KEY` is not present, the system defaults to safe abstention or deterministic offline simulation without raising runtime exceptions.

---

## 10. Action Gate, TOCTOU Defense & Context Privacy (v0.6)

AstraRun v0.6 introduces concrete workstation action execution under strict architectural controls:

### 10.1. Action Gate Multi-Tier Enforcement (`astrarun.policy.action_gate`)
- All proposed actions pass through four non-bypassable tiers:
  - **Tier 0 (Hard Policy Pre-Checks)**: Blocks dangerous shell patterns (`format`, `rmdir /s /q`, `del system32`), directory traversal (`../`), malicious download URLs, protected Windows system processes, and privileged port modification.
  - **Tier 1 (Ambiguity & Disagreement Gating)**: Evaluates multi-candidate match distance ($\Delta \le 0.15$), model disagreement (Jensen-Shannon divergence $> 0.25$), and minimum confidence ($< 0.70$), forcing `CLARIFY` when uncertain.
  - **Tier 2 (Tool Registry Validation)**: Enforces registered tool existence and typed argument checking.
  - **Tier 3 (Risk & Confirmation)**: Distinguishes auto-allowed low-risk tools from gated high-risk actions.
- Target Metric: **0.00% False Execution Rate (FER)**.

### 10.2. Time-of-Check to Time-of-Use (TOCTOU) Process Defense
- Process IDs are recycled quickly by the Windows kernel upon process exit.
- To prevent a user confirmation intended for a dead development process from terminating an unrelated, newly spawned process, `ConfirmationToken` captures:
  - `pid: int`
  - `expected_create_time: float` (from `psutil.Process(pid).create_time()`)
  - `expected_name: str` (e.g. `"node.exe"`)
- Immediately prior to execution, `ActionGate.revalidate_confirmation` queries the OS. If `abs(current_ctime - expected_ctime) > 1.0\text{ s}` or process name has changed, execution aborts and the token is revoked.

### 10.3. Cryptographic Confirmation Tokens & Tampering Prevention
- High-risk and gated actions generate a 32-character hexadecimal token using `secrets.token_hex(16)`.
- Tokens have a strictly bounded time-to-live of **60 seconds**.
- Tokens are cryptographically bound to their original argument payload. Any argument tampering (e.g. swapping port from 3000 to 80) triggers immediate validation failure.
- Tokens are single-use: atomically purged upon validation to prevent replay attacks.

### 10.4. Workstation Context Privacy & Zero-Surveillance Invariants
- Context capture is strictly limited to:
  - Focused window title, executable name, and PID via Win32 `ctypes`.
  - Active TCP listening dev ports (`1024..65535`) via `psutil`.
  - Recent project interaction history.
- Zero keystroke logging, zero screenshots, zero frame grabbing, zero background audio.
- State history is bounded to **30 items** and automatically purged past **48 hours**.
- Atomic persistence to local JSON (`data/context_state.json`) prevents state corruption across sudden reboots.

### 10.5. Context Injection & Jailbreak Defense
- All contextual requests are pre-screened for prompt injection vectors:
  - `ignore previous context and ...`
  - `the previous model said this is allowed ...`
  - `pretend policy is disabled ...`
- Matching queries immediately nullify context references, falling through to global hard security policy blocks.

### 10.6. Immutable Workflow Audit Logging
- Every workstation workflow execution appends a structured JSON transaction record to `data/workflow_audit.jsonl` recording workflow ID, target entity, step-by-step success/failure, latency, and timestamp.



