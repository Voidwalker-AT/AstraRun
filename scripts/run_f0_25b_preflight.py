"""F0-25B Pre-flight Freeze and Regression Suite Runner.

Records:
- git branch, HEAD commit, git status
- production tree SHA-256
- model GGUF file SHA-256
- Hermes schema/version
- Computer Use architecture version
- Executes regression/oracle suites
- Emits docs/audit/F0_25B_PREFLIGHT.json
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def compute_production_tree_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "src" / "astrarun").rglob("*.py")):
        h.update(str(p.as_posix()).encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest().lower()


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def run_preflight() -> dict:
    # 1. Git branch and HEAD
    branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    status_out = subprocess.check_output(["git", "status", "--short"], text=True).strip()
    status_lines = [l.strip() for l in status_out.splitlines() if l.strip()]

    # 2. Production tree hash
    prod_sha256 = compute_production_tree_sha256()

    # 3. Model GGUF hash
    model_path = Path(r"E:\AI_Models\GGUF\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
    assert model_path.exists(), f"Model file not found: {model_path}"
    model_sha256 = compute_file_sha256(model_path)

    # 4. Run full regression test suite
    test_cmd = [
        str(ROOT / ".venv" / "Scripts" / "pytest"),
        "tests/hermes/test_f0_25a3_causal_mutations.py",
        "tests/hermes/test_hermes_experiential_memory.py",
        "tests/eval_v1/test_f0_24a1_adversarial_oracle.py",
        "tests/eval_v1/test_f0_24a1_oracle_mutations.py",
        "-q",
    ]
    t0 = time.time()
    proc = subprocess.run(test_cmd, cwd=str(ROOT), capture_output=True, text=True)
    duration = time.time() - t0
    tests_passed = proc.returncode == 0
    test_output = proc.stdout.strip() or proc.stderr.strip()

    preflight = {
        "phase": "F0-25B",
        "title": "Pre-Flight Freeze & Verification",
        "timestamp": time.time(),
        "git": {
            "branch": branch,
            "head": head,
            "status_entry_count": len(status_lines),
            "status_summary": status_lines[:15],
        },
        "hashes": {
            "production_tree_sha256": prod_sha256,
            "model_path": str(model_path),
            "model_id": "qwen2.5-coder-1.5b-instruct-q4_k_m",
            "model_sha256": model_sha256,
            "model_size_bytes": model_path.stat().st_size,
        },
        "schemas": {
            "hermes_schema_version": "1.0.0-f025",
            "computer_use_architecture": "F0-25A.3R",
            "causal_resource_model": "CausalProvenance + Ownership-Relative Restoration",
        },
        "regression_results": {
            "command": " ".join(test_cmd),
            "exit_code": proc.returncode,
            "passed": tests_passed,
            "duration_seconds": round(duration, 2),
            "output": test_output,
        },
        "preflight_status": "PASS" if tests_passed else "FAIL",
    }

    out_file = ROOT / "docs" / "audit" / "F0_25B_PREFLIGHT.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(preflight, f, indent=2)

    print(f"Preflight status: {preflight['preflight_status']}")
    print(f"Wrote {out_file}")
    return preflight


if __name__ == "__main__":
    run_preflight()
