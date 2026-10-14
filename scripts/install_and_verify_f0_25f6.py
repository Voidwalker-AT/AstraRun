"""Install PyInstaller canonical binary and verify SHA256 parity for F0-25F.6 (Stage 13)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path

import psutil

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_EXE = ROOT_DIR / "dist" / "AstraRun" / "AstraRun.exe"
DIST_DIR = ROOT_DIR / "dist" / "AstraRun"
INSTALL_DIR = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "AstraRun"
INSTALL_EXE = INSTALL_DIR / "AstraRun.exe"
OUT_JSON = ROOT_DIR / "docs" / "audit" / "F0_25F6_BINARY_IDENTITY.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def remove_readonly(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


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
    print("[BUILD_INSTALL] Verifying PyInstaller build and installing canonical binary for F0-25F.6...")
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
                shutil.rmtree(dest, onexc=remove_readonly)
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            if dest.exists():
                try:
                    os.chmod(dest, stat.S_IWRITE)
                except Exception:
                    pass
            shutil.copy2(item, dest)

    installed_hash = sha256_file(INSTALL_EXE)
    installed_size = INSTALL_EXE.stat().st_size
    print(f"[BUILD_INSTALL] Installed AstraRun.exe: sha256={installed_hash}, size={installed_size} bytes")

    parity = (built_hash == installed_hash) and (built_size == installed_size)
    print(f"[BUILD_INSTALL] Binary parity verified: {parity}")

    result = {
        "phase": "F0-25F.6",
        "stage": "STAGE 13 — PRODUCTION ARTIFACT VERIFICATION",
        "timestamp": time.time(),
        "build_status": "SUCCESS" if parity else "FAIL",
        "dist_exe": str(DIST_EXE),
        "dist_sha256": built_hash,
        "dist_size_bytes": built_size,
        "install_exe": str(INSTALL_EXE),
        "install_sha256": installed_hash,
        "install_size_bytes": installed_size,
        "binary_parity_verified": parity,
        "hash_parity": (built_hash == installed_hash),
        "size_parity": (built_size == installed_size),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[BUILD_INSTALL] Wrote binary identity verification to {OUT_JSON}")
    return 0 if parity else 1


if __name__ == "__main__":
    sys.exit(main())
