import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
from PIL import ImageGrab

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Attach current thread to Default
hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
if hwinsta:
    user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
if not hdesk:
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
user32.SetThreadDesktop(hdesk)

# Clean only AstraRun.exe processes
for p in psutil.process_iter(["pid", "name"]):
    if "astrarun" in (p.info["name"] or "").lower():
        try:
            p.kill()
        except Exception:
            pass
time.sleep(1.0)

# Launch source
cmd = [str(Path(".venv/Scripts/python.exe").resolve()), "src/astrarun/main.py", "--show-now"]
si_cmd = subprocess.STARTUPINFO()
si_cmd.lpDesktop = r"WinSta0\Default"
proc = subprocess.Popen(cmd, startupinfo=si_cmd)
print(f"Started PID={proc.pid}")

sys.path.insert(0, "src")
from astrarun.core.single_instance import AstraSingleInstance
si = AstraSingleInstance()

t0 = time.time()
ready = False
while time.time() - t0 < 15.0:
    res = si.send_command("SHOW_MAIN_UI", timeout_ms=500)
    if res.get("status") == "OK" or res.get("action") == "SHOW_MAIN_UI_TRIGGERED":
        ready = True
        break
    time.sleep(0.5)

print("IPC Ready:", ready)
time.sleep(1.0)

state_path = Path(r"C:\Users\hp\AppData\Local\AstraRun\data\astrarun_state.json")
sf = json.loads(state_path.read_text(encoding="utf-8"))
hwnd = sf.get("launcher_hwnd")
pid = sf.get("pid")
print(f"State file: PID={pid}, HWND={hwnd}")

pid_val = wintypes.DWORD()
tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
th_desk = user32.GetThreadDesktop(tid)

def get_name(h):
    needed = wintypes.DWORD()
    user32.GetUserObjectInformationW(h, 2, None, 0, ctypes.byref(needed))
    buf = ctypes.create_unicode_buffer(needed.value // 2 + 2)
    user32.GetUserObjectInformationW(h, 2, buf, needed.value, ctypes.byref(needed))
    return buf.value

desktop_name = get_name(th_desk)
print(f"AstraRun thread desktop name: '{desktop_name}'")
print(f"IsWindow: {user32.IsWindow(hwnd)}")
print(f"IsWindowVisible: {user32.IsWindowVisible(hwnd)}")

enum_found = []
def cb(h, lp):
    if h == hwnd:
        enum_found.append(h)
    return True
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(cb), 0)
print(f"EnumWindows on Default found hwnd: {enum_found}")

rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
print(f"Rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom})")

# Test attestation
from astrarun.ui.attestation import attest_window_visibility
att = attest_window_visibility(hwnd, expected_pid=pid)
print(f"Attestation status: {att['status']}, is_visible={att['is_visible']}")
print(f"Attestation failure_reasons: {att['failure_reasons']}")

# Screenshot
img = ImageGrab.grab(all_screens=True)
cropped = img.crop((rect.left, rect.top, rect.right, rect.bottom))
colors = [cropped.getpixel((x, y)) for x in range(cropped.width) for y in range(cropped.height)]
dark_pixels = [c for c in colors if c[0] < 40 and c[1] < 40 and c[2] < 40]
print(f"Dark launcher pixels: {len(dark_pixels)} / {len(colors)}")

# Clean up
try:
    si.send_command("QUIT")
except Exception:
    pass
time.sleep(0.5)
try:
    proc.kill()
except Exception:
    pass
