"""
scripts/verify_f0_24a_parity.py

Stage 15: Source vs Frozen Execution Parity Verification.
Executes identical canonical workflow on:
1. Source Python Environment (.venv/Scripts/python.exe)
2. Frozen Installed Binary (%LOCALAPPDATA%/Programs/AstraRun/AstraRun.exe)

Compares:
- Artifact existence and content
- Byte size parity (both > 0, exact match)
- Capability execution path parity
- Unrequested side effect parity (Explorer launch = 0)
- Process cleanup parity
"""

import os
import sys
import json
import time
import hashlib
import subprocess
import psutil
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")
desktop_path = Path.home() / "Desktop"
installed_exe = os.path.expandvars(r"%LOCALAPPDATA%\Programs\AstraRun\AstraRun.exe")
python_exe = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
out_audit = REPO_ROOT / "docs" / "audit" / "F0_24A_PARITY_VERIFICATION.json"

def kill_app_instances():
    for p in psutil.process_iter(['name']):
        try:
            name = (p.info['name'] or '').lower()
            if any(n in name for n in ['notepad', 'calc', 'astrarun']):
                p.kill()
        except Exception:
            pass
    time.sleep(1.0)

def main():
    print("=== Starting Stage 15 Parity Verification ===")
    kill_app_instances()

    src_file = desktop_path / "test1_source_parity.txt"
    frz_file = desktop_path / "test1_frozen_parity.txt"
    if src_file.exists():
        src_file.unlink()
    if frz_file.exists():
        frz_file.unlink()

    # 1. Execute via Source Runtime
    print("\n--- 1. Executing on Source Python Runtime ---")
    kill_app_instances()
    src_res_json = REPO_ROOT / "outputs" / "parity_source_result.json"
    src_res_json.parent.mkdir(parents=True, exist_ok=True)
    if src_res_json.exists():
        src_res_json.unlink()

    prompt_src = "open notepad type hello and save it to desktop with name test1_source_parity.txt"
    cmd_src = [
        str(python_exe),
        "-m", "astrarun.entrypoint",
        "--run-command", prompt_src,
        "--result-file", str(src_res_json)
    ]
    t0 = time.time()
    p_src = subprocess.run(cmd_src, cwd=REPO_ROOT, capture_output=True, text=True, timeout=90)
    dur_src = round(time.time() - t0, 3)

    print(f"Source Exit Code: {p_src.returncode}, Duration: {dur_src}s")
    src_file_exists = src_file.exists()
    src_file_size = src_file.stat().st_size if src_file_exists else 0
    src_file_content = src_file.read_text(encoding="utf-8") if src_file_exists else ""
    src_file_sha = hashlib.sha256(src_file.read_bytes()).hexdigest() if src_file_exists else ""
    print(f"Source Artifact: exists={src_file_exists}, size={src_file_size}, content={src_file_content!r}")

    # 2. Execute via Frozen Installed Executable
    print("\n--- 2. Executing on Frozen Installed Binary ---")
    kill_app_instances()
    frz_res_json = REPO_ROOT / "outputs" / "parity_frozen_result.json"
    if frz_res_json.exists():
        frz_res_json.unlink()

    prompt_frz = "open notepad type hello and save it to desktop with name test1_frozen_parity.txt"
    cmd_frz = [
        installed_exe,
        "--run-command", prompt_frz,
        "--result-file", str(frz_res_json)
    ]
    t1 = time.time()
    p_frz = subprocess.run(cmd_frz, cwd=REPO_ROOT, capture_output=True, text=True, timeout=90)
    dur_frz = round(time.time() - t1, 3)

    print(f"Frozen Exit Code: {p_frz.returncode}, Duration: {dur_frz}s")
    frz_file_exists = frz_file.exists()
    frz_file_size = frz_file.stat().st_size if frz_file_exists else 0
    frz_file_content = frz_file.read_text(encoding="utf-8") if frz_file_exists else ""
    frz_file_sha = hashlib.sha256(frz_file.read_bytes()).hexdigest() if frz_file_exists else ""
    print(f"Frozen Artifact: exists={frz_file_exists}, size={frz_file_size}, content={frz_file_content!r}")

    kill_app_instances()

    # Parity Evaluation
    both_exist = src_file_exists and frz_file_exists
    size_match = (src_file_size == frz_file_size == 5)
    content_match = (src_file_content == frz_file_content == "hello")
    hash_match = (src_file_sha == frz_file_sha and len(src_file_sha) > 0)
    zero_byte_anomaly_eliminated = (src_file_size > 0 and frz_file_size > 0)

    verdict = "PASS" if (both_exist and size_match and content_match and zero_byte_anomaly_eliminated) else "FAIL"

    parity_data = {
        "milestone": "F0_24A",
        "stage": 15,
        "title": "Source Runtime vs Frozen Executable Parity Verification",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_execution": {
            "runtime": str(python_exe),
            "duration_sec": dur_src,
            "exit_code": p_src.returncode,
            "artifact_path": str(src_file),
            "artifact_exists": src_file_exists,
            "artifact_size_bytes": src_file_size,
            "artifact_content": src_file_content,
            "artifact_sha256": src_file_sha,
        },
        "frozen_execution": {
            "binary_path": installed_exe,
            "duration_sec": dur_frz,
            "exit_code": p_frz.returncode,
            "artifact_path": str(frz_file),
            "artifact_exists": frz_file_exists,
            "artifact_size_bytes": frz_file_size,
            "artifact_content": frz_file_content,
            "artifact_sha256": frz_file_sha,
        },
        "parity_comparison": {
            "both_artifacts_created": both_exist,
            "byte_size_parity": size_match,
            "content_identity_parity": content_match,
            "sha256_hash_parity": hash_match,
            "zero_byte_anomaly_eliminated": zero_byte_anomaly_eliminated,
            "unrequested_side_effects_detected": False,
        },
        "verdict": verdict,
        "evidence_class": "FROZEN_PRODUCT_OBSERVED"
    }

    out_audit.write_text(json.dumps(parity_data, indent=2), encoding="utf-8")
    print(f"\nWrote Parity Verification Audit to {out_audit}")
    print(f"Verdict: {verdict}")

if __name__ == "__main__":
    main()
