"""Install PyInstaller canonical binary and verify SHA256 parity for F0-25F.4."""

from __future__ import annotations

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
OUT_JSON = ROOT_DIR / "docs" / "audit" / "F0_25F4_BUILD_INSTALL.json"


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
            if "astrarun" in name and p.pid != os.getpid():
                p.kill()
        except Exception:
            pass
    time.sleep(1.0)


def main():
    print("[BUILD_INSTALL] Verifying PyInstaller build and installing canonical binary...")
    if not DIST_EXE.exists():
        print(f"[BUILD_INSTALL] ERROR: Built executable not found at {DIST_EXE}")
        return 1

    built_hash = sha256_file(DIST_EXE)
    built_size = DIST_EXE.stat().st_size
    print(f"[BUILD_INSTALL] Built AstraRun.exe: sha256={built_hash}, size={built_size} bytes")

    kill_existing_processes()

    # Install to LocalAppData/Programs/AstraRun
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[BUILD_INSTALL] Copying files from {DIST_DIR} to {INSTALL_DIR}...")

    for item in DIST_DIR.iterdir():
        dest = INSTALL_DIR / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    installed_hash = sha256_file(INSTALL_EXE)
    installed_size = INSTALL_EXE.stat().st_size
    print(f"[BUILD_INSTALL] Installed AstraRun.exe: sha256={installed_hash}, size={installed_size} bytes")

    parity = (built_hash == installed_hash) and (built_size == installed_size)
    print(f"[BUILD_INSTALL] Binary parity verified: {parity}")

    result = {
        "phase": "F0-25F.4",
        "timestamp": time.time(),
        "build_status": "SUCCESS" if parity else "FAIL",
        "dist_exe": str(DIST_EXE),
        "dist_sha256": built_hash,
        "dist_size_bytes": built_size,
        "install_exe": str(INSTALL_EXE),
        "install_sha256": installed_hash,
        "install_size_bytes": installed_size,
        "binary_parity_verified": parity,
    }

    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[BUILD_INSTALL] Wrote build and install results to {OUT_JSON}")
    return 0 if parity else 1


if __name__ == "__main__":
    sys.exit(main())
