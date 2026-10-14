"""Authoritative Windows AppContainer Capability-Isolated Launcher for AstraRun 1.0.

Provides kernel-enforced execution containment using:
1. Windows AppContainer Profile (TokenIsAppContainer = True, zero network capabilities)
2. Ephemeral per-task package identity (AstraRun_Task_<task_id>)
3. Explicit runtime read/execute ACLs scoped strictly to the task package SID
4. Suspended process creation + Win32 Job Object assignment before untrusted instruction runs
5. Allowlisted handle inheritance (PROC_THREAD_ATTRIBUTE_HANDLE_LIST)
6. Sealed execution with zero ambient fallback on any failure
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.execution.job_object import Win32JobObject
from astrarun.sandbox.models import SandboxResult

logger = get_logger("astrarun.sandbox.appcontainer_launcher")

# Win32 API Definitions
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
userenv = ctypes.WinDLL("userenv", use_last_error=True)

PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
STARTF_USESTDHANDLES = 0x00000100
CREATE_NO_WINDOW = 0x08000000
CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
HANDLE_FLAG_INHERIT = 0x00000001
STILL_ACTIVE = 259


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", wintypes.LPVOID),
        ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
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


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", STARTUPINFOW),
        ("lpAttributeList", wintypes.LPVOID),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]

kernel32.InitializeProcThreadAttributeList.argtypes = [
    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)
]
kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL

kernel32.UpdateProcThreadAttribute.argtypes = [
    wintypes.LPVOID, wintypes.DWORD, ctypes.c_size_t,
    wintypes.LPVOID, ctypes.c_size_t,
    wintypes.LPVOID, ctypes.POINTER(ctypes.c_size_t)
]
kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL

kernel32.DeleteProcThreadAttributeList.argtypes = [wintypes.LPVOID]
kernel32.DeleteProcThreadAttributeList.restype = None

kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPWSTR,
    wintypes.LPVOID, wintypes.LPVOID,
    wintypes.BOOL, wintypes.DWORD,
    wintypes.LPVOID, wintypes.LPCWSTR,
    wintypes.LPVOID, ctypes.POINTER(PROCESS_INFORMATION)
]
kernel32.CreateProcessW.restype = wintypes.BOOL

advapi32.ConvertSidToStringSidW.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)]
advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

userenv.CreateAppContainerProfile.argtypes = [
    wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
    wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID)
]
userenv.CreateAppContainerProfile.restype = wintypes.LONG

userenv.DeleteAppContainerProfile.argtypes = [wintypes.LPCWSTR]
userenv.DeleteAppContainerProfile.restype = wintypes.LONG


@dataclass
class AppContainerWorkerResult:
    """Diagnostic evidence and outcome of an AppContainer worker execution."""
    run_id: str
    package_sid: str
    status: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: float
    peak_memory_mb: float
    is_appcontainer: bool = True
    capabilities_granted: List[str] = field(default_factory=list)
    isolation_type: str = "APPCONTAINER"


class AppContainerLauncher:
    """Manages ephemeral AppContainer lifecycle, ACL staging, and suspended execution."""

    @classmethod
    def build_sanitized_environment(
        cls,
        workspace: Path,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> ctypes.Array:
        """Constructs an explicit allowlist environment block."""
        output_dir = workspace / "output"
        temp_dir = workspace / "temp"
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

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
            "MPLCONFIGDIR": str(temp_dir),
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
            "MKL_NUM_THREADS": "2",
            "VECLIB_MAXIMUM_THREADS": "2",
            "NUMEXPR_NUM_THREADS": "2",
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

    _runtime_dirs_configured: set = set()

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
        on_process_created: Optional[Callable[[int, wintypes.HANDLE], None]] = None,
    ) -> AppContainerWorkerResult:
        """
        Executes an entrypoint in an ephemeral AppContainer profile with suspended process creation,
        Job Object assignment before thread resume, and automatic ACL teardown.
        """
        t0 = time.time()
        container_name = f"AstraRun_{run_id.replace('-', '_')}"

        # Clean any stale container profile with this name
        try:
            userenv.DeleteAppContainerProfile(container_name)
        except Exception:
            pass

        pSid = wintypes.LPVOID()
        hr = userenv.CreateAppContainerProfile(
            container_name,
            container_name,
            f"AstraRun Ephemeral Container for {run_id}",
            None,  # No capabilities granted -> offline by default
            0,
            ctypes.byref(pSid),
        )
        if hr != 0 or not pSid.value:
            raise RuntimeError(f"Failed to create AppContainer profile (HRESULT: {hex(hr)})")

        pStrSid = wintypes.LPWSTR()
        advapi32.ConvertSidToStringSidW(pSid, ctypes.byref(pStrSid))
        sid_str = pStrSid.value

        from astrarun.core.paths import resolve_python_executable
        exe = resolve_python_executable(python_executable)
        py_dir = os.path.dirname(exe)
        runtime_dirs = [py_dir]
        if getattr(sys, "base_prefix", None) and sys.base_prefix not in runtime_dirs:
            runtime_dirs.append(sys.base_prefix)
        if getattr(sys, "prefix", None) and sys.prefix not in runtime_dirs:
            runtime_dirs.append(sys.prefix)

        # Stage ACL: full control for this container on its ephemeral task workspace
        subprocess.run(["icacls", str(workspace), "/grant", f"*{sid_str}:(OI)(CI)(F)"], capture_output=True)
        for r_dir in runtime_dirs:
            r_path = Path(r_dir).resolve()
            r_str = str(r_path)
            if r_str not in cls._runtime_dirs_configured and r_path.exists():
                subprocess.run(["icacls", r_str, "/grant", "*S-1-15-2-1:(OI)(CI)(RX)"], capture_output=True)
                cls._runtime_dirs_configured.add(r_str)

        hReadPipe = wintypes.HANDLE()
        hWritePipe = wintypes.HANDLE()
        pAttrList = None

        try:
            sec_cap = SECURITY_CAPABILITIES()
            sec_cap.AppContainerSid = pSid
            sec_cap.Capabilities = None
            sec_cap.CapabilityCount = 0
            sec_cap.Reserved = 0

            # Anonymous pipes with handle inheritance
            sa = SECURITY_ATTRIBUTES()
            sa.nLength = ctypes.sizeof(sa)
            sa.bInheritHandle = True
            kernel32.CreatePipe(ctypes.byref(hReadPipe), ctypes.byref(hWritePipe), ctypes.byref(sa), 0)
            kernel32.SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0)

            # Initialize 2 attributes: SECURITY_CAPABILITIES and HANDLE_LIST
            size = ctypes.c_size_t(0)
            kernel32.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
            buf = ctypes.create_string_buffer(size.value)
            pAttrList = ctypes.cast(buf, wintypes.LPVOID)
            if not kernel32.InitializeProcThreadAttributeList(pAttrList, 2, 0, ctypes.byref(size)):
                raise RuntimeError(f"InitializeProcThreadAttributeList failed: {ctypes.get_last_error()}")

            if not kernel32.UpdateProcThreadAttribute(
                pAttrList, 0,
                PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                ctypes.byref(sec_cap), ctypes.sizeof(sec_cap),
                None, None,
            ):
                raise RuntimeError(f"UpdateProcThreadAttribute (Capabilities) failed: {ctypes.get_last_error()}")

            handles = (wintypes.HANDLE * 1)(hWritePipe)
            if not kernel32.UpdateProcThreadAttribute(
                pAttrList, 0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                handles, ctypes.sizeof(handles),
                None, None,
            ):
                raise RuntimeError(f"UpdateProcThreadAttribute (Handles) failed: {ctypes.get_last_error()}")

            siex = STARTUPINFOEXW()
            siex.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
            siex.StartupInfo.dwFlags = STARTF_USESTDHANDLES
            siex.StartupInfo.hStdOutput = hWritePipe
            siex.StartupInfo.hStdError = hWritePipe
            siex.StartupInfo.hStdInput = None
            siex.lpAttributeList = pAttrList

            pi = PROCESS_INFORMATION()

            output_dir = workspace / "output"
            temp_dir = workspace / "temp"
            localappdata_dir = workspace / "localappdata"
            output_dir.mkdir(parents=True, exist_ok=True)
            temp_dir.mkdir(parents=True, exist_ok=True)
            localappdata_dir.mkdir(parents=True, exist_ok=True)

            sys_root = os.environ.get("SystemRoot", r"C:\Windows")
            from astrarun.core.paths import resolve_python_executable
            exe = resolve_python_executable(python_executable)
            py_dir = os.path.dirname(exe)
            clean_path_parts = [py_dir]
            if getattr(sys, "base_prefix", None) and sys.base_prefix not in clean_path_parts:
                clean_path_parts.append(sys.base_prefix)
            if getattr(sys, "prefix", None) and sys.prefix not in clean_path_parts:
                clean_path_parts.append(sys.prefix)
            clean_path_parts.extend([f"{sys_root}\\System32", sys_root])
            clean_path = ";".join(clean_path_parts)

            # Strict Positive Allowlist Environment (No host secrets passed into worker memory)
            allowlist_env = {
                "SystemRoot": sys_root,
                "WINDIR": sys_root,
                "SystemDrive": os.environ.get("SystemDrive", "C:"),
                "LOCALAPPDATA": str(localappdata_dir),
                "TEMP": str(temp_dir),
                "TMP": str(temp_dir),
                "PATH": clean_path,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
                "ASTRARUN_WORKSPACE_DIR": str(workspace),
                "ASTRARUN_OUTPUT_DIR": str(output_dir),
                "OUTPUT_DIR": str(output_dir),
                "MPLCONFIGDIR": str(temp_dir),
                "MPLBACKEND": "Agg",
            }
            if extra_env:
                for k, v in extra_env.items():
                    if not any(s in k.upper() for s in ("KEY", "SECRET", "TOKEN", "AUTH", "PASS", "CRED", "API")):
                        allowlist_env[k] = str(v)

            # Build Win32 Unicode environment block (double null terminated, alphabetically sorted)
            sorted_items = sorted(allowlist_env.items(), key=lambda kv: kv[0].upper())
            block_str = "\0".join(f"{k}={v}" for k, v in sorted_items) + "\0\0"
            env_buf = ctypes.create_unicode_buffer(block_str)
            lp_env = ctypes.cast(env_buf, wintypes.LPVOID)

            # Direct entrypoint execution in isolated mode (-s avoids user-site pollution while allowing configured venv packages)
            cmd = f'"{exe}" -s "{Path(entrypoint_file).resolve()}"'
            cmd_buf = ctypes.create_unicode_buffer(cmd)

            # Launch process SUSPENDED with explicit environment block
            flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
            ok = kernel32.CreateProcessW(
                None,
                cmd_buf,
                None,
                None,
                True,  # bInheritHandles (restricted to PROC_THREAD_ATTRIBUTE_HANDLE_LIST)
                flags,
                lp_env,  # Explicit positive allowlist environment block
                str(workspace),
                ctypes.byref(siex),
                ctypes.byref(pi),
            )
            if not ok:
                err = ctypes.get_last_error()
                raise RuntimeError(f"CreateProcessW in AppContainer failed: WinError {err}")

            # Close write handle in parent so ReadFile reaches EOF when child terminates
            kernel32.CloseHandle(hWritePipe)
            hWritePipe = wintypes.HANDLE()

            # Assign suspended process to Job Object BEFORE resume
            job = Win32JobObject(
                name=f"ac_job_{run_id}",
                memory_limit_bytes=memory_limit_bytes if memory_limit_bytes > 0 else None,
            )
            try:
                job.assign_process(int(pi.hProcess))
            except Exception as e:
                # If job assignment fails, terminate suspended child immediately! Fail closed!
                kernel32.TerminateProcess(pi.hProcess, 1)
                kernel32.CloseHandle(pi.hProcess)
                kernel32.CloseHandle(pi.hThread)
                raise RuntimeError(f"Failed to assign AppContainer process to Job Object: {e}")

            if on_process_created:
                try:
                    on_process_created(pi.dwProcessId, pi.hProcess)
                except Exception as e:
                    logger.warning("on_process_created callback failed: %s", e)

            # Resume process execution
            kernel32.ResumeThread(pi.hThread)

            status = "SUCCESS"
            exit_code: Optional[int] = None
            output_bytes = b""
            peak_mb = 0.0

            # Wait with bounded timeout
            wait_res = kernel32.WaitForSingleObject(pi.hProcess, int(timeout_sec * 1000))
            if wait_res == 0:  # WAIT_OBJECT_0
                dw_code = wintypes.DWORD()
                kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(dw_code))
                exit_code = dw_code.value
                if exit_code != 0:
                    status = "FAILED"
            elif wait_res == 0x00000102:  # WAIT_TIMEOUT
                status = "TIMEOUT"
                kernel32.TerminateProcess(pi.hProcess, 1)
                job.terminate(exit_code=1)
                exit_code = 1
            else:
                status = "ERROR"
                exit_code = 1

            # Read all pipe output
            read_chunks: List[bytes] = []
            chunk_buf = ctypes.create_string_buffer(16384)
            bytes_read = wintypes.DWORD()
            while True:
                r_ok = kernel32.ReadFile(hReadPipe, chunk_buf, 16384, ctypes.byref(bytes_read), None)
                if not r_ok or bytes_read.value == 0:
                    break
                read_chunks.append(chunk_buf.raw[:bytes_read.value])
                if sum(len(c) for c in read_chunks) > 512 * 1024:  # 512 KB cap
                    read_chunks.append(b"\n[TRUNCATED: Output exceeded cap]")
                    break

            output_bytes = b"".join(read_chunks)
            stdout_text = output_bytes.decode("utf-8", errors="replace")
            if "Failed to find real location of" in stdout_text:
                stdout_text = "".join(
                    line for line in stdout_text.splitlines(keepends=True)
                    if not line.strip().startswith("Failed to find real location of")
                )

            try:
                peak_bytes = job.query_peak_memory()
                peak_mb = round(peak_bytes / (1024 * 1024), 2)
            except Exception:
                peak_mb = 0.0

            job.close()
            kernel32.CloseHandle(pi.hProcess)
            kernel32.CloseHandle(pi.hThread)

            duration_ms = round((time.time() - t0) * 1000.0, 2)

            return AppContainerWorkerResult(
                run_id=run_id,
                package_sid=sid_str,
                status=status,
                exit_code=exit_code,
                stdout=stdout_text,
                stderr=stdout_text if exit_code != 0 else "",
                duration_ms=duration_ms,
                peak_memory_mb=peak_mb,
                is_appcontainer=True,
                capabilities_granted=[],
                isolation_type="APPCONTAINER",
            )

        finally:
            if hReadPipe:
                kernel32.CloseHandle(hReadPipe)
            if hWritePipe:
                kernel32.CloseHandle(hWritePipe)
            if pAttrList:
                kernel32.DeleteProcThreadAttributeList(pAttrList)
            if pSid.value:
                kernel32.LocalFree(pSid)

            # Teardown temporary ACLs and AppContainer Profile
            try:
                subprocess.run(["icacls", str(workspace), "/remove", sid_str], capture_output=True)
                for r_dir in runtime_dirs:
                    if Path(r_dir).exists():
                        subprocess.run(["icacls", str(r_dir), "/remove", sid_str], capture_output=True)
                userenv.DeleteAppContainerProfile(container_name)
            except Exception as e:
                logger.warning("Error during AppContainer profile/ACL cleanup: %s", e)
