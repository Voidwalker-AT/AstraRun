"""
scripts/generate_f0_23_freezes.py

Generates:
1. docs/audit/F0_23_SOURCE_FREEZE.json (SHA-256 of all production source files in src/astrarun/)
2. docs/audit/F0_23_HARNESS_FREEZE.json (SHA-256 of test harnesses and verification scripts)
3. docs/audit/F0_23_HOLDOUT_MANIFEST.json (Independent physical holdout matrix)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")
SRC_DIR = REPO_ROOT / "src" / "astrarun"
TESTS_DIR = REPO_ROOT / "tests"
SCRIPTS_DIR = REPO_ROOT / "scripts"
AUDIT_DIR = REPO_ROOT / "docs" / "audit"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def get_git_info() -> Dict[str, str]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
        status = subprocess.check_output(["git", "status", "-s"], cwd=REPO_ROOT, text=True).strip()
        return {"commit": commit, "status_summary": f"{len(status.splitlines())} modified/untracked files"}
    except Exception:
        return {"commit": "unknown", "status_summary": "git_unavailable"}


def main() -> None:
    git_info = get_git_info()
    ts = datetime.now(timezone.utc).isoformat()

    # 1. Source Freeze
    src_hashes = {}
    for p in sorted(SRC_DIR.rglob("*.py")):
        rel = str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        src_hashes[rel] = sha256_file(p)

    source_freeze = {
        "timestamp": ts,
        "phase": "F0-23",
        "freeze_type": "SOURCE_FREEZE",
        "description": "Cryptographic freeze manifest of all production source files in src/astrarun/. After this freeze, NO production file may change.",
        "git_commit": git_info["commit"],
        "total_source_files": len(src_hashes),
        "source_files": src_hashes,
    }

    with open(AUDIT_DIR / "F0_23_SOURCE_FREEZE.json", "w", encoding="utf-8") as f:
        json.dump(source_freeze, f, indent=2)
    print(f"Generated {AUDIT_DIR / 'F0_23_SOURCE_FREEZE.json'} ({len(src_hashes)} files)")

    # 2. Harness Freeze
    harness_hashes = {}
    for p in sorted(TESTS_DIR.rglob("*.py")):
        rel = str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        harness_hashes[rel] = sha256_file(p)

    for p in sorted(SCRIPTS_DIR.glob("*f0_23*.py")):
        rel = str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        harness_hashes[rel] = sha256_file(p)

    harness_freeze = {
        "timestamp": ts,
        "phase": "F0-23",
        "freeze_type": "HARNESS_FREEZE",
        "description": "Cryptographic freeze manifest of all evaluation test harnesses and oracle suites. After this freeze, NO test harness file may change.",
        "git_commit": git_info["commit"],
        "total_harness_files": len(harness_hashes),
        "harness_files": harness_hashes,
    }

    with open(AUDIT_DIR / "F0_23_HARNESS_FREEZE.json", "w", encoding="utf-8") as f:
        json.dump(harness_freeze, f, indent=2)
    print(f"Generated {AUDIT_DIR / 'F0_23_HARNESS_FREEZE.json'} ({len(harness_hashes)} files)")

    # 3. Holdout Manifest
    holdout_manifest = {
        "timestamp": ts,
        "phase": "F0-23",
        "freeze_type": "HOLDOUT_MANIFEST",
        "description": "Independent physical holdout verification matrix to be executed exclusively against the frozen installed executable.",
        "cases": [
            {
                "case_id": "FROZEN-01-CALC_LAUNCH",
                "prompt": "open calculator",
                "claim": "Launches Calculator window, verifies HWND and visibility, and shuts down cleanly.",
                "evidence_class": "FROZEN_PRODUCT_PHYSICAL_EXECUTION"
            },
            {
                "case_id": "FROZEN-02-NOTEPAD_SAVE_REGRESSION",
                "prompt": "open notepad type hello and save it to desktop with name test1.txt",
                "claim": "Executes full application-mediated Save As workflow through Notepad UI, verifying physical artifact > 0 bytes with 'hello'.",
                "evidence_class": "FROZEN_PRODUCT_PHYSICAL_EXECUTION"
            },
            {
                "case_id": "FROZEN-03-NOTEPADPP_INTERACTION",
                "prompt": "open notepad++",
                "claim": "Launches Notepad++, verifies editing window, and closes cleanly without orphans.",
                "evidence_class": "FROZEN_PRODUCT_PHYSICAL_EXECUTION"
            },
            {
                "case_id": "FROZEN-04-HARDWARE_OBSERVATION",
                "prompt": "check available system memory",
                "claim": "Queries physical host memory status without mutating desktop state.",
                "evidence_class": "FROZEN_PRODUCT_PHYSICAL_EXECUTION"
            },
            {
                "case_id": "FROZEN-05-ADVERSARIAL_UNHANDLED_SAFETY",
                "prompt": "compute sha256 hash for confidential_payload_789",
                "claim": "Must reject unhandled adversarial command gracefully; strict ZERO false completion.",
                "evidence_class": "FROZEN_PRODUCT_ADVERSARIAL_SAFETY"
            }
        ]
    }

    with open(AUDIT_DIR / "F0_23_HOLDOUT_MANIFEST.json", "w", encoding="utf-8") as f:
        json.dump(holdout_manifest, f, indent=2)
    print(f"Generated {AUDIT_DIR / 'F0_23_HOLDOUT_MANIFEST.json'} (5 holdout cases)")


if __name__ == "__main__":
    main()
