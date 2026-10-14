"""Generate the authoritative, immutable source freeze manifest for Phase F0-25F.3."""

import hashlib
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def get_git_info():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip()
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT).decode().strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_ROOT).decode().splitlines()
        dirty_count = len([s for s in status if s.strip()])
    except Exception:
        commit = "unknown"
        branch = "unknown"
        dirty_count = 0
    return commit, branch, dirty_count

def generate_freeze_manifest():
    commit, branch, dirty_count = get_git_info()
    manifest = {
        "phase": "F0-25F.3",
        "description": "Authoritative immutable source freeze manifest before canonical build and physical acceptance",
        "commit": commit,
        "branch": branch,
        "dirty_count": dirty_count,
        "source_hashes": {},
    }

    scan_dirs = ["src", "packaging", "scripts", "tests"]
    total_files = 0
    total_bytes = 0

    for sdir in scan_dirs:
        dir_path = REPO_ROOT / sdir
        if not dir_path.exists():
            continue
        for p in sorted(dir_path.rglob("*")):
            if p.is_file() and not p.name.endswith((".pyc", ".pyo", ".log", ".tmp")):
                rel_path = str(p.relative_to(REPO_ROOT)).replace("\\", "/")
                file_size = p.stat().st_size
                sha = compute_sha256(p)
                manifest["source_hashes"][rel_path] = {
                    "sha256": sha,
                    "size": file_size,
                }
                total_files += 1
                total_bytes += file_size

    manifest["total_files_frozen"] = total_files
    manifest["total_bytes_frozen"] = total_bytes

    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_SOURCE_FREEZE.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Frozen {total_files} files ({total_bytes} bytes) into {out_file}")

if __name__ == "__main__":
    generate_freeze_manifest()
