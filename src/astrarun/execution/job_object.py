"""Native Win32 Job Object containment for AstraRun 1.0.

Provides deterministic process tree containment using JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
enforcing memory quotas and ensuring zero orphaned background processes.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from typing import Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.execution.job_object")

# Win32 Constants
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800

JobObjectBasicAccountingInformation = 1
JobObjectExtendedLimitInformation = 9


if os.name == "nt":
    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", wintypes.ULARGE_INTEGER),
            ("WriteOperationCount", wintypes.ULARGE_INTEGER),
            ("OtherOperationCount", wintypes.ULARGE_INTEGER),
            ("ReadTransferCount", wintypes.ULARGE_INTEGER),
            ("WriteTransferCount", wintypes.ULARGE_INTEGER),
            ("OtherTransferCount", wintypes.ULARGE_INTEGER),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.windll.kernel32

    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE

    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL

    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL

    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL


class Win32JobObject:
    """
    Win32 Job Object wrapper providing automatic descendant tree cleanup.
    Strictly restricted to AstraRun-created process trees.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        memory_limit_bytes: Optional[int] = None,
    ) -> None:
        self.name = name
        self.memory_limit_bytes = memory_limit_bytes
        self._handle: Optional[int] = None
        self._is_closed = False

        if os.name == "nt":
            self._init_win32_job()

    def _init_win32_job(self) -> None:
        """Create and configure native Win32 Job Object."""
        self._handle = kernel32.CreateJobObjectW(None, self.name)
        if not self._handle:
            err = ctypes.GetLastError()
            logger.error("Failed to create Win32 JobObject (WinError %d)", err)
            raise OSError(f"Failed to create JobObject (WinError {err})")

        # Configure Limits: KILL_ON_JOB_CLOSE is mandatory
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK

        if self.memory_limit_bytes and self.memory_limit_bytes > 0:
            limit_flags |= JOB_OBJECT_LIMIT_JOB_MEMORY
            info.JobMemoryLimit = ctypes.c_size_t(self.memory_limit_bytes)

        info.BasicLimitInformation.LimitFlags = limit_flags

        success = kernel32.SetInformationJobObject(
            self._handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not success:
            err = ctypes.GetLastError()
            logger.error("Failed to set JobObject extended limits (WinError %d)", err)
            kernel32.CloseHandle(self._handle)
            self._handle = None
            raise OSError(f"Failed to set JobObject limits (WinError {err})")

        logger.debug(
            "Initialized Win32 JobObject [handle=%s, kill_on_close=True, mem_limit=%s]",
            self._handle,
            self.memory_limit_bytes,
        )

    @property
    def handle(self) -> Optional[int]:
        return self._handle

    @property
    def is_valid(self) -> bool:
        return self._handle is not None and not self._is_closed

    def assign_process(self, process_handle: int) -> bool:
        """
        Assign a native process handle to this Job Object.
        INVARIANT: Only AstraRun-spawned worker processes may be assigned.
        """
        if os.name != "nt" or not self.is_valid:
            return False

        success = kernel32.AssignProcessToJobObject(self._handle, process_handle)
        if not success:
            err = ctypes.GetLastError()
            logger.error("Failed to assign process %s to JobObject (WinError %d)", process_handle, err)
            return False

        logger.debug("Assigned process handle %s to JobObject", process_handle)
        return True

    def query_peak_memory(self) -> int:
        """Query peak physical memory used by the entire job object tree in bytes."""
        if os.name != "nt" or not self.is_valid:
            return 0

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        return_len = wintypes.DWORD(0)
        success = kernel32.QueryInformationJobObject(
            self._handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(return_len),
        )
        if success:
            return int(info.PeakJobMemoryUsed)
        return 0

    def terminate(self, exit_code: int = 1) -> bool:
        """
        Immediately terminate all processes currently in the Job Object.
        """
        if os.name != "nt" or not self.is_valid:
            return False

        success = kernel32.TerminateJobObject(self._handle, exit_code)
        if not success:
            err = ctypes.GetLastError()
            logger.warning("TerminateJobObject failed (WinError %d)", err)
            return False

        logger.info("Terminated all processes in JobObject (exit_code=%d)", exit_code)
        return True

    def close(self) -> None:
        """
        Close the Job Object handle.
        If processes are still running, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE triggers automatic termination.
        """
        if self._handle and not self._is_closed and os.name == "nt":
            kernel32.CloseHandle(self._handle)
            logger.debug("Closed JobObject handle %s", self._handle)
            self._handle = None
            self._is_closed = True

    def __enter__(self) -> Win32JobObject:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
