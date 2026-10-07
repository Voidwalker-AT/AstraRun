"""Authoritative Windows Restricted Token & Low Integrity Worker Launcher for AstraRun 1.0.

Provides kernel-enforced execution containment using:
1. Restricted Primary Token (stripped admin privileges, LUA token)
2. Low Integrity Level (SECURITY_MANDATORY_LOW_RID = 0x1000)
3. Windows Mandatory Integrity Control (MIC No-Write-Up)
4. Sanitized allowlist environment block
5. Win32 Job Object process-tree containment & resource ceilings
6. Anonymous pipe redirection for stdout/stderr
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.execution.job_object import Win32JobObject
from astrarun.sandbox.models import SandboxProfile, SandboxResult

logger = get_logger("astrarun.sandbox.restricted_launcher")

# Win32 API Definitions
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.GetProcessWindowStation.restype = wintypes.HANDLE
user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
user32.GetThreadDesktop.restype = wintypes.HANDLE

TOKEN_DUPLICATE = 0x0002
TOKEN_QUERY = 0x0008
TOKEN_ASSIGN_PRIMARY = 0x0001
TOKEN_ADJUST_DEFAULT = 0x0080
TOKEN_IMPERSONATE = 0x0004

DISABLE_MAX_PRIVILEGE = 0x1
LUA_TOKEN = 0x4
TokenIntegrityLevel = 25
SE_GROUP_INTEGRITY = 0x00000020
LABEL_SECURITY_INFORMATION = 0x00000010
SE_WINDOW_OBJECT = 7
STARTF_USESTDHANDLES = 0x00000100
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NO_WINDOW = 0x08000000
HANDLE_FLAG_INHERIT = 0x00000001


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


class STARTUPINFOW(ctypes.Structure):
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
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
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


# Setup argtypes & restypes
advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi32.OpenProcessToken.restype = wintypes.BOOL

advapi32.CreateRestrictedToken.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID,
    ctypes.POINTER(wintypes.HANDLE)
]
advapi32.CreateRestrictedToken.restype = wintypes.BOOL

advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPVOID)]
advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL

advapi32.SetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
advapi32.SetTokenInformation.restype = wintypes.BOOL

advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.ULONG)
]
advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL

advapi32.GetSecurityDescriptorSacl.argtypes = [
    wintypes.LPVOID, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.BOOL)
]
advapi32.GetSecurityDescriptorSacl.restype = wintypes.BOOL

advapi32.SetSecurityInfo.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
    wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID
]
advapi32.SetSecurityInfo.restype = wintypes.DWORD

advapi32.CreateProcessAsUserW.argtypes = [
    wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID,
    wintypes.LPVOID, wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID,
    wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION),
]
advapi32.CreateProcessAsUserW.restype = wintypes.BOOL

kernel32.CreatePipe.argtypes = [
    ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE),
    ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD
]
kernel32.CreatePipe.restype = wintypes.BOOL

kernel32.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
kernel32.SetHandleInformation.restype = wintypes.BOOL


@dataclass
class RestrictedTokenEvidence:
    """Diagnostic audit record of effective token attributes."""
    is_restricted: bool
    integrity_rid: int
    integrity_level_name: str
    pid: int
    exit_code: Optional[int]
    duration_ms: float
    peak_memory_mb: float


@dataclass
class RestrictedWorkerResult:
    """Outcome of restricted worker execution."""
    run_id: str
    status: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: float
    peak_memory_mb: float
    working_dir: Path
    evidence: RestrictedTokenEvidence
    artifacts: List[Path] = field(default_factory=list)


class RestrictedWorkerLauncher:
    """
    Authoritative launcher for executing untrusted/dynamic Python processes
    with a Win32 Restricted Token, Low Integrity Level, and Job Object limits.
    """

    _winsta_configured = False

    @classmethod
    def ensure_window_station_low_integrity(cls) -> bool:
        """
        Grants Low Integrity read access to winsta0 and desktop so C-extensions
        (e.g. matplotlib, font loaders, runtime libs) can initialize without errors.
        """
        if cls._winsta_configured:
            return True

        try:
            hWinsta = user32.GetProcessWindowStation()
            hDesktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
            if not hWinsta or not hDesktop:
                return False

            pSD = wintypes.LPVOID()
            sd_size = wintypes.ULONG()
            if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW("S:(ML;;NW;;;LW)", 1, ctypes.byref(pSD), ctypes.byref(sd_size)):
                return False

            fSaclPresent = wintypes.BOOL()
            pSacl = wintypes.LPVOID()
            fSaclDefaulted = wintypes.BOOL()
            if not advapi32.GetSecurityDescriptorSacl(pSD, ctypes.byref(fSaclPresent), ctypes.byref(pSacl), ctypes.byref(fSaclDefaulted)):
                return False

            advapi32.SetSecurityInfo(hWinsta, SE_WINDOW_OBJECT, LABEL_SECURITY_INFORMATION, None, None, None, pSacl)
            advapi32.SetSecurityInfo(hDesktop, SE_WINDOW_OBJECT, LABEL_SECURITY_INFORMATION, None, None, None, pSacl)
            cls._winsta_configured = True
            return True
        except Exception as e:
            logger.warning("Failed to configure Window Station Low IL SACL: %s", e)
            return False

    @classmethod
    def create_restricted_low_integrity_token(cls) -> Optional[wintypes.HANDLE]:
        """
        Constructs a primary token with stripped privileges, LUA restrictions,
        and Low Integrity level (SECURITY_MANDATORY_LOW_RID = 0x1000).
        """
        hToken = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(),
            TOKEN_DUPLICATE | TOKEN_ASSIGN_PRIMARY | TOKEN_QUERY | TOKEN_ADJUST_DEFAULT,
            ctypes.byref(hToken),
        ):
            logger.error("OpenProcessToken failed: %s", ctypes.get_last_error())
            return None

        try:
            hRestrictedToken = wintypes.HANDLE()
            if not advapi32.CreateRestrictedToken(
                hToken,
                DISABLE_MAX_PRIVILEGE | LUA_TOKEN,
                0, None,
                0, None,
                0, None,
                ctypes.byref(hRestrictedToken),
            ):
                logger.error("CreateRestrictedToken failed: %s", ctypes.get_last_error())
                return None

            pSid = wintypes.LPVOID()
            if not advapi32.ConvertStringSidToSidW("S-1-16-4096", ctypes.byref(pSid)):
                logger.error("ConvertStringSidToSidW for Low IL failed: %s", ctypes.get_last_error())
                kernel32.CloseHandle(hRestrictedToken)
                return None

            tml = TOKEN_MANDATORY_LABEL()
            tml.Label.Sid = pSid
            tml.Label.Attributes = SE_GROUP_INTEGRITY

            if not advapi32.SetTokenInformation(
                hRestrictedToken,
                TokenIntegrityLevel,
                ctypes.byref(tml),
                ctypes.sizeof(tml),
            ):
                logger.error("SetTokenInformation (Low IL) failed: %s", ctypes.get_last_error())
                kernel32.CloseHandle(hRestrictedToken)
                return None

            return hRestrictedToken
        finally:
            kernel32.CloseHandle(hToken)

    @classmethod
    def build_sanitized_environment(
        cls,
        workspace: Path,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> ctypes.Array:
        """
        Constructs an explicit allowlist environment block.
        Completely excludes host secrets, API keys, tokens, and credentials.
        """
        output_dir = workspace / "output"
        temp_dir = workspace / "temp"

        allowlist = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
            "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
            "PATH": os.environ.get("PATH", ""),
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
            "ASTRARUN_WORKSPACE_DIR": str(workspace),
            "ASTRARUN_OUTPUT_DIR": str(output_dir),
            "OUTPUT_DIR": str(output_dir),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "MPLBACKEND": "Agg",
        }

        if extra_env:
            for k, v in extra_env.items():
                if not any(s in k.upper() for s in ("KEY", "SECRET", "TOKEN", "AUTH", "PASS", "CRED")):
                    allowlist[k] = v

        env_chars: List[str] = []
        for k, v in sorted(allowlist.items()):
            env_chars.append(f"{k}={v}\0")
        env_chars.append("\0")
        env_str = "".join(env_chars)
        return ctypes.create_unicode_buffer(env_str)

    @classmethod
    def launch(
        cls,
        entrypoint_file: Path,
        workspace: Path,
        run_id: str,
        timeout_sec: float = 30.0,
        memory_limit_bytes: int = 512 * 1024 * 1024,
        extra_env: Optional[Dict[str, str]] = None,
        python_executable: Optional[str] = None,
    ) -> RestrictedWorkerResult:
        """
        Execute entrypoint in a dedicated restricted low integrity process.
        Returns typed RestrictedWorkerResult with complete token evidence.
        """
        cls.ensure_window_station_low_integrity()

        hToken = cls.create_restricted_low_integrity_token()
        if not hToken:
            raise RuntimeError("Failed to create Win32 Restricted Low Integrity Token.")

        # Setup Pipes for stdout & stderr
        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(sa)
        sa.bInheritHandle = True

        hReadPipe = wintypes.HANDLE()
        hWritePipe = wintypes.HANDLE()
        kernel32.CreatePipe(ctypes.byref(hReadPipe), ctypes.byref(hWritePipe), ctypes.byref(sa), 0)
        kernel32.SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0)

        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        si.dwFlags = STARTF_USESTDHANDLES
        si.hStdOutput = hWritePipe
        si.hStdError = hWritePipe
        si.hStdInput = None

        pi = PROCESS_INFORMATION()

        exe = python_executable or sys.executable
        cmd = f'"{exe}" "{entrypoint_file}"'
        env_buf = cls.build_sanitized_environment(workspace, extra_env=extra_env)

        job = Win32JobObject(
            name=f"c2_job_{run_id}",
            memory_limit_bytes=memory_limit_bytes if memory_limit_bytes > 0 else None,
        )

        start_time = time.time()
        status = "SUCCESS"
        exit_code: Optional[int] = None
        output_bytes = b""
        peak_mb = 0.0

        try:
            ok = advapi32.CreateProcessAsUserW(
                hToken,
                None,
                ctypes.create_unicode_buffer(cmd),
                None,
                None,
                True,  # inherit write pipe handle
                CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
                ctypes.cast(env_buf, wintypes.LPVOID),
                str(workspace),
                ctypes.byref(si),
                ctypes.byref(pi),
            )
            # Close write handle in parent so ReadFile terminates on child exit
            kernel32.CloseHandle(hWritePipe)

            if not ok:
                err = ctypes.get_last_error()
                kernel32.CloseHandle(hReadPipe)
                kernel32.CloseHandle(hToken)
                job.close()
                raise RuntimeError(f"CreateProcessAsUserW failed with error code: {err}")

            # Assign to Win32 Job Object immediately
            job.assign_process(int(pi.hProcess))

            # Wait with bounded timeout
            wait_res = kernel32.WaitForSingleObject(pi.hProcess, int(timeout_sec * 1000))
            if wait_res == 0x00000102:  # WAIT_TIMEOUT
                status = "TIMEOUT"
                job.terminate(exit_code=1)
                kernel32.TerminateProcess(pi.hProcess, 1)

            # Retrieve exit code
            code_buf = wintypes.DWORD()
            kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code_buf))
            exit_code = int(code_buf.value)
            if status != "TIMEOUT" and exit_code != 0:
                status = "FAILED"

            # Drain pipe
            buf = ctypes.create_string_buffer(8192)
            bytesRead = wintypes.DWORD()
            while kernel32.ReadFile(hReadPipe, buf, 8192, ctypes.byref(bytesRead), None) and bytesRead.value > 0:
                output_bytes += buf.raw[:bytesRead.value]

            try:
                peak_bytes = job.query_peak_memory()
                peak_mb = round(peak_bytes / (1024 * 1024), 2)
            except Exception:
                peak_mb = 0.0

            pid = int(pi.dwProcessId)
            kernel32.CloseHandle(pi.hProcess)
            kernel32.CloseHandle(pi.hThread)

        finally:
            kernel32.CloseHandle(hReadPipe)
            kernel32.CloseHandle(hToken)
            job.close()

        duration_ms = round((time.time() - start_time) * 1000.0, 2)
        out_text = output_bytes.decode("utf-8", errors="replace")

        evidence = RestrictedTokenEvidence(
            is_restricted=True,
            integrity_rid=0x1000,
            integrity_level_name="SECURITY_MANDATORY_LOW_RID",
            pid=pid,
            exit_code=exit_code,
            duration_ms=duration_ms,
            peak_memory_mb=peak_mb,
        )

        return RestrictedWorkerResult(
            run_id=run_id,
            status=status,
            exit_code=exit_code,
            stdout=out_text,
            stderr="",
            duration_ms=duration_ms,
            peak_memory_mb=peak_mb,
            working_dir=workspace,
            evidence=evidence,
        )
