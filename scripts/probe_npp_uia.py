import subprocess
import time
import ctypes
import ctypes.wintypes as wintypes
from astrarun.interaction.discovery import inspect_window_ui
from astrarun.hermes.resource_lifecycle import capture_world_frame

user32 = ctypes.windll.user32
npp_path = r"C:\Program Files\Notepad++\notepad++.exe"
proc = subprocess.Popen([npp_path])
pid = proc.pid
print(f"Launched Notepad++ PID: {pid}")
time.sleep(2.0)

frame = capture_world_frame("npp_probe")
npp_hwnds = [w.hwnd for w in frame.windows if w.pid == pid and w.hwnd]

for h in npp_hwnds:
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, cls, 256)
    title_len = user32.GetWindowTextLengthW(h)
    title_buf = ctypes.create_unicode_buffer(title_len + 1)
    user32.GetWindowTextW(h, title_buf, title_len + 1)
    is_vis = bool(user32.IsWindowVisible(h))
    print(f"HWND {h}: Class='{cls.value}', Title='{title_buf.value}', Visible={is_vis}")
    if cls.value == "Notepad++" or "Notepad++" in title_buf.value:
        els = inspect_window_ui(h, max_depth=3, max_elements=50)
        print(f"  -> Discovered {len(els)} controls under {h}")
        for el in els[:10]:
            print(f"     - {el.control_type.name}: '{el.name}' (id: {el.automation_id})")

proc.terminate()
try:
    proc.wait(timeout=2.0)
except Exception:
    proc.kill()
print("Cleaned up.")
