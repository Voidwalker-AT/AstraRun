# Workstation Resource Locking Engine

> **Module**: `astrarun.agent.locking`  
> **Status**: APPROVED & VERIFIED  
> **Target**: AstraRun v0.11+  

---

## 1. Concurrency Challenges on Local Workstations

Unlike stateless serverless agents, a local workstation agent interacts with physical shared state:
- Multiple tasks typing into the same active window cause character interleaving.
- Simultaneous Wi-Fi connect/disconnect commands corrupt network adapter state.
- Concurrent file writes create corrupted output or race conditions.

---

## 2. ResourceLockManager Architecture

`ResourceLockManager` enforces granular mutual exclusion across workstation domains:
- `WINDOW:<hwnd>`: Locks a specific window during UI interaction or typing.
- `FILE:<canonical_path>`: Locks target files during generation or modification.
- `NETWORK:WIFI`: Locks the 802.11 wireless adapter during profile connection.
- `PROCESS:<pid>`: Locks process handle during termination or inspection.

### Features:
- **Re-entrant Acquisition**: The same task can re-acquire locks recursively across child steps without deadlock.
- **Mutual Exclusion**: Other tasks attempting to acquire the lock are blocked until release or timeout.
- **Fail-Safe Cleanup**: `release_all_for_task(task_id)` ensures all held locks are cleaned up if a task terminates or fails.
