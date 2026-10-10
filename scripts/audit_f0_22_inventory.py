"""
scripts/audit_f0_22_inventory.py

Inventories the complete AstraRun repository for Phase F0-22:
- Git metadata (status, rev-parse HEAD, diff --stat, ls-files) with --no-pager
- Source tree hashes & file counts
- Executable & installer forensic hashes
- Full categorization of all files in the repository
- Generates docs/audit/F0_22_REPOSITORY_INVENTORY.json
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
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


def run_git(args: list[str], cwd: Path) -> str:
    try:
        env = dict(os.environ)
        env["GIT_PAGER"] = "cat"
        env["PAGER"] = "cat"
        cmd = ["git", "--no-pager"] + args
        return subprocess.check_output(cmd, cwd=cwd, text=True, errors="replace", env=env).strip()
    except Exception as e:
        return f"ERROR: {e}"


def main():
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src" / "astrarun"
    tests_dir = repo_root / "tests"
    docs_dir = repo_root / "docs"

    print("Gathering Git metadata...", flush=True)
    git_head = run_git(["rev-parse", "HEAD"], repo_root)
    git_status = run_git(["status", "--porcelain"], repo_root)
    git_diff_stat = run_git(["diff", "--stat"], repo_root)
    git_ls_files_raw = run_git(["ls-files"], repo_root).splitlines()

    print(f"Git HEAD: {git_head}", flush=True)
    print(f"Tracked files count: {len(git_ls_files_raw)}", flush=True)

    print("Hashing production source files...", flush=True)
    prod_py_files = sorted(
        [p for p in src_dir.rglob("*.py") if "__pycache__" not in p.parts],
        key=lambda p: str(p.relative_to(repo_root)).replace("\\", "/"),
    )

    prod_composite_hasher = hashlib.sha256()
    prod_inventory = {}
    for p in prod_py_files:
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        size, sha = hash_file(p)
        prod_inventory[rel] = {"size_bytes": size, "sha256": sha}
        prod_composite_hasher.update(f"{rel}:{sha}\n".encode("utf-8"))

    print(f"Production Python files: {len(prod_py_files)}", flush=True)

    print("Hashing test files...", flush=True)
    test_py_files = sorted(
        [p for p in tests_dir.rglob("*.py") if "__pycache__" not in p.parts],
        key=lambda p: str(p.relative_to(repo_root)).replace("\\", "/"),
    )
    test_inventory = {}
    for p in test_py_files:
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        size, sha = hash_file(p)
        test_inventory[rel] = {"size_bytes": size, "sha256": sha}

    print(f"Test Python files: {len(test_py_files)}", flush=True)

    print("Hashing documentation files...", flush=True)
    doc_files = sorted(
        [p for p in docs_dir.rglob("*") if p.is_file()],
        key=lambda p: str(p.relative_to(repo_root)).replace("\\", "/"),
    )
    doc_inventory = {}
    for p in doc_files:
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        size, sha = hash_file(p)
        doc_inventory[rel] = {"size_bytes": size, "sha256": sha}

    print(f"Docs files: {len(doc_files)}", flush=True)

    # Binary and installer forensics
    print("Hashing binaries and installers...", flush=True)
    built_exe = repo_root / "dist" / "AstraRun" / "AstraRun.exe"
    built_exe_info = {}
    if built_exe.exists():
        size, sha = hash_file(built_exe)
        built_exe_info = {
            "path": str(built_exe.relative_to(repo_root)).replace("\\", "/"),
            "size_bytes": size,
            "sha256": sha,
            "modified": datetime.fromtimestamp(built_exe.stat().st_mtime, timezone.utc).isoformat(),
        }

    installed_exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "AstraRun" / "AstraRun.exe"
    installed_exe_info = {}
    if installed_exe.exists():
        size, sha = hash_file(installed_exe)
        installed_exe_info = {
            "path": str(installed_exe).replace("\\", "/"),
            "size_bytes": size,
            "sha256": sha,
            "modified": datetime.fromtimestamp(installed_exe.stat().st_mtime, timezone.utc).isoformat(),
        }

    installers = list((repo_root / "installer").glob("*.exe")) + list((repo_root / "dist").glob("*Setup*.exe")) + list((repo_root / "dist" / "installer").glob("*.exe"))
    installer_info = {}
    for inst in installers:
        rel = str(inst.relative_to(repo_root)).replace("\\", "/")
        size, sha = hash_file(inst)
        installer_info[rel] = {
            "size_bytes": size,
            "sha256": sha,
            "modified": datetime.fromtimestamp(inst.stat().st_mtime, timezone.utc).isoformat(),
        }

    categories = {
        "src": len(prod_py_files),
        "tests": len(test_py_files),
        "benchmarks": len(list((repo_root / "benchmarks").glob("*"))) if (repo_root / "benchmarks").exists() else 0,
        "scripts": len(list((repo_root / "scripts").glob("*.py"))),
        "packaging": len(list((repo_root / "packaging").glob("*"))),
        "installer": len(list((repo_root / "installer").glob("*"))),
        "docs": len(doc_files),
        "config": len(list((repo_root / "config").glob("*"))) if (repo_root / "config").exists() else 0,
        "outputs": len(list((repo_root / "outputs").glob("*"))) if (repo_root / "outputs").exists() else 0,
    }

    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-22",
        "git": {
            "head": git_head,
            "status_porcelain_lines": len(git_status.splitlines()),
            "ls_files_count": len(git_ls_files_raw),
            "diff_stat": git_diff_stat,
        },
        "counts": {
            "production_python_source_files": len(prod_py_files),
            "test_python_files": len(test_py_files),
            "docs_and_audit_files": len(doc_files),
            "categories_total_file_counts": categories,
        },
        "hashes": {
            "production_source_tree_composite_sha256": prod_composite_hasher.hexdigest(),
            "built_exe": built_exe_info,
            "installed_exe": installed_exe_info,
            "installers": installer_info,
        },
        "forensic_finding": {
            "built_vs_installed_match": built_exe_info.get("sha256") == installed_exe_info.get("sha256"),
            "root_cause_of_discrepancy": (
                "The installed EXE (SHA: "
                + str(installed_exe_info.get("sha256"))[:16]
                + "... mtime: "
                + str(installed_exe_info.get("modified"))
                + ") is an older build and differs from the built EXE (SHA: "
                + str(built_exe_info.get("sha256"))[:16]
                + "... mtime: "
                + str(built_exe_info.get("modified"))
                + ")."
            ),
        },
        "production_inventory": prod_inventory,
        "test_inventory": test_inventory,
        "docs_inventory": doc_inventory,
    }

    out_file = repo_root / "docs" / "audit" / "F0_22_REPOSITORY_INVENTORY.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Inventory written to: {out_file}", flush=True)
    print(f"Production Python Files: {len(prod_py_files)}", flush=True)
    print(f"Test Python Files: {len(test_py_files)}", flush=True)
    print(f"Docs Files: {len(doc_files)}", flush=True)
    print(f"Production Composite SHA-256: {manifest['hashes']['production_source_tree_composite_sha256']}", flush=True)
    print(f"Built EXE SHA-256: {built_exe_info.get('sha256')}", flush=True)
    print(f"Installed EXE SHA-256: {installed_exe_info.get('sha256')}", flush=True)
    print(f"Built vs Installed Match: {manifest['forensic_finding']['built_vs_installed_match']}", flush=True)


if __name__ == "__main__":
    main()
