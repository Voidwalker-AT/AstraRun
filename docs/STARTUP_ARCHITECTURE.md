# STARTUP_ARCHITECTURE.md — Resident Lifecycle, Single-Instance Lock & Hotkey Hook

> **Milestone**: AstraRun v0.9 (Daily Driver Integration & Window Intelligence)  
> **Status**: APPROVED  
> **Target Audience**: Windows Systems Engineers, Runtime Developers  
> **Last Updated**: 2026-09-27  

---

## 1. Overview & Lifecycle Requirements

As a daily driver workstation assistant, AstraRun must satisfy four critical operational requirements:
1. **Single-Instance Enforcement**: Only one instance of AstraRun may run per Windows user session. Attempting to launch a second instance must focus the existing resident instance and exit immediately.
2. **Background Persistence**: The application must run quietly in the background without cluttering the Windows taskbar, living exclusively in the System Tray until summoned.
3. **Global Hotkey Hooking**: `Alt+Space` must be registered at the Win32 OS level via `RegisterHotKey`, operating asynchronously with zero UI stutter.
4. **Clean Graceful Shutdown**: Exiting via the system tray or host signal must cleanly unregister hotkeys, flush SQLite ledgers, cancel in-flight tasks, release named Win32 mutexes, and exit with code 0.

---

## 2. Named Win32 Mutex Single-Instance Lock

AstraRun uses a Windows-native named Mutex via `kernel32.CreateMutexW`:

```python
class SingleInstanceLock:
    """Windows-native single instance lock using a named Win32 Mutex."""

    def __init__(self, name: str = "Local\\AstraRun_SingleInstance_Mutex"):
        self.name = name
        self.mutex_handle = None
        self.is_locked = False

    def acquire(self) -> bool:
        ERROR_ALREADY_EXISTS = 183
        self.mutex_handle = kernel32.CreateMutexW(None, True, self.name)
        last_error = kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            if self.mutex_handle:
                kernel32.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
            return False
        self.is_locked = True
        return True

    def release(self) -> None:
        if self.mutex_handle:
            kernel32.ReleaseMutex(self.mutex_handle)
            kernel32.CloseHandle(self.mutex_handle)
            self.mutex_handle = None
            self.is_locked = False
```

### Advantages over File Locks:
- **Instant OS Cleanup**: If AstraRun terminates abnormally or is killed via Task Manager, the Windows kernel automatically destroys the Mutex handle, preventing stale lockfile states.
- **Session Isolation**: Using the `Local\` prefix restricts the mutex scope to the active Windows logon session, allowing multiple terminal services sessions without cross-talk.

---

## 3. Global Hotkey Management (`RegisterHotKey`)

The hotkey architecture in `src/astrarun/hotkeys/manager.py`:
- Spawns a dedicated message-only background thread (`QThread` / `threading.Thread`).
- Calls `user32.RegisterHotKey(hwnd, HOTKEY_ID, MOD_ALT, VK_SPACE)`.
- Enters a lightweight Win32 message pump (`user32.GetMessageW`).
- When `WM_HOTKEY` is received, the thread immediately captures the current foreground window handle via `user32.GetForegroundWindow()` and emits an asynchronous signal to the main PySide6 UI loop.
- The UI loop captures the origin HWND, centers the launcher window on the active monitor, and calls `launcher.toggle_visibility()`.

---

## 4. Graceful Shutdown Sequence

When the user selects **Exit** from the System Tray or terminates via `start-astrarun.ps1 -Stop`:
1. `AstraTrayIcon.hide()` removes the icon from the Windows notification area immediately.
2. `HotkeyManager.unregister()` unregisters `Alt+Space` via `UnregisterHotKey`.
3. `AstraApplication.shutdown()`:
   - Flushes write-ahead logs (`WAL`) on SQLite databases (`tasks.db`, `memory.db`, `usage.db`).
   - Prunes temporary cache files.
   - Terminates the background observation polling thread.
4. `SingleInstanceLock.release()` releases the named mutex.
5. `QApplication.quit()` cleanly terminates the PySide6 event loop.
