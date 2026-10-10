"""
scripts/generate_f0_21a_freeze_manifest.py

Authoritative Freeze Manifest for Phase F0-21A:
- Git status & HEAD commit
- All production source files in src/astrarun (size, sha256)
- Runtime/packaging configs (pyproject.toml, packaging/AstraRun.spec)
- Regression & adversarial test files
- Frozen executable dist/AstraRun/AstraRun.exe
- Composite source hash and immutable lock
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


def get_git_info(repo_root: Path) -> dict:
    info = {"commit": "unknown", "branch": "unknown", "dirty": False}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
        info["commit"] = commit
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, text=True
        ).strip()
        info["branch"] = branch
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, text=True
        ).strip()
        info["dirty"] = len(status) > 0
    except Exception as e:
        info["error"] = str(e)
    return info


def main():
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src" / "astrarun"
    tests_dir = repo_root / "tests"
    dist_exe = repo_root / "dist" / "AstraRun" / "AstraRun.exe"

    print("Computing Git state...")
    git_info = get_git_info(repo_root)

    print("Hashing production source files...")
    py_files = sorted(
        [p for p in src_dir.rglob("*.py") if "__pycache__" not in p.parts],
        key=lambda p: str(p.relative_to(repo_root)).replace("\\", "/"),
    )

    manifest_files = {}
    composite_hasher = hashlib.sha256()

    for p in py_files:
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        size, sha = hash_file(p)
        manifest_files[rel] = {"size_bytes": size, "sha256": sha}
        composite_hasher.update(f"{rel}:{sha}\n".encode("utf-8"))

    # Config files
    config_paths = [
        repo_root / "pyproject.toml",
        repo_root / "packaging" / "AstraRun.spec",
    ]
    manifest_configs = {}
    for p in config_paths:
        if p.exists():
            rel = str(p.relative_to(repo_root)).replace("\\", "/")
            size, sha = hash_file(p)
            manifest_configs[rel] = {"size_bytes": size, "sha256": sha}
            composite_hasher.update(f"{rel}:{sha}\n".encode("utf-8"))

    test_files = sorted(
        [p for p in tests_dir.glob("test_f0_21_*.py")],
        key=lambda p: str(p.relative_to(repo_root)).replace("\\", "/"),
    )

    manifest_tests = {}
    for p in test_files:
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        size, sha = hash_file(p)
        manifest_tests[rel] = {"size_bytes": size, "sha256": sha}

    binary_info = {}
    if dist_exe.exists():
        size, sha = hash_file(dist_exe)
        binary_info = {
            "path": str(dist_exe.relative_to(repo_root)).replace("\\", "/"),
            "size_bytes": size,
            "sha256": sha,
            "verified_present": True,
        }
    else:
        binary_info = {"verified_present": False, "error": "Executable not found"}

    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-21A",
        "lock_status": "LOCKED",
        "git": git_info,
        "composite_source_tree_sha256": composite_hasher.hexdigest(),
        "frozen_binary": binary_info,
        "config_files": manifest_configs,
        "test_files": manifest_tests,
        "production_files_count": len(manifest_files),
        "production_files": manifest_files,
    }

    out_path = repo_root / "docs" / "audit" / "F0_21A_FREEZE_MANIFEST.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest written to: {out_path}")
    print(f"Composite Source Tree SHA-256: {manifest['composite_source_tree_sha256']}")
    if binary_info.get("verified_present"):
        print(f"Frozen Binary SHA-256: {binary_info['sha256']}")
        print(f"Frozen Binary Size: {binary_info['size_bytes']} bytes")
    else:
        print("WARNING: Frozen binary not present!")


if __name__ == "__main__":
    main()
