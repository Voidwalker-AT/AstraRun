# 38 — Dynamic Runtime Sandbox Experiment Protocol (Lab G)

> **Scope**: Phase 17 Lab G Specification  
> **Status**: APPROVED EXPERIMENT PROTOCOL  
> **Focus**: Windows Job Object Process Containment, Memory Ceilings, Tree Termination, ConPTY Streaming, and Secret Redaction  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Experimental Objectives & Falsification Targets

This lab physically verifies the safety primitives that underpin AstraRun's proposed execution sandboxes, ensuring that runaway commands or malicious payloads cannot compromise host memory or leave zombie background processes:

1. **Process-Tree Termination**: Does `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` unconditionally terminate all descendant subprocesses (e.g., Python spawning Node spawning child workers) upon parent exit?
2. **Hard Memory Quota Enforcement**: When a sandboxed script attempts an unconstrained memory allocation exceeding the quota (e.g., allocating 1 GB in a 256 MB Job Object), does Windows abort the process with `STATUS_QUOTA_EXCEEDED` without degrading host system responsiveness?
3. **Interactive ConPTY Streaming**: Does the Windows Pseudo Console (ConPTY) deliver real-time ANSI-rendered terminal streams with bidirectional prompt detection?
4. **Zero-Leak Secret Redaction**: Does the in-memory Aho-Corasick pattern scrubber reliably redact all registered secret tokens from output streams before writing to disk or returning to the engine?

---

## 2. Experimental Test Cases

```mermaid
flowchart TD
    RunLab[Lab G Runtime Test Harness] --> TC1[TC 1: Orphan Process Prevention\nSpawn 3-deep process tree -> Kill root Job]
    RunLab --> TC2[TC 2: Memory Ceiling Quota\nAllocate 1024 MB in 256 MB Sandbox]
    RunLab --> TC3[TC 3: Hard Timeout Enforcement\nInfinite loop script killed at exactly 5.0s]
    RunLab --> TC4[TC 4: ConPTY Streaming & Interruption\nInteractive [y/N] prompt detection]
    RunLab --> TC5[TC 5: Secret Stream Redaction\nInjected secret:// token replaced with ***REDACTED***]
```

### Test Case G-1: Recursive Process Tree Termination
- **Harness Script**: `tests/benchmarks/phase17/fixtures/spawn_tree.py`
  - Spawns a root Python process.
  - Root process spawns a child PowerShell process.
  - PowerShell process spawns a long-running background worker (`ping -t 127.0.0.1`).
- **Action**: Terminate the root Job Object handle.
- **Verification**: Query `psutil` for all three PIDs after 500 ms.
- **Success Criteria**: All three processes terminated; zero orphan processes remaining in Windows Task Manager.

### Test Case G-2: Memory Ceiling & OS Protection
- **Harness Script**: `tests/benchmarks/phase17/fixtures/memory_hog.py`
  - Attempts to allocate a 1024 MB `bytearray` in RAM.
- **Action**: Execute inside a Job Object configured with `JobMemoryLimit = 256 * 1024 * 1024` (256 MB).
- **Verification**:
  - Script is terminated by Windows kernel.
  - Process exit code equals `STATUS_QUOTA_EXCEEDED` (`0xC0000044`).
  - Host free physical RAM remains stable at ~3.30 GB without pagefile thrashing.

### Test Case G-3: Hard Timeout Watchdog
- **Harness Script**: `tests/benchmarks/phase17/fixtures/infinite_loop.py`
- **Action**: Execute with a 5.0-second timeout.
- **Verification**: Process tree terminated at $5000 \pm 100\,\text{ms}$.

### Test Case G-4: ConPTY Streaming & Interactive Prompt Detection
- **Harness Script**: `tests/benchmarks/phase17/fixtures/interactive_prompt.py`
  - Prints 10 lines of progress, prompts `Do you want to continue? [y/N]: `, and waits on stdin.
- **Action**: Execute attached to ConPTY pseudo-console.
- **Verification**:
  - Live lines are captured in real-time streaming buffer.
  - Pattern matcher detects `[y/N]` prompt within 50 ms.
  - Test sends `y\n` to ConPTY input pipe; process completes successfully.

### Test Case G-5: Real-Time Stream Scrubber (Secret Redaction)
- **Harness Script**: `tests/benchmarks/phase17/fixtures/leak_token.py`
  - Prints: `Connecting with key: hf_live_secret_token_123456789 to API.`
- **Action**: Stream output through the Aho-Corasick scrubber configured with `hf_live_secret_token_123456789`.
- **Verification**:
  - Raw stream written to memory/disk contains strictly: `Connecting with key: ***REDACTED*** to API.`
  - Zero occurrences of plaintext secret bytes across logs, return payloads, or exceptions.

---

## 3. Falsification Conditions for Runtime Architecture

1. **Zombie Leakage**: If any child process survives Job Object handle closure, native Windows Job Objects alone are insufficient and require fallback to manual PID-tree tracking via `taskkill /F /T`.
2. **Memory Quota Bypass**: If Python C-extensions or Node processes allocate beyond the Job Object limit without being halted, the sandbox memory defense is falsified.
3. **Scrubber Latency Degradation**: If in-memory stream scrubbing adds $> 2.0\,\text{ms}$ latency per 4 KB chunk, the pattern matching algorithm must be optimized.
