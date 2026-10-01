"""
Phase 17 - Stage 2 Artifact Downloader & Cryptographic Verifier
Downloads authorized tournament models to canonical storage E:\AI_Models\
and verifies local SHA-256 against upstream published hashes.
"""

import sys
import os
import json
import time
import hashlib
from pathlib import Path
from huggingface_hub import hf_hub_download

# Canonical Storage Paths
GGUF_DIR = Path(r"E:\AI_Models\GGUF")
ONNX_DIR = Path(r"E:\AI_Models\ONNX\bge-small-en-v1.5")
MANIFEST_DIR = Path(__file__).resolve().parent / "env"

GGUF_DIR.mkdir(parents=True, exist_ok=True)
ONNX_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

AUTHORIZED_ARTIFACTS = [
    {
        "name": "Qwen2.5-Coder-1.5B-Instruct-Q4_K_M",
        "repo_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        "repo_url": "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        "commit": "f86cb2c1fa58255f8052cc32aeede1b7482d4361",
        "license": "apache-2.0",
        "filename": "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "expected_size_bytes": 1117320768,
        "upstream_sha256": "cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046",
        "target_dir": GGUF_DIR,
        "target_filename": "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
    },
    {
        "name": "Qwen2.5-Coder-1.5B-Instruct-Q5_K_M",
        "repo_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        "repo_url": "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        "commit": "f86cb2c1fa58255f8052cc32aeede1b7482d4361",
        "license": "apache-2.0",
        "filename": "qwen2.5-coder-1.5b-instruct-q5_k_m.gguf",
        "expected_size_bytes": 1285494336,
        "upstream_sha256": "f15d02e8e51a5c6f9448b972819acfa66aee4d8bb7d881a8b8ba3d90da08ef09",
        "target_dir": GGUF_DIR,
        "target_filename": "qwen2.5-coder-1.5b-instruct-q5_k_m.gguf"
    },
    {
        "name": "Spark-X2.5-1.7B-Q4_K_M",
        "repo_id": "XHToken/Spark-X2.5-1.7B-GGUF",
        "repo_url": "https://huggingface.co/XHToken/Spark-X2.5-1.7B-GGUF",
        "commit": "1f7fa33b1245c14730da39e125714ad3a327901b",
        "license": "apache-2.0",
        "filename": "Spark-X2.5-1.7B-Q4_K_M.gguf",
        "expected_size_bytes": 1107457856,
        "upstream_sha256": "902bde2522394954ac17821b3e5fd0df02defbc6944f122253f2580acf0503f4",
        "target_dir": GGUF_DIR,
        "target_filename": "Spark-X2.5-1.7B-Q4_K_M.gguf"
    },
    {
        "name": "BGE-Small-EN-v1.5-ONNX",
        "repo_id": "BAAI/bge-small-en-v1.5",
        "repo_url": "https://huggingface.co/BAAI/bge-small-en-v1.5",
        "commit": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        "license": "mit",
        "filename": "onnx/model.onnx",
        "expected_size_bytes": 133093490,
        "upstream_sha256": "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
        "target_dir": ONNX_DIR,
        "target_filename": "model.onnx",
        "companion_files": [
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json"
        ]
    }
]

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def main():
    print("=== Phase 17 - Stage 2 Artifact Downloader & Verifier ===")
    print(f"Destination GGUF: {GGUF_DIR}")
    print(f"Destination ONNX: {ONNX_DIR}\n")
    
    results = []
    all_passed = True
    
    for item in AUTHORIZED_ARTIFACTS:
        print(f"--------------------------------------------------")
        print(f"Processing: {item['name']}")
        print(f"  Repo:     {item['repo_url']}")
        print(f"  File:     {item['filename']}")
        print(f"  Expected: {item['expected_size_bytes']} bytes (~{round(item['expected_size_bytes'] / (1024*1024), 2)} MB)")
        print(f"  Upstream SHA-256: {item['upstream_sha256']}")
        
        target_path = item["target_dir"] / item["target_filename"]
        
        # Check if already present and verified
        already_valid = False
        if target_path.exists() and target_path.stat().st_size == item["expected_size_bytes"]:
            print(f"  File exists locally. Verifying SHA-256...")
            local_hash = compute_sha256(target_path)
            if local_hash == item["upstream_sha256"]:
                print(f"  [OK] Hash matches upstream: {local_hash}")
                already_valid = True
            else:
                print(f"  [WARN] Corrupt existing file (hash {local_hash} != {item['upstream_sha256']}). Re-downloading...")
                
        if not already_valid:
            print(f"  Downloading from HuggingFace...")
            t0 = time.perf_counter()
            downloaded_cached = hf_hub_download(
                repo_id=item["repo_id"],
                filename=item["filename"],
                revision=item["commit"]
            )
            dl_time = time.perf_counter() - t0
            print(f"  Download completed in {round(dl_time, 2)} s. Copying to canonical path...")
            
            # Copy/move to canonical destination
            import shutil
            shutil.copy2(downloaded_cached, target_path)
            
            # Compute hash
            local_hash = compute_sha256(target_path)
            
        actual_size = target_path.stat().st_size
        hash_matched = (local_hash == item["upstream_sha256"])
        size_matched = (actual_size == item["expected_size_bytes"])
        
        if hash_matched and size_matched:
            print(f"  [PASS] Successfully verified {item['name']}")
            print(f"         Local Path: {target_path}")
            print(f"         Local Hash: {local_hash}")
        else:
            print(f"  [FAIL] Verification failed for {item['name']}")
            print(f"         Local:    {actual_size} bytes, hash: {local_hash}")
            print(f"         Expected: {item['expected_size_bytes']} bytes, hash: {item['upstream_sha256']}")
            all_passed = False
            
        # Download companion files if needed (e.g. tokenizer for ONNX)
        companion_results = {}
        for comp_file in item.get("companion_files", []):
            comp_target = item["target_dir"] / comp_file
            if not comp_target.exists():
                print(f"  Fetching companion file: {comp_file}")
                cached = hf_hub_download(
                    repo_id=item["repo_id"],
                    filename=comp_file,
                    revision=item["commit"]
                )
                import shutil
                shutil.copy2(cached, comp_target)
            companion_results[comp_file] = {
                "size_bytes": comp_target.stat().st_size,
                "local_path": str(comp_target)
            }
            
        record = {
            "artifact_name": item["name"],
            "repo_id": item["repo_id"],
            "repo_url": item["repo_url"],
            "revision_commit": item["commit"],
            "license": item["license"],
            "remote_filename": item["filename"],
            "local_path": str(target_path),
            "expected_size_bytes": item["expected_size_bytes"],
            "actual_size_bytes": actual_size,
            "size_matched": size_matched,
            "upstream_sha256": item["upstream_sha256"],
            "local_sha256": local_hash,
            "sha256_matched": hash_matched,
            "verification_status": "VERIFIED" if (hash_matched and size_matched) else "CORRUPT_OR_MISMATCHED",
            "companion_files": companion_results
        }
        results.append(record)

    # Save Manifest
    manifest_payload = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage": "STAGE_2_MODEL_ARTIFACTS",
        "artifacts_count": len(results),
        "all_verified": all_passed,
        "artifacts": results
    }
    
    manifest_path = MANIFEST_DIR / "STAGE_2_DOWNLOAD_MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_payload, f, indent=2)
        
    print(f"\n==================================================")
    print(f"All Stage-2 downloads complete.")
    print(f"Manifest written to: {manifest_path}")
    print(f"Status: {'100% VERIFIED' if all_passed else 'VERIFICATION FAILED'}")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
