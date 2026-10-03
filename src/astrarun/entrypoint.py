"""Standalone Windows executable entry point for AstraRun.

Launched by AstraRun.exe (GUI Subsystem).
Runs without console window, ensuring seamless resident desktop operation.
"""

import os
import sys

# Guarantee High-DPI and platform attributes before any Qt initialization
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

# Ensure proper Windows AppUserModelId for taskbar and notification pinning
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AstraEngineering.AstraRun.Desktop.1.0")
        # If launched from a console with CLI flags, attach to parent console for readable output
        if any(arg in sys.argv for arg in ("--run-command", "--help", "-h", "--version", "--repair")):
            ctypes.windll.kernel32.AttachConsole(-1)
    except Exception:
        pass

# Ensure standard streams exist even in pure windowed GUI mode
if sys.stdout is None:
    import io
    sys.stdout = io.StringIO()
if sys.stderr is None:
    import io
    sys.stderr = io.StringIO()

from astrarun.main import main

if __name__ == "__main__":
    sys.exit(main())
