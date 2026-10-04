"""Safe folder opening tool for Windows File Explorer."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tools.folders")


def open_folder(folder: str) -> bool:
    """
    Open a directory safely in Windows File Explorer.
    
    Args:
        folder: Resolved directory path.
    """
    clean_folder = (folder or "").strip().lower()
    if not clean_folder or clean_folder in ("file explorer", "explorer", "this pc", "quick access"):
        logger.info("Executing open_folder: default File Explorer instance")
        if sys.platform == "win32":
            subprocess.Popen(["explorer.exe"], shell=False)
            return True
        else:
            subprocess.Popen(["xdg-open", str(Path.home())], shell=False)
            return True

    folder_path = Path(folder)
    if folder_path.exists() and folder_path.is_file():
        folder_path = folder_path.parent

    if not folder_path.exists() or not folder_path.is_dir():
        logger.error("Cannot open folder: directory does not exist at %s", folder)
        return False

    logger.info("Executing open_folder: %s", folder_path)

    try:
        if sys.platform == "win32":
            os.startfile(str(folder_path))
        else:
            subprocess.Popen(["xdg-open", str(folder_path)], shell=False)
        return True
    except Exception as err:
        logger.error("Failed to open folder '%s': %s", folder, err, exc_info=True)
        return False
