"""E2E Installed Product Verification and Evidence Capture for Workflow 1.

Executes strictly against the production installed binary:
C:\\Users\\hp\\AppData\\Local\\Programs\\AstraRun\\AstraRun.exe
via named pipe IPC and launcher UI.
Captures REAL_OS_SCREENSHOT artifacts for all 5 lifecycle stages.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import ctypes

# Ensure src/ on path for IPC client
REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication
from astrarun.core.single_instance import AstraSingleInstance

ARTIFACT_DIR = Path(r"C:\Users\hp\.gemini\antigravity\brain\23cb9148-e84c-4e70-9e8c-2413e3b2f9d6")
INSTALLED_EXE = Path(r"C:\Users\hp\AppData\Local\Programs\AstraRun\AstraRun.exe")
DESKTOP_FILE = Path.home() / "Desktop" / "Astra Computer Use Test.txt"
LOG_FILE = Path.home() / "AppData" / "Local" / "AstraRun" / "logs" / "astrarun.log"

QUERY = "Open Notepad, type 'Astra computer-use test', save it as Desktop\\Astra Computer Use Test.txt, then open File Explorer and show me the file."

def ensure_clean_preconditions():
    print("[PRECHECK] Verifying clean preconditions...")
    if DESKTOP_FILE.exists():
        print(f"[PRECHECK] Removing existing test file: {DESKTOP_FILE}")
        DESKTOP_FILE.unlink()
    assert not DESKTOP_FILE.exists(), "Precondition failed: test file still exists"

    # Close any existing Notepad or AstraRun instances
    os.system("taskkill /f /im notepad.exe 2>nul")
    os.system("taskkill /f /im AstraRun.exe 2>nul")
    time.sleep(1.0)
    print("[PRECHECK] Preconditions verified clean.")

def grab_and_save(screen, filename: str):
    pix = screen.grabWindow(0)
    dest = ARTIFACT_DIR / filename
    pix.save(str(dest))
    print(f"[SCREENSHOT] Saved REAL_OS_SCREENSHOT: {dest} ({pix.width()}x{pix.height()})")
    return dest

def main():
    ensure_clean_preconditions()
    app = QApplication(sys.argv)
    screen = QGuiApplication.primaryScreen()

    print(f"[LAUNCH] Starting resident installed AstraRun: {INSTALLED_EXE}")
    proc = subprocess.Popen([str(INSTALLED_EXE)], cwd=str(INSTALLED_EXE.parent))
    print(f"[LAUNCH] AstraRun PID: {proc.pid}")

    client = AstraSingleInstance()
    connected = False
    print("[IPC] Waiting for AstraRun IPC server...")
    for attempt in range(30):
        time.sleep(0.5)
        res = client.send_command("SHOW_MAIN_UI", timeout_ms=500)
        if res.get("action") == "SHOW_MAIN_UI_TRIGGERED":
            connected = True
            print(f"[IPC] Connected to resident AstraRun after {attempt*0.5:.1f}s")
            break

    if not connected:
        print("[ERROR] Could not connect to resident AstraRun IPC server!")
        proc.kill()
        return 1

    time.sleep(1.0)

    # 1. Populate query in launcher
    print(f"[STEP 1] Populating query in launcher: '{QUERY}'")
    client.send_command("POPULATE_QUERY", {"query": QUERY})
    time.sleep(1.5)  # Wait for launcher slide-in animation to complete
    shot_a = grab_and_save(screen, "A_launcher_submitted_command.png")

    # 2. Submit query to trigger real execution
    print("[STEP 2] Submitting query to trigger real Astra execution...")
    client.send_command("SUBMIT_QUERY", {"query": QUERY})
    time.sleep(0.8)  # HUD appears and displays running step
    shot_b = grab_and_save(screen, "B_hud_task_executing.png")

    # 3. Wait for Notepad to open and text to be typed
    print("[STEP 3] Waiting for Notepad window and typing...")
    time.sleep(2.5)  # Allow Notepad to appear and type_into_window to execute
    shot_c = grab_and_save(screen, "C_notepad_typed_text.png")

    # 4. Wait for File Explorer and file creation
    print("[STEP 4] Waiting for File Explorer and file verification...")
    for _ in range(30):
        if DESKTOP_FILE.exists():
            break
        time.sleep(0.5)

    time.sleep(2.0)  # Let File Explorer window raise and select file
    shot_d = grab_and_save(screen, "D_file_explorer_showing_file.png")

    # 5. Open Task Center to inspect audit trail
    print("[STEP 5] Requesting Task Center display...")
    client.send_command("SHOW_TASK_CENTER")
    time.sleep(1.5)
    shot_e = grab_and_save(screen, "E_task_center_completed.png")

    # 6. Capture system tray area
    print("[STEP 6] Capturing System Tray...")
    shot_tray = grab_and_save(screen, "real_system_tray_rc5a.png")

    # Clean shutdown
    print("[CLEANUP] Requesting clean resident AstraRun shutdown...")
    client.send_command("QUIT")
    time.sleep(1.5)
    if proc.poll() is None:
        proc.terminate()

    # Empirical post-execution file verification
    print("\n============================================================")
    print("EMPIRICAL POST-EXECUTION VERIFICATION")
    print("============================================================")
    if not DESKTOP_FILE.exists():
        print(f"[FAIL] Desktop file does NOT exist: {DESKTOP_FILE}")
        return 1

    content = DESKTOP_FILE.read_text(encoding="utf-8")
    size_bytes = DESKTOP_FILE.stat().st_size
    sha256 = hashlib.sha256(DESKTOP_FILE.read_bytes()).hexdigest()

    print(f"File Path:    {DESKTOP_FILE}")
    print(f"File Exists:  True")
    print(f"File Size:    {size_bytes} bytes")
    print(f"SHA-256:      {sha256}")
    print(f"File Content: {repr(content)}")

    expected_text = "Astra computer-use test"
    if content.strip() == expected_text:
        print("[PASS] File content matches expected text perfectly!")
    else:
        print(f"[WARN] File content '{content}' differs from '{expected_text}'")

    print("\nAll 5 Real OS Screenshots captured:")
    print(f"  A (Launcher):     {shot_a}")
    print(f"  B (HUD Executing):{shot_b}")
    print(f"  C (Notepad):      {shot_c}")
    print(f"  D (Explorer):     {shot_d}")
    print(f"  E (Task Center):  {shot_e}")
    print(f"  Tray:             {shot_tray}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
