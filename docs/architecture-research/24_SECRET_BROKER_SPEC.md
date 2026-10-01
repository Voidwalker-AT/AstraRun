# 24 — Secret Broker Architecture & Zero-Leak Credential Boundary

> **Status**: APPROVED RESEARCH & ARCHITECTURAL SPECIFICATION  
> **Phase**: 13 — Secret Broker Architecture  
> **Focus**: Opaque Secret URIs, Windows Credential Manager Integration, JIT Process Injection, and Stream Scrubbing  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Executive Summary & Zero-Leak Invariant

A fundamental flaw of many AI coding agents is passing raw API keys, tokens, and database passwords directly through LLM prompts or writing them into plain-text plan DAGs. Once exposed:
1. Keys are sent to external model APIs or cached in local inference KV buffers.
2. Keys are permanently written into task execution logs and terminal transcripts.
3. Git commit actions risk accidentally staging and committing credentials.

AstraRun enforces a **Zero-Leak Invariant**: No raw secret string may ever appear in an LLM prompt, plan DAG step, serialization JSON, or on-disk log file.

```mermaid
flowchart TD
    UserConfig[User Config / Windows Credential Manager] --> Broker[SecretBroker Service\nSecure In-Memory Registry]

    subgraph LLM & Planning Realm (100% Blind to Raw Secrets)
        Planner[Dynamic Goal Planner] --> DAG[Plan DAG Step\nenv: {'HF_TOKEN': 'secret://VAULT/HF_TOKEN'}]
    end

    subgraph Execution Boundary (JIT In-Memory Injection)
        DAG --> Runtime[DynamicExecutionRuntime]
        Runtime -->|Resolve Handle| Broker
        Broker -->|In-Memory Plaintext| Runtime
        Runtime --> Child[Spawn Process with Injected Environment Block]
    end

    subgraph Output Sanitization Realm
        Child -->|stdout / stderr stream| Scrubber[Token Scrubber\nScrub all registered secret patterns]
        Scrubber --> MaskedLog[Sanitized Log: '***REDACTED***']
        MaskedLog --> ReturnToPlanner[Returned to Agent Execution Engine]
    end
```

---

## 2. Opaque Handle Specification

Secrets are referenced exclusively through standardized URI handles:

| URI Scheme | Resolution Target | Example |
| :--- | :--- | :--- |
| `secret://VAULT/<NAME>` | Windows Credential Manager (DPAPI Encrypted) | `secret://VAULT/OPENAI_API_KEY` |
| `secret://ENV/<NAME>` | Filtered Host Process Environment Variable | `secret://ENV/GITHUB_TOKEN` |
| `secret://FILE/<PATH>` | DPAPI-encrypted credential file | `secret://FILE/config/tokens.enc` |

---

## 3. Storage Backends & Windows DPAPI

Raw secrets are never saved in plain JSON or YAML config files.

### 3.1 Windows Credential Manager (`wincred.h`)
- Leverages the Windows OS native credential store (`TargetName: AstraRun:<SECRET_NAME>`).
- Encrypted using the logged-in user's Windows DPAPI (Data Protection API) credentials.
- Inaccessible to other user accounts on the machine.

### 3.2 In-Memory Lifecycle & Hygiene
- Secrets are held in volatile memory only while actively required.
- Strings are backed by pinned memory buffers; upon task completion, buffer contents are explicitly zeroed out (`ctypes.memset`) to prevent lingering in Python garbage collection cycles.

---

## 4. JIT Environment Block Injection

When spawning a sandboxed child process (`Sandbox Tier B` or `Sandbox Tier D`):
1. The planner specifies environment variables using handles:
   ```json
   {
     "capability": "execute_project_command",
     "arguments": {
       "command": "uv run huggingface-cli upload ...",
       "env": {
         "HF_TOKEN": "secret://VAULT/HF_TOKEN"
       }
     }
   }
   ```
2. The runtime queries `SecretBroker.resolve("secret://VAULT/HF_TOKEN")`.
3. The raw string is placed **strictly inside the C-level environment block** passed to `CreateProcessW`:
   ```python
   # Only the spawned subprocess receives the variable in its memory space
   child_env = os.environ.copy()
   child_env["HF_TOKEN"] = resolved_secret
   ```
4. The resolved value is **never** appended to command line arguments (e.g., `--token <RAW_KEY>`), which would expose it in Windows task managers (`tasklist`, Process Explorer).

---

## 5. Bidirectional Stream Scrubbing

Even if a script prints its own environment variables or dumps an error containing a key, the runtime's **Stream Scrubber** guarantees it never enters the log or model context:

1. **Registration**: When `SecretBroker` resolves a secret, its raw byte sequence and common encodings (Base64, URL-encoded) are registered into the active task's scrubber ring.
2. **Streaming Scrubber**: All `stdout` and `stderr` lines pass through an Aho-Corasick multi-pattern scanner before being written to disk or returned to the engine.
3. **Replacement**: Any match is instantly replaced with `***REDACTED***`.

---

## 6. Synthesis & Architectural Invariants

1. **Zero Secret Exposure**: Passing raw credentials in natural language prompts or plan DAG arguments is an instant fatal validation error.
2. **Never in CLI Arguments**: Secrets must only be injected via environment variables, never CLI flag strings visible to system process monitors.
3. **Automatic Stream Masking**: All stdout/stderr streams must pass through token scrubbing before reaching model context or log files.
