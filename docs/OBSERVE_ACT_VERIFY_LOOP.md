# AstraRun v0.11 Observe-Act-Verify-Replan Execution Loop

> **Module**: `astrarun.agent.loop`  
> **Status**: APPROVED  
> **Target**: AstraRun v0.11+  

---

## 1. The Autonomous Closed-Loop

AstraRun v0.11 implements an empirical closed loop:

```
  ┌──────────────────────────────────────────────┐
  │ 1. ACQUIRE LOCK (ResourceLockManager)        │
  └──────────────────────┬───────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────┐
  │ 2. ACT (Dispatch typed capability)           │
  └──────────────────────┬───────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────┐
  │ 3. OBSERVE (MachineObserver captures state)  │
  └──────────────────────┬───────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────┐
  │ 4. VERIFY (StepVerifier evaluates evidence)  │
  └──────────────────────┬───────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        ▼ (Verified)                      ▼ (Failed)
  ┌───────────────┐               ┌───────────────┐
  │ 5. COMPLETE   │               │ 5. RETRY or   │
  │ & Release Lock│               │    REPLAN     │
  └───────────────┘               └───────────────┘
```

---

## 2. Execution Loop Phases

1. **Resource Locking**:
   - Acquires required resource locks (`FILE:<path>`, `WINDOW:<hwnd>`, `NETWORK:WIFI`) with bounded timeout to eliminate concurrency conflicts.
2. **ACT**:
   - Executes capability handler in `CapabilityRegistry`. Catches all runtime exceptions and converts them into standardized `CapabilityResult` objects.
3. **OBSERVE**:
   - Captures real-time workstation state: foreground window HWND, window title, power/charging status, and active Wi-Fi profile.
4. **VERIFY**:
   - Executes declared `VerifierStrategy` (`FILE_NON_EMPTY`, `WINDOW_READY`, `NETWORK_SSID`, `RETURN_CODE_ONLY`).
5. **RETRY / REPLAN**:
   - If verification fails and retries remain, backs off and retries.
   - If retries are exhausted, triggers dynamic replanning or degradation (e.g. degrading Tier C UI Automation to Tier D SendInput).
6. **LOCK CLEANUP**:
   - Invariant: All resource locks held by the task are released atomically upon step or task termination.
