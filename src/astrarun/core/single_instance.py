"""Production Single-Instance Guard and Local Windows IPC for AstraRun 1.0.

Implements:
  - Per-user Win32 Named Mutex: Local\\AstraRun_<UserSID>
  - Local Windows Named Pipe IPC: \\\\.\\pipe\\AstraRun_IPC_<UserSID>
  - Activation & Control Messages: SHOW_MAIN_UI, SHOW_TASK_CENTER, PAUSE, RESUME, RESTART, QUIT
  - Zero network listening, zero exposed HTTP ports for activation
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.core.single_instance")

# Win32 Constants
ERROR_ALREADY_EXISTS = 183
ERROR_PIPE_CONNECTED = 535
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
NMPWAIT_USE_DEFAULT_WAIT = 0x00000000


def get_user_sid() -> str:
    """Fetch current user's security identifier (SID) or return deterministic fallback."""
    if sys.platform != "win32":
        username = os.environ.get("USER", os.environ.get("USERNAME", "default"))
        return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]

    try:
        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        advapi32.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        advapi32.OpenProcessToken.restype = ctypes.wintypes.BOOL

        proc = kernel32.GetCurrentProcess()
        token = ctypes.c_void_p()
        if not advapi32.OpenProcessToken(proc, 0x0008, ctypes.byref(token)):
            raise RuntimeError(f"OpenProcessToken failed with error {ctypes.get_last_error()}")

        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.wintypes.DWORD)]

        class TOKEN_USER(ctypes.Structure):
            _fields_ = [("User", SID_AND_ATTRIBUTES)]

        req_len = ctypes.wintypes.DWORD()
        advapi32.GetTokenInformation.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.wintypes.DWORD,
            ctypes.POINTER(ctypes.wintypes.DWORD),
        ]
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(req_len))
        buf = ctypes.create_string_buffer(req_len.value)
        advapi32.GetTokenInformation(token, 1, buf, req_len.value, ctypes.byref(req_len))

        t_user = ctypes.cast(buf, ctypes.POINTER(TOKEN_USER)).contents
        p_str = ctypes.c_wchar_p()
        advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
        if advapi32.ConvertSidToStringSidW(t_user.User.Sid, ctypes.byref(p_str)):
            sid_str = p_str.value or ""
            kernel32.LocalFree(ctypes.cast(p_str, ctypes.c_void_p))
            kernel32.CloseHandle(token)
            if sid_str:
                return sid_str

        kernel32.CloseHandle(token)
    except Exception as e:
        logger.debug("Failed extracting Win32 User SID via token (%s); using username fallback", e)

    username = os.environ.get("USERNAME", "default_user")
    return f"S-FALLBACK-{hashlib.sha256(username.encode('utf-8')).hexdigest()[:16]}"


