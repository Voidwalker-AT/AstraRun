"""
Phase 17-S: Download and setup isolated llama.cpp runtime for Spark-X2.5-1.7B
Downloads official b11294 CUDA 12.4 Windows build into E:\\AI_Runtimes\\llama.cpp-spark\\
Verifies byte sizes, SHA-256, extracts, and checks executable versions.
"""

import sys
import os
import zipfile
import hashlib
import urllib.request
import subprocess
from pathlib import Path

TARGET_DIR = Path(r"E:\AI_Runtimes\llama.cpp-spark")
TARGET_DIR.mkdir(parents=True, exist_ok=True)

ASSETS = [
    {
        "name": "llama-b11294-bin-win-cuda-12.4-x64.zip",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11294/llama-b11294-bin-win-cuda-12.4-x64.zip",
        "expected_bytes": 263381426,
    },
    {
        "name": "cudart-llama-bin-win-cuda-12.4-x64.zip",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11294/cudart-llama-bin-win-cuda-12.4-x64.zip",
        "expected_bytes": 391443627,
    }
]

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def download_with_progress(url: str, dest_path: Path, expected_size: int):
    if dest_path.exists() and dest_path.stat().st_size == expected_size:
        print(f"Already downloaded: {dest_path.name} ({dest_path.stat().st_size} bytes)")
        return
    print(f"Downloading {url} -> {dest_path}...")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AstraRun-Phase17/1.0"}
    )
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out_f:
        downloaded = 0
        while True:
            chunk = resp.read(1048576) # 1MB
            if not chunk:
                break
            out_f.write(chunk)
            downloaded += len(chunk)
            if downloaded % (10 * 1048576) == 0:
                print(f"  {downloaded / 1048576:.1f} MB / {expected_size / 1048576:.1f} MB")
    print(f"Download complete: {dest_path.name} ({dest_path.stat().st_size} bytes)")

def main():
    print("=== Step 1: Downloading isolated llama.cpp b11294 CUDA 12.4 assets ===")
    results = {}
    for asset in ASSETS:
        dest = TARGET_DIR / asset["name"]
        download_with_progress(asset["url"], dest, asset["expected_bytes"])
        actual_size = dest.stat().st_size
        h = sha256_file(dest)
        print(f"Asset: {asset['name']}")
        print(f"  Size: {actual_size} bytes (Expected: {asset['expected_bytes']})")
        print(f"  SHA-256: {h}")
        results[asset["name"]] = {
            "size": actual_size,
            "sha256": h,
            "size_match": actual_size == asset["expected_bytes"]
        }
        if actual_size != asset["expected_bytes"]:
            print(f"ERROR: Size mismatch for {asset['name']}!")
            sys.exit(1)

    print("\n=== Step 2: Extracting assets to E:\\AI_Runtimes\\llama.cpp-spark ===")
    for asset in ASSETS:
        dest = TARGET_DIR / asset["name"]
        print(f"Extracting {dest.name}...")
        with zipfile.ZipFile(dest, 'r') as zf:
            zf.extractall(TARGET_DIR)

    print("\n=== Step 3: Verifying extracted binaries ===")
    binaries = ["llama-server.exe", "llama-cli.exe", "ggml.dll", "llama.dll"]
    for b in binaries:
        b_path = TARGET_DIR / b
        if b_path.exists():
            h = sha256_file(b_path)
            print(f"  {b}: {b_path.stat().st_size} bytes, SHA-256: {h}")
        else:
            print(f"  {b}: NOT FOUND")

    server_exe = TARGET_DIR / "llama-server.exe"
    if server_exe.exists():
        print("\n=== Step 4: Testing llama-server --version ===")
        res = subprocess.run([str(server_exe), "--version"], capture_output=True, text=True)
        print("llama-server output:")
        print(res.stdout or res.stderr)

    cli_exe = TARGET_DIR / "llama-cli.exe"
    if cli_exe.exists():
        print("\n=== Step 5: Testing llama-cli --version ===")
        res = subprocess.run([str(cli_exe), "--version"], capture_output=True, text=True)
        print("llama-cli output:")
        print(res.stdout or res.stderr)

    with open(TARGET_DIR / "manifest.json", "w", encoding="utf-8") as f:
        import json
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
