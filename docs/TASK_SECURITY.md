# AstraRun Task Runtime Security & Invariant Enforcement

## 1. Absolute Security Boundaries

AstraRun v0.8 strictly upholds the following workstation security invariants:

1. **Zero Shell Execution**:
   - `TaskManager`, `TaskLedger`, and `TaskEventBus` contain zero instances of `subprocess.Popen(shell=True)`, `os.system()`, `cmd.exe`, or `powershell.exe`.
   - All capabilities execute strictly through typed, vetted Python APIs.

2. **100% Parameterized SQLite Queries**:
   - Zero dynamic SQL string concatenation.
   - All parameters in `TaskLedger` use `?` placeholders, preventing SQL injection attacks even when requests contain malicious payloads like `'; DROP TABLE tasks; --`.

3. **Stored XSS & Injection Defense in UI**:
   - Historical task summaries and requests are rendered into native Qt widgets (`QLabel.setText()`), ensuring raw HTML/script strings like `<script>alert('xss')</script>` are treated purely as literal text rather than executable markup.

4. **Zero Neural Execution Authority**:
   - No neural model has permission to alter database records, bypass the ActionGate, or execute workstation tools directly.
   - The `ReasoningProvider` interface remains strictly unconfigured.

5. **Semantic Re-Run Safety**:
   - Historical re-runs strictly instantiate **new** tasks using the original semantic request text.
   - Replaying stale PIDs, outdated port numbers, or old file paths is architecturally impossible.
