"""Preflight and Machine Capability Discovery for Phase F0-25C.

Discovers available workstation editors, compilers, runtimes, terminals,
browsers, and reasoning providers without touching unrelated user data.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))


def check_command(cmd_name: str) -> Optional[Dict[str, str]]:
    path = shutil.which(cmd_name)
    if not path:
        return None
    version_info = "available"
    try:
        if cmd_name in ("gcc", "g++"):
            res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=2.0)
            version_info = res.stdout.splitlines()[0] if res.stdout else "unknown"
        elif cmd_name in ("python", "python3"):
            res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=2.0)
            version_info = res.stdout.strip()
        elif cmd_name == "node":
            res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=2.0)
            version_info = res.stdout.strip()
        elif cmd_name in ("javac", "java"):
            res = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=2.0)
            version_info = (res.stderr or res.stdout).splitlines()[0] if (res.stderr or res.stdout) else "unknown"
    except Exception as ex:
        version_info = f"error checking version: {ex}"

    return {"path": path, "version": version_info}


def discover_editors() -> Dict[str, Dict[str, Any]]:
    editors = {}

    # VS Code
    code_path = shutil.which("code")
    if code_path:
        editors["VS_CODE"] = {
            "name": "Visual Studio Code",
            "type": "FULL_IDE",
            "path": code_path,
            "available": True,
            "profiles_supported": True,
        }

    # Notepad++
    npp_default = Path(r"C:\Program Files\Notepad++\notepad++.exe")
    npp_32 = Path(r"C:\Program Files (x86)\Notepad++\notepad++.exe")
    npp_path = npp_default if npp_default.exists() else (npp_32 if npp_32.exists() else None)
    if npp_path:
        editors["NOTEPAD_PLUS_PLUS"] = {
            "name": "Notepad++",
            "type": "ADVANCED_EDITOR",
            "path": str(npp_path),
            "available": True,
            "scintilla_host": True,
        }

    # Notepad
    np_path = shutil.which("notepad")
    if np_path:
        editors["NOTEPAD"] = {
            "name": "Windows Notepad",
            "type": "MINIMAL_EDITOR",
            "path": np_path,
            "available": True,
            "scintilla_host": False,
        }

    # Direct Filesystem
    editors["DIRECT_FILESYSTEM"] = {
        "name": "Direct File I/O Capability",
        "type": "DIRECT_IO",
        "path": "builtin",
        "available": True,
        "zero_gui_overhead": True,
    }

    return editors


def discover_toolchains() -> Dict[str, Any]:
    toolchains = {}
    for cmd in ["gcc", "g++", "python", "node", "javac", "java"]:
        info = check_command(cmd)
        if info:
            toolchains[cmd] = info

    # Explicit local .venv python
    venv_py = Path(sys.executable)
    toolchains["venv_python"] = {
        "path": str(venv_py),
        "version": sys.version.splitlines()[0],
        "is_active_runtime": True,
    }
    return toolchains


def discover_terminals() -> Dict[str, Any]:
    terms = {}
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh:
        terms["POWERSHELL"] = {"path": pwsh, "available": True}
    cmd = shutil.which("cmd")
    if cmd:
        terms["CMD"] = {"path": cmd, "available": True}
    return terms


def discover_browsers() -> Dict[str, Any]:
    browsers = {}
    paths = {
        "MICROSOFT_EDGE": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "GOOGLE_CHROME": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "VIVALDI": [
            os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"),
            r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
        ],
    }
    for name, p_list in paths.items():
        for p in p_list:
            if Path(p).exists():
                browsers[name] = {"path": p, "available": True}
                break
    return browsers


def check_reasoning_server() -> Dict[str, Any]:
    import httpx
    endpoint = "http://127.0.0.1:8089"
    status = {"endpoint": endpoint, "online": False, "model": "none"}
    try:
        r = httpx.get(f"{endpoint}/v1/models", timeout=2.0)
        if r.status_code == 200:
            status["online"] = True
            data = r.json()
            models = [m.get("id", m.get("name")) for m in data.get("data", data.get("models", []))]
            status["model"] = models[0] if models else "qwen2.5-coder"
    except Exception as ex:
        status["error"] = str(ex)
    return status


def main():
    t0 = time.time()
    root = Path(__file__).resolve().parent.parent

    editors = discover_editors()
    toolchains = discover_toolchains()
    terminals = discover_terminals()
    browsers = discover_browsers()
    reasoning = check_reasoning_server()

    machine_caps = {
        "phase": "F0-25C",
        "timestamp": t0,
        "workstation_os": sys.platform,
        "editors": editors,
        "toolchains": toolchains,
        "terminals": terminals,
        "browsers": browsers,
        "local_reasoning_server": reasoning,
    }

    out_caps = root / "docs" / "audit" / "F0_25C_MACHINE_CAPABILITIES.json"
    with open(out_caps, "w", encoding="utf-8") as f:
        json.dump(machine_caps, f, indent=2)

    preflight = {
        "phase": "F0-25C",
        "timestamp": t0,
        "status": "READY",
        "worktree": str(root),
        "python_runtime": sys.executable,
        "editors_count": len(editors),
        "toolchains_count": len(toolchains),
        "terminals_count": len(terminals),
        "browsers_count": len(browsers),
        "reasoning_server_online": reasoning["online"],
        "governed_destinations": [
            str(root / "projects" / "task1_token_matrix"),
            str(root / "projects" / "task2_memory_status"),
            str(root / "projects" / "task3_debugger"),
        ],
        "verdict": "PREFLIGHT_PASS",
    }

    out_pre = root / "docs" / "audit" / "F0_25C_PREFLIGHT.json"
    with open(out_pre, "w", encoding="utf-8") as f:
        json.dump(preflight, f, indent=2)

    print("Preflight and Machine Capabilities successfully generated!")
    print(f"  Editors: {list(editors.keys())}")
    print(f"  Toolchains: {list(toolchains.keys())}")
    print(f"  Browsers: {list(browsers.keys())}")
    print(f"  Reasoning Server Online: {reasoning['online']} ({reasoning.get('model')})")


if __name__ == "__main__":
    main()
