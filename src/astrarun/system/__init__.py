"""System capability module."""

from astrarun.system.service import (
    audio_status,
    battery_status,
    cpu_status,
    disk_status,
    gpu_status,
    lock_workstation,
    memory_status,
    system_summary,
)

__all__ = [
    "audio_status",
    "battery_status",
    "cpu_status",
    "disk_status",
    "gpu_status",
    "lock_workstation",
    "memory_status",
    "system_summary",
]
