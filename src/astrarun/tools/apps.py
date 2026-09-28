"""Safe application execution tool."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tools.apps")


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
            # Modern Windows 11 Store/MSIX applications cannot be spawned via raw detached Popen;
            # they require AppX execution alias or os.startfile to initialize an interactive window.
            if "windowsapps" in str(exe_path).lower():
                alias = f"{app}.exe" if not app.endswith(".exe") else app
                try:
                    os.startfile(alias)
                    return True
                except Exception:
                    os.startfile(str(exe_path))
                    return True
            # DETACHED_PROCESS (0x00000008) or CREATE_NEW_PROCESS_GROUP (0x00000200)
            # avoids holding child process handles
            creationflags = 0x00000008 | 0x00000200
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
