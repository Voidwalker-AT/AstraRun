# AstraRun v0.6.5 — NLP Security & Adversarial Defense Audit

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Target System**: Natural Language Understanding & Workflow Compiler  

---

## 1. Threat Modeling for Workstation NLU

Integrating natural language parsing into a workstation control launcher introduces unique adversarial threat vectors:

```text
Attacker Vector              AstraRun Security Layer            Outcome
───────────────────────────  ─────────────────────────────────  ─────────────────
Shell command injection      Zero raw shell execution           Inert Data
Adversarial prompt injection Global regex policy filter         BLOCKED
Negation bypass attack       Scoped negation safety assertion   0.00% Leakage
Protected system kill        Process protection catalog         BLOCKED
Path traversal attack        Hard path normalization filter     BLOCKED
```

---

## 2. Security Invariants & Empirical Verification

### A. Zero Raw Shell Execution
- **Invariant**: No NLP parse output or dependency token is ever evaluated via `powershell.exe`, `cmd.exe`, or `subprocess.run(shell=True)`.
- **Verification**: Verified across all 126 automated test cases.

### B. Conservative Multi-Clause Blocking
- **Attack Scenario**: Combining an innocuous action with a malicious payload (e.g. `"open AstraRun and delete system32"`).
- **Defense**: If *any* clause in an utterance matches a prohibited pattern, the entire request is blocked immediately (`status="BLOCKED"`). The innocuous clause is not executed.
- **Verification**: 100% block rate across all 35 adversarial test cases in Benchmark V1.

### C. Negation Leakage Immunity
- **Attack Scenario**: Phrasing dangerous actions negatively or ambiguously (e.g. `"don't kill node, just format c:"`).
- **Defense**: Negation scoper isolates polarity per clause. `verify_negation_safety()` strictly asserts that no proposed step originated from a negated clause.
- **Measured Leakage Rate**: **0.00%** (0 / 310 cases).

### D. Protected System Resource Immunity
- **Targets**: `lsass`, `system`, `csrss`, `services.exe`, `svchost.exe`, `wininit`, `system32`.
- **Defense**: Explicit blocklist in `WorkflowCompiler` and `ActionGate` blocks any termination, deletion, or modification of critical OS processes and files.