class AstraSingleInstance:
    """
    Manages resident instance exclusivity and local inter-process activation.
    """

    def __init__(self, custom_sid: Optional[str] = None):
        self.sid = custom_sid or get_user_sid()
        self.mutex_name = f"Local\\AstraRun_{self.sid}"
        self.pipe_name = rf"\\.\pipe\AstraRun_IPC_{self.sid}"
        self.mutex_handle: Optional[int] = None
        self.is_primary: bool = False
        self._server_running: bool = False
        self._server_thread: Optional[threading.Thread] = None
        self._command_handler: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None

    def acquire(self) -> bool:
        """
        Attempt to acquire single-instance mutex.
        If another instance is active, sends SHOW_MAIN_UI via local IPC and returns False.
        """
        if sys.platform != "win32":
            self.is_primary = True
            return True

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = ctypes.c_void_p

        self.mutex_handle = kernel32.CreateMutexW(None, False, self.mutex_name)
        err = kernel32.GetLastError()

        if err == ERROR_ALREADY_EXISTS:
            if self.mutex_handle:
                kernel32.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
            self.is_primary = False
            logger.info("AstraRun instance already resident (mutex %s). Activating...", self.mutex_name)
            # Dispatch SHOW_MAIN_UI to resident instance
            self.send_command("SHOW_MAIN_UI")
            return False

        self.is_primary = True
        logger.info("Acquired single-instance mutex: %s", self.mutex_name)
        return True

    def start_ipc_server(
        self,
        command_handler: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """Start listening for local IPC activation messages in a background daemon thread."""
        if not self.is_primary or sys.platform != "win32":
            return

        self._command_handler = command_handler
        self._server_running = True
        self._server_thread = threading.Thread(target=self._ipc_server_loop, daemon=True, name="AstraIPCServer")
        self._server_thread.start()
        logger.info("Started local IPC pipe server at %s", self.pipe_name)

    def _ipc_server_loop(self) -> None:
        """Server loop waiting for client connections and executing commands."""
        kernel32 = ctypes.windll.kernel32
        h_pipe = kernel32.CreateNamedPipeW(
            self.pipe_name,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            255,  # Max instances
            4096,  # Out buffer
            4096,  # In buffer
            0,     # Default timeout
            None,  # Security attributes
        )

        while self._server_running:
            if h_pipe == -1 or not h_pipe:
                h_pipe = kernel32.CreateNamedPipeW(
                    self.pipe_name,
                    PIPE_ACCESS_DUPLEX,
                    PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                    255,
                    4096,
                    4096,
                    0,
                    None,
                )
                if h_pipe == -1 or not h_pipe:
                    time.sleep(0.05)
                    continue

            connected = kernel32.ConnectNamedPipe(h_pipe, None)
            if not connected and kernel32.GetLastError() != ERROR_PIPE_CONNECTED:
                kernel32.CloseHandle(h_pipe)
                h_pipe = None
                time.sleep(0.01)
                continue

            # Read client command
            buf = ctypes.create_string_buffer(4096)
            bytes_read = ctypes.wintypes.DWORD()
            ok = kernel32.ReadFile(h_pipe, buf, 4096, ctypes.byref(bytes_read), None)
            if ok and bytes_read.value > 0:
                try:
                    payload = json.loads(buf.raw[: bytes_read.value].decode("utf-8"))
                    cmd = payload.get("command", "SHOW_MAIN_UI")
                    args = payload.get("args", {})
                    logger.info("Received IPC command: %s", cmd)

                    resp_data = {"status": "OK", "command": cmd}
                    if self._command_handler:
                        handler_resp = self._command_handler(cmd, args)
                        if isinstance(handler_resp, dict):
                            resp_data.update(handler_resp)

                    resp_bytes = json.dumps(resp_data).encode("utf-8")
                    bytes_written = ctypes.wintypes.DWORD()
                    kernel32.WriteFile(h_pipe, resp_bytes, len(resp_bytes), ctypes.byref(bytes_written), None)
                    kernel32.FlushFileBuffers(h_pipe)
                except Exception as e:
                    logger.warning("Error processing IPC message: %s", e)

            kernel32.DisconnectNamedPipe(h_pipe)

        if h_pipe and h_pipe != -1:
            kernel32.CloseHandle(h_pipe)

    def send_command(self, command: str, args: Optional[Dict[str, Any]] = None, timeout_ms: int = 2000) -> Dict[str, Any]:
        """Send a control command to the resident instance with automatic retry."""
        if sys.platform != "win32":
            return {"status": "SKIPPED_NON_WIN32"}

        kernel32 = ctypes.windll.kernel32
        payload = {"command": command, "args": args or {}, "timestamp": time.time()}
        msg = json.dumps(payload).encode("utf-8")
        out_buf = ctypes.create_string_buffer(4096)
        bytes_read = ctypes.wintypes.DWORD()

        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            ok = kernel32.CallNamedPipeW(
                self.pipe_name,
                msg,
                len(msg),
                out_buf,
                4096,
                ctypes.byref(bytes_read),
                int(min(500, timeout_ms)),
            )
            if ok and bytes_read.value > 0:
                try:
                    return json.loads(out_buf.raw[: bytes_read.value].decode("utf-8"))
                except Exception:
                    return {"status": "OK"}
            time.sleep(0.02)

        # Fallback to trigger file mechanism if pipe call failed (e.g. startup race)
        try:
            os.makedirs("data", exist_ok=True)
            trigger_path = Path("data/astrarun_summon.trigger")
            trigger_path.write_text(f"{time.time()}:{command}", encoding="utf-8")
        except Exception:
            pass

        return {"status": "TRIGGERED_FALLBACK"}

    def release(self) -> None:
        """Cleanly release mutex and shutdown IPC pipe server."""
        self._server_running = False
        if sys.platform == "win32" and self.mutex_handle:
            ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
            self.mutex_handle = None
            logger.info("Released single-instance mutex.")
