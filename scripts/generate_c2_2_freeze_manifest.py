"""Generate C2.2 Production Freeze Manifest for AstraRun.

Audits and hashes:
- Git commit HEAD and modified files list
- All production Python source files under src/astrarun
- Canonical AI models in E:\\AI_Models\\GGUF
- Canonical AI runtime binaries (llama-server.exe, python.exe)
- Composite aggregate hash
"""

import hashlib
import json
import os
import subprocess
import sys
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
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except Exception as e:
        head = f"ERROR: {e}"

    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, text=True
        ).strip().splitlines()
    except Exception as e:
        status = [f"ERROR: {e}"]

    return {"head": head, "modified_files": status}


def main():
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src" / "astrarun"

    print(f"Auditing production source at: {src_dir}")
    py_files = sorted(
        [
            p for p in src_dir.rglob("*.py")
            if "__pycache__" not in p.parts
        ],
        key=lambda p: str(p.relative_to(src_dir)).replace("\\", "/")
    )

    file_entries = {}
    composite_hasher = hashlib.sha256()

    for p in py_files:
        rel_path = str(p.relative_to(src_dir)).replace("\\", "/")
        size, file_sha = hash_file(p)
        file_entries[rel_path] = {
            "bytes": size,
            "sha256": file_sha,
        }
        composite_hasher.update(f"{rel_path}:{file_sha}\n".encode("utf-8"))

    composite_sha = composite_hasher.hexdigest()
    print(f"Total production Python files: {len(py_files)}")
    print(f"Composite tree SHA256: {composite_sha}")

    # Model and Runtime Binaries
    qwen_path = Path(r"E:\AI_Models\GGUF\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
    spark_path = Path(r"E:\AI_Models\GGUF\Spark-X2.5-1.7B-Q4_K_M.gguf")
    llama_srv_path = Path(r"E:\AI_Runtimes\llama.cpp-spark\llama-server.exe")
    python_path = Path(sys.executable)

    binaries_manifest = {}
    for label, target_path in [
        ("qwen_coder_model", qwen_path),
        ("spark_nlp_model", spark_path),
        ("llama_server_binary", llama_srv_path),
        ("python_runtime", python_path),
    ]:
        if target_path.exists():
            bsize, bsha = hash_file(target_path)
            binaries_manifest[label] = {
                "path": str(target_path),
                "bytes": bsize,
                "sha256": bsha,
                "present": True,
            }
        else:
            binaries_manifest[label] = {
                "path": str(target_path),
                "present": False,
            }

    git_info = get_git_info(repo_root)

    manifest = {
        "freeze_tier": "C2.2_FROZEN_SOURCE",
        "timestamp": subprocess.check_output(["powershell", "-Command", "Get-Date -Format o"], text=True).strip(),
        "platform": {
            "os": "Windows",
            "release": "11 Build 26200",
            "architecture": "AMD64",
            "python_version": sys.version,
            "python_executable": sys.executable,
        },
        "git": git_info,
        "total_python_files": len(py_files),
        "composite_tree_sha256": composite_sha,
        "files": file_entries,
        "external_assets": binaries_manifest,
    }

    out_file = repo_root / "docs" / "audit" / "C2_2_FREEZE_MANIFEST.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Successfully generated freeze manifest: {out_file}")


if __name__ == "__main__":
    main()
