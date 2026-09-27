# AstraRun Skill Security & Non-Learnable Policy Invariants

> **Document**: `docs/SKILL_SECURITY.md`  
> **Milestone**: AstraRun v0.8.5 (Memory, Learning & Skill Foundation)  
> **Status**: APPROVED SECURITY SPECIFICATION  

---

## 1. Prime Security Invariant: Zero Learned Policy Weakening

A catastrophic failure mode of self-improving agents is the gradual relaxation of security boundaries (e.g. learning to bypass confirmation prompts because "the user always confirms anyway").

AstraRun enforces the following **hard architectural invariants**:

### 1.1 Non-Learnable Gating Policy
- The `ActionGate` is an immutable, compiled code arbiter.
- Repeating a high-risk capability (e.g. `capability.processes.terminate` or file deletion) 100 times will **never** cause the ActionGate to transition from `CONFIRM` to `AUTO`.
- Every compound skill execution evaluates each individual step against the ActionGate at runtime.

### 1.2 No Arbitrary Code or Shell Infiltration
- A skill can **only** contain references to capabilities registered in `CapabilityRegistry`.
- A skill cannot contain raw shell strings, arbitrary python code snippets, or inline executable scripts.
- Attempts to alias or trigger commands matching `BLOCKED_PATTERNS` (`format c:`, `rmdir /s`, command injection, directory traversal) are rejected at evidence extraction time and runtime.

### 1.3 Protected Process Immunity
The following system critical processes are hardcoded into `PROTECTED_PROCESSES`:
- `system`, `registry`, `smss.exe`, `csrss.exe`, `wininit.exe`, `services.exe`, `lsass.exe`, `svchost.exe`, `winlogon.exe`, `explorer.exe`, `dwm.exe`

It is mathematically and structurally impossible for:
1. An alias to resolve to a protected process.
2. A mined skill to target a protected process.
3. An ActionGate evaluation to allow termination or manipulation of a protected process.

---

## 2. Capability Sandboxing & Gating Table

| Scenario | Evaluated In | Verdict | Security Justification |
| :--- | :--- | :--- | :--- |
| User confirms skill containing `terminate_process` | `SkillStep.requires_confirmation` | `CONFIRM` | Destructive capabilities always require active per-invocation confirmation |
| Pattern miner detects 10 `format c:` queries | `EvidenceExtractor.is_security_safe` | `DISCARD` | Dangerous patterns are rejected before entering database |
| Learned alias points to `lsass.exe` | `AliasManager._is_security_safe` | `BLOCKED` | Protected operating system processes cannot be aliased |
| Unapproved skill executed via trigger | `SkillManager.to_workflow` | `ERROR` | Only `ACTIVE` (human-approved) skills can compile to workflows |
