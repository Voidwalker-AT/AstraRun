"""
scripts/generate_f0_21_freeze_manifest.py

Generates the authoritative Phase F0-21 Freeze Manifest:
- Hashes all modified production source files in src/astrarun
- Hashes all F0-21 test files in tests/
- Hashes the frozen binary dist/AstraRun/AstraRun.exe
- Computes aggregate composite tree SHA256
- Outputs to docs/audit/F0_21_FREEZE_MANIFEST.json
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def hash_file(path: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
            size += len(chunk)
    return size, hasher.hexdigest()


def main():
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src" / "astrarun"
    tests_dir = repo_root / "tests"
    dist_exe = repo_root / "dist" / "AstraRun" / "AstraRun.exe"

    print("Hashing production source files...")
    py_files = sorted(
        [p for p in src_dir.rglob("*.py") if "__pycache__" not in p.parts],
        key=lambda p: str(p.relative_to(repo_root)).replace("\\", "/")
    )

    manifest_files = {}
    composite_hasher = hashlib.sha256()

    for p in py_files:
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        size, sha = hash_file(p)
        manifest_files[rel] = {"size_bytes": size, "sha256": sha}
        composite_hasher.update(f"{rel}:{sha}\n".encode("utf-8"))

    test_files = sorted(
        [p for p in tests_dir.glob("test_f0_21_*.py")],
        key=lambda p: str(p.relative_to(repo_root)).replace("\\", "/")
    )

    manifest_tests = {}
    for p in test_files:
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        size, sha = hash_file(p)
        manifest_tests[rel] = {"size_bytes": size, "sha256": sha}
        composite_hasher.update(f"{rel}:{sha}\n".encode("utf-8"))

    binary_info = {}
    if dist_exe.exists():
        size, sha = hash_file(dist_exe)
        binary_info = {
            "path": str(dist_exe.relative_to(repo_root)).replace("\\", "/"),
            "size_bytes": size,
            "sha256": sha,
        }

    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-21",
        "composite_tree_sha256": composite_hasher.hexdigest(),
        "frozen_binary": binary_info,
        "test_files": manifest_tests,
        "production_files_count": len(manifest_files),
        "production_files": manifest_files,
    }

    out_path = repo_root / "docs" / "audit" / "F0_21_FREEZE_MANIFEST.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest written to: {out_path}")
    print(f"Composite Tree SHA-256: {manifest['composite_tree_sha256']}")
    if binary_info:
        print(f"Frozen Binary SHA-256: {binary_info['sha256']}")


if __name__ == "__main__":
    main()
