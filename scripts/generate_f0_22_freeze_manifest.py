"""Phase F0-22 Authoritative Freeze Manifest Generator.

Computes:
- Git status & HEAD commit
- Production source files in src/astrarun (size, sha256)
- Runtime and packaging configs (pyproject.toml, packaging/AstraRun.spec)
- Test suite files
- Composite source SHA-256 hash
- Frozen executable information (dist/AstraRun/AstraRun.exe and installed)

Outputs:
  docs/audit/F0_22_FREEZE_MANIFEST.json
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
        c = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True)
        info["commit"] = c.stdout.strip()
    except Exception:
        pass
    try:
        b = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True)
        info["branch"] = b.stdout.strip()
    except Exception:
        pass
    try:
        s = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, check=True)
        info["dirty"] = bool(s.stdout.strip())
        info["status_lines"] = len(s.stdout.strip().splitlines()) if s.stdout.strip() else 0
    except Exception:
        pass
    return info


def generate_freeze_manifest():
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src" / "astrarun"
    docs_dir = repo_root / "docs" / "audit"
    docs_dir.mkdir(parents=True, exist_ok=True)

    git_info = get_git_info(repo_root)

    # 1. Production source files
    src_files = {}
    composite_hasher = hashlib.sha256()

    for p in sorted(src_dir.rglob("*.py")):
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        size, fhash = hash_file(p)
        src_files[rel] = {"size": size, "sha256": fhash}
        composite_hasher.update(f"{rel}:{fhash}\n".encode("utf-8"))

    composite_source_hash = composite_hasher.hexdigest()

    # 2. Config & packaging files
    config_files = {}
    for cfg in [
        repo_root / "pyproject.toml",
        repo_root / "packaging" / "AstraRun.spec",
        repo_root / "packaging" / "file_version_info.txt",
        repo_root / "installer" / "AstraRun.iss",
    ]:
        if cfg.exists():
            rel = str(cfg.relative_to(repo_root)).replace("\\", "/")
            size, fhash = hash_file(cfg)
            config_files[rel] = {"size": size, "sha256": fhash}

    # 3. Built binary & Installed binary
    built_exe = repo_root / "dist" / "AstraRun" / "AstraRun.exe"
    built_info = None
    if built_exe.exists():
        size, fhash = hash_file(built_exe)
        built_info = {
            "path": str(built_exe),
            "size": size,
            "sha256": fhash,
            "mtime": datetime.fromtimestamp(built_exe.stat().st_mtime, timezone.utc).isoformat(),
        }

    installed_exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "AstraRun" / "AstraRun.exe"
    installed_info = None
    if installed_exe.exists():
        size, fhash = hash_file(installed_exe)
        installed_info = {
            "path": str(installed_exe),
            "size": size,
            "sha256": fhash,
            "mtime": datetime.fromtimestamp(installed_exe.stat().st_mtime, timezone.utc).isoformat(),
        }

    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-22",
        "description": "Authoritative Freeze Manifest for Phase F0-22 reality audit, consolidation, and generic computer use.",
        "git": git_info,
        "composite_production_source_sha256": composite_source_hash,
        "production_source_file_count": len(src_files),
        "production_sources": src_files,
        "config_files": config_files,
        "built_executable": built_info,
        "installed_executable": installed_info,
        "built_installed_match": bool(built_info and installed_info and built_info["sha256"] == installed_info["sha256"]),
    }

    out_file = docs_dir / "F0_22_FREEZE_MANIFEST.json"
    out_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated {out_file}: {len(src_files)} sources, composite hash={composite_source_hash[:16]}...")
    return manifest


if __name__ == "__main__":
    generate_freeze_manifest()
