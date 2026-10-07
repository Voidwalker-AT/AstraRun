"""Section 8: Concurrency Ceiling Tests for AstraRun C2.2.

Verifies that SandboxManager bounds concurrent dynamic compute workers strictly to 1.
"""

import threading
import time
from astrarun.sandbox.manager import SandboxManager
from astrarun.sandbox.models import SandboxConfig


def test_sandbox_concurrency_ceiling():
    mgr = SandboxManager()
    
    # 1. Acquire the single worker slot manually
    acquired = mgr._concurrency_lock.acquire(blocking=False)
    assert acquired, "Should acquire free concurrency slot"

    try:
        # 2. An execution attempt while slot is occupied must fail with BUSY when timeout expires
        cfg = SandboxConfig(run_id="test_busy_run", timeout_sec=0.1)
        res = mgr.execute_script("print('should not run')", config=cfg)
        assert res.status == "BUSY"
        assert "concurrency ceiling" in res.stderr.lower()
    finally:
        mgr._concurrency_lock.release()

    # 3. After release, worker execution acquires slot normally
    acquired_after = mgr._concurrency_lock.acquire(blocking=False)
    assert acquired_after
    mgr._concurrency_lock.release()
