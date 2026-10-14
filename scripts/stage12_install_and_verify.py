"""Stage 12: Verify PyInstaller build, install canonical binary, and attest SHA256 parity."""

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import psutil

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_EXE = ROOT_DIR / "dist" / "AstraRun" / "AstraRun.exe"
DIST_DIR = ROOT_DIR / "dist" / "AstraRun"
INSTALL_DIR = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "AstraRun"
INSTALL_EXE = INSTALL_DIR / "AstraRun.exe"
OUT_JSON = ROOT_DIR / "docs" / "audit" / "F0_25F1_BUILD_INSTALL.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def kill_existing_processes():
    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = (p.info["name"] or "").lower()
            if "astrarun" in name:
                p.kill()
        except Exception:
            pass
    time.sleep(1.0)


def main():
    print("[STAGE 12] Verifying PyInstaller build and installing canonical binary...")
    if not DIST_EXE.exists():
        print(f"[STAGE 12] ERROR: Built executable not found at {DIST_EXE}")
        return 1

    built_hash = sha256_file(DIST_EXE)
    built_size = DIST_EXE.stat().st_size
    print(f"[STAGE 12] Built AstraRun.exe: sha256={built_hash}, size={built_size} bytes")

    kill_existing_processes()

    # Install to LocalAppData/Programs/AstraRun
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[STAGE 12] Copying files from {DIST_DIR} to {INSTALL_DIR}...")
    
    # Copy all files from dist/AstraRun into INSTALL_DIR
    for item in DIST_DIR.iterdir():
        dest = INSTALL_DIR / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    assert INSTALL_EXE.exists(), f"Installed executable missing at {INSTALL_EXE}"
    installed_hash = sha256_file(INSTALL_EXE)
    installed_size = INSTALL_EXE.stat().st_size
    print(f"[STAGE 12] Installed AstraRun.exe: sha256={installed_hash}, size={installed_size} bytes")

    assert built_hash == installed_hash, f"Hash mismatch: built={built_hash} != installed={installed_hash}"
    assert built_size == installed_size, f"Size mismatch: built={built_size} != installed={installed_size}"
    print("[STAGE 12] SUCCESS: Built and installed binaries are hash-identical!")

    report = {
        "status": "PASS",
        "timestamp": time.time(),
        "built_executable": str(DIST_EXE),
        "built_sha256": built_hash,
        "built_size_bytes": built_size,
        "installed_executable": str(INSTALL_EXE),
        "installed_sha256": installed_hash,
        "installed_size_bytes": installed_size,
        "hash_parity": True,
        "size_parity": True,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[STAGE 12] Report saved to {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
