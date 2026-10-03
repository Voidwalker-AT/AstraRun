"""Windows Native Power & Session Broadcast Listener for AstraRun 1.0.

Receives WM_POWERBROADCAST, RegisterPowerSettingNotification, and WM_QUERYENDSESSION
events from Windows without active polling.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import threading
from typing import Callable, List, Optional

from astrarun.core.logging import get_logger
from astrarun.power.events import DisplayState, PowerEventType

logger = get_logger("astrarun.power.listener")

# Win32 Constants
WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
PBT_POWERSETTINGCHANGE = 0x8013

WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016

DEVICE_NOTIFY_WINDOW_HANDLE = 0x00000000

# GUID structure for Win32
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

# GUIDs for power settings
# GUID_CONSOLE_DISPLAY_STATE: {6FE69556-704A-47A0-8F24-C28D936F080C}
GUID_CONSOLE_DISPLAY_STATE = GUID(
    0x6FE69556, 0x704A, 0x47A0, (ctypes.c_ubyte * 8)(0x8F, 0x24, 0xC2, 0x8D, 0x93, 0x6F, 0x08, 0x0C)
)
# GUID_SESSION_DISPLAY_STATUS: {2B84C10B-0856-4D6F-8597-580C774EB708}
GUID_SESSION_DISPLAY_STATUS = GUID(
    0x2B84C10B, 0x0856, 0x4D6F, (ctypes.c_ubyte * 8)(0x85, 0x97, 0x58, 0x0C, 0x77, 0x4E, 0xB7, 0x08)
)


class POWERBROADCAST_SETTING(ctypes.Structure):
    _fields_ = [
        ("PowerSetting", GUID),
        ("DataLength", ctypes.wintypes.DWORD),
        ("Data", ctypes.c_byte * 1),
    ]


class PowerCallbackRegistry:
    """Manages listeners for power lifecycle callbacks."""

    def __init__(self) -> None:
        self.on_suspend: List[Callable[[], None]] = []
        self.on_resume: List[Callable[[str], None]] = []
        self.on_display_change: List[Callable[[DisplayState], None]] = []
        self.on_session_end: List[Callable[[], None]] = []

    def dispatch_suspend(self) -> None:
        logger.info("[POWER_BROADCAST] PBT_APMSUSPEND received. Dispatching suspend callbacks.")
        for cb in self.on_suspend:
            try:
                cb()
            except Exception as e:
                logger.error("Error in on_suspend callback: %s", e)

    def dispatch_resume(self, reason: str = "RESUME_AUTOMATIC") -> None:
        logger.info("[POWER_BROADCAST] Resume received (%s). Dispatching resume callbacks.", reason)
        for cb in self.on_resume:
            try:
                cb(reason)
            except Exception as e:
                logger.error("Error in on_resume callback: %s", e)

    def dispatch_display(self, state: DisplayState) -> None:
        logger.info("[POWER_BROADCAST] Display state changed: %s", state.value)
        for cb in self.on_display_change:
            try:
                cb(state)
            except Exception as e:
                logger.error("Error in on_display_change callback: %s", e)

    def dispatch_session_end(self) -> None:
        logger.info("[POWER_BROADCAST] Session ending (shutdown/logoff).")
        for cb in self.on_session_end:
            try:
                cb()
            except Exception as e:
                logger.error("Error in on_session_end callback: %s", e)


# Global callback registry
callbacks = PowerCallbackRegistry()


def register_power_notifications(hwnd: int) -> List[ctypes.c_void_p]:
    """Register window handle for modern display state notifications."""
    handles: List[ctypes.c_void_p] = []
    if sys.platform != "win32":
        return handles

    try:
        user32 = ctypes.windll.user32
        h1 = user32.RegisterPowerSettingNotification(
            ctypes.wintypes.HWND(hwnd),
            ctypes.byref(GUID_CONSOLE_DISPLAY_STATE),
            DEVICE_NOTIFY_WINDOW_HANDLE,
        )
        if h1:
            handles.append(h1)

        h2 = user32.RegisterPowerSettingNotification(
            ctypes.wintypes.HWND(hwnd),
            ctypes.byref(GUID_SESSION_DISPLAY_STATUS),
            DEVICE_NOTIFY_WINDOW_HANDLE,
        )
        if h2:
            handles.append(h2)

        logger.info("Registered display power notifications on HWND %s (handles=%d)", hwnd, len(handles))
    except Exception as e:
        logger.warning("Failed to register display power notifications: %s", e)

    return handles


class StandaloneWin32PowerListener:
    """Creates a hidden Win32 message window to receive power broadcasts in headless mode or tests."""

    def __init__(self) -> None:
        self.hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._notification_handles: List[ctypes.c_void_p] = []

    def start(self) -> None:
        if sys.platform != "win32" or self._running:
            return

        self._running = True
        ready_evt = threading.Event()

        def _message_loop():
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Define WNDPROC
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.wintypes.HWND,
                ctypes.wintypes.UINT,
                ctypes.wintypes.WPARAM,
                ctypes.wintypes.LPARAM,
            )

            def wndproc(hwnd, msg, wparam, lparam):
                if msg == WM_POWERBROADCAST:
                    if wparam == PBT_APMSUSPEND:
                        callbacks.dispatch_suspend()
                        return 1
                    elif wparam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
                        callbacks.dispatch_resume(
                            "RESUME_AUTOMATIC" if wparam == PBT_APMRESUMEAUTOMATIC else "RESUME_SUSPEND"
                        )
                        return 1
                    elif wparam == PBT_POWERSETTINGCHANGE:
                        pbs = ctypes.cast(lparam, ctypes.POINTER(POWERBROADCAST_SETTING)).contents
                        val = pbs.Data[0] if pbs.DataLength > 0 else 1
                        state = DisplayState.OFF if val == 0 else (DisplayState.ON if val == 1 else DisplayState.DIM)
                        callbacks.dispatch_display(state)
                        return 1
                elif msg in (WM_QUERYENDSESSION, WM_ENDSESSION):
                    callbacks.dispatch_session_end()
                    return 1

                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            # Register Class
            class WNDCLASSEX(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.wintypes.UINT),
                    ("style", ctypes.wintypes.UINT),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", ctypes.wintypes.HINSTANCE),
                    ("hIcon", ctypes.wintypes.HICON),
                    ("hCursor", ctypes.wintypes.HICON),
                    ("hbrBackground", ctypes.wintypes.HBRUSH),
                    ("lpszMenuName", ctypes.wintypes.LPCWSTR),
                    ("lpszClassName", ctypes.wintypes.LPCWSTR),
                    ("hIconSm", ctypes.wintypes.HICON),
                ]

            wndproc_ptr = WNDPROC(wndproc)
            class_name = f"AstraRunPowerListener_{id(self)}"
            wc = WNDCLASSEX()
            wc.cbSize = ctypes.sizeof(WNDCLASSEX)
            wc.lpfnWndProc = wndproc_ptr
            wc.hInstance = kernel32.GetModuleHandleW(None)
            wc.lpszClassName = class_name

            atom = user32.RegisterClassExW(ctypes.byref(wc))
            if not atom:
                logger.error("Failed to register window class for power listener")
                ready_evt.set()
                return

            HWND_MESSAGE = -3
            hwnd = user32.CreateWindowExW(
                0, class_name, "AstraRunPowerMsgWindow",
                0, 0, 0, 0, 0,
                HWND_MESSAGE, 0, wc.hInstance, 0
            )

            if not hwnd:
                logger.error("Failed to create message window for power listener")
                ready_evt.set()
                return

            self.hwnd = hwnd
            self._notification_handles = register_power_notifications(hwnd)
            ready_evt.set()

            msg = ctypes.wintypes.MSG()
            while self._running and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        self._thread = threading.Thread(target=_message_loop, daemon=True, name="Win32PowerListener")
        self._thread.start()
        ready_evt.wait(timeout=3.0)
        logger.info("StandaloneWin32PowerListener started (HWND=%s)", self.hwnd)

    def stop(self) -> None:
        self._running = False
        if self.hwnd and sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                for h in self._notification_handles:
                    user32.UnregisterPowerSettingNotification(h)
                self._notification_handles.clear()
                WM_CLOSE = 0x0010
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            except Exception as e:
                logger.debug("Error stopping power listener: %s", e)
        self.hwnd = None


# Qt Native Event Filter for integration when PySide6 is active
try:
    from PySide6.QtCore import QAbstractNativeEventFilter

    class QtPowerNativeEventFilter(QAbstractNativeEventFilter):
        """Intercepts Windows power messages in the main Qt event loop."""

        def nativeEventFilter(self, event_type, message):
            if event_type == b"windows_generic_MSG" and sys.platform == "win32":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_POWERBROADCAST:
                    if msg.wParam == PBT_APMSUSPEND:
                        callbacks.dispatch_suspend()
                    elif msg.wParam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
                        reason = "RESUME_AUTOMATIC" if msg.wParam == PBT_APMRESUMEAUTOMATIC else "RESUME_SUSPEND"
                        callbacks.dispatch_resume(reason)
                    elif msg.wParam == PBT_POWERSETTINGCHANGE:
                        pbs = ctypes.cast(msg.lParam, ctypes.POINTER(POWERBROADCAST_SETTING)).contents
                        val = pbs.Data[0] if pbs.DataLength > 0 else 1
                        state = DisplayState.OFF if val == 0 else (DisplayState.ON if val == 1 else DisplayState.DIM)
                        callbacks.dispatch_display(state)
                elif msg.message in (WM_QUERYENDSESSION, WM_ENDSESSION):
                    callbacks.dispatch_session_end()
            return False, 0

except ImportError:
    QtPowerNativeEventFilter = None  # type: ignore
