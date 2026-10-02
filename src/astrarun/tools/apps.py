"""Safe application execution tool."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tools.apps")


def _launch_win32_process(cmd_line: str, desktop: str = r"WinSta0\Default") -> bool:
    """Launch process on the interactive user desktop via native CreateProcessW."""
    import ctypes
    from ctypes import wintypes

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.c_char_p),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.lpDesktop = desktop
    pi = PROCESS_INFORMATION()

    kernel32 = ctypes.windll.kernel32
    ok = kernel32.CreateProcessW(
        None,
        cmd_line,
        None,
        None,
        False,
        0,
        None,
        None,
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    if ok:
        kernel32.CloseHandle(pi.hProcess)
        kernel32.CloseHandle(pi.hThread)
        return True
    return False


def open_app(app: str, path: str | None = None, target: str | None = None) -> bool:
    """
    Launch a local application without using a shell.
    
    Args:
        app: Application key or identifier.
        path: Absolute or resolved executable path.
        target: Optional argument passed to the executable (e.g., file path to open).
    """
    if not path:
        logger.error("Cannot launch application '%s': no path provided.", app)
        return False

    exe_path = Path(path)
    if not exe_path.exists():
        logger.error("Cannot launch application '%s': file not found at %s", app, path)
        return False

    args = [str(exe_path)]
    if target:
        args.append(str(target))

    logger.info("Executing open_app: %s (args=%s)", exe_path, args)

    try:
        if sys.platform == "win32":
            if exe_path.suffix.lower() == ".lnk":
                os.startfile(str(exe_path))
                return True

            launch_cmd = str(exe_path)
            # Modern Windows 11 Store/MSIX applications cannot be spawned via raw internal binaries;
            # resolve to standard system alias or executable if available.
            if "windowsapps" in str(exe_path).lower():
                alias = f"{app}.exe" if not app.endswith(".exe") else app
                system_root = os.environ.get("SystemRoot", r"C:\Windows")
                candidates = [
                    Path(system_root) / alias,
                    Path(system_root) / "System32" / alias,
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / alias,
                ]
                for cand in candidates:
                    if cand.exists():
                        launch_cmd = str(cand)
                        break

            cmd_line = f'"{launch_cmd}"'
            if target:
                cmd_line += f' "{target}"'

            if _launch_win32_process(cmd_line):
                return True

            # Fallback to os.startfile if CreateProcessW failed
            try:
                os.startfile(launch_cmd)
                return True
            except Exception:
                pass

            # Final detached Popen fallback
            creationflags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
            subprocess.Popen(
                args,
                shell=False,
                close_fds=True,
                creationflags=creationflags,
            )
        else:
            subprocess.Popen(args, shell=False, close_fds=True)
        return True
    except Exception as err:
        logger.error("Failed to launch application '%s': %s", app, err, exc_info=True)
        return False

