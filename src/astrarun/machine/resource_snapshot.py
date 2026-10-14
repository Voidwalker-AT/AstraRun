"""Instantaneous hardware resource telemetry snapshot for AstraRun 1.0.

Provides fast, synchronous resource telemetry (<15ms latency) to feed
ModelResidencyManager, DynamicToolBuilder, and the Planner.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

import psutil

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.machine.resource_snapshot")


@dataclass
class ResourceSnapshot:
    """Instantaneous snapshot of system resource utilization."""
    timestamp: float = field(default_factory=time.time)
    cpu_percent: float = 0.0
    total_ram_gb: float = 0.0
    available_ram_gb: float = 0.0
    ram_used_percent: float = 0.0
    commit_pressure_percent: float = 0.0
    total_vram_gb: float = 0.0
    free_vram_gb: float = 0.0
    gpu_utilization_percent: float = 0.0
    disk_free_gb: Dict[str, float] = field(default_factory=dict)
    power_plugged: bool = True
    battery_percent: Optional[float] = None
    network_connected: bool = True

    @property
    def has_cuda_gpu(self) -> bool:
        return self.total_vram_gb > 0.0

    @property
    def is_low_ram(self) -> bool:
        """True if available RAM is under 2.5 GB."""
        return self.available_ram_gb < 2.5

    @property
    def is_low_vram(self) -> bool:
        """True if free VRAM is under 0.8 GB."""
        return self.has_cuda_gpu and self.free_vram_gb < 0.8

    def can_fit_model_vram(self, required_vram_gb: float, safety_margin_gb: float = 0.4) -> bool:
        """Evaluate if required VRAM can fit with safe margin."""
        if not self.has_cuda_gpu:
            return False
        return self.free_vram_gb >= (required_vram_gb + safety_margin_gb)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ResourceSnapshot:
        return cls(**data)

    @classmethod
    def capture(cls, include_gpu: bool = True) -> ResourceSnapshot:
        """Capture instantaneous resource snapshot synchronously."""
        t0 = time.perf_counter()
        now = time.time()

        # 1. CPU (non-blocking instant percent)
        cpu_pct = psutil.cpu_percent(interval=None)

        # 2. RAM & Swap
        vm = psutil.virtual_memory()
        total_ram = round(vm.total / (1024 ** 3), 2)
        avail_ram = round(vm.available / (1024 ** 3), 2)
        ram_pct = vm.percent

        swap = psutil.swap_memory()
        commit_pct = swap.percent

        # 3. Storage Free per Drive
        disk_free: Dict[str, float] = {}
        try:
            partitions = psutil.disk_partitions(all=False)
            mounts = [p.mountpoint for p in partitions if p.mountpoint]
        except Exception:
            mounts = ["C:\\"]
        for mount in mounts:
            try:
                u = psutil.disk_usage(mount)
                drive_key = mount[0].upper()
                disk_free[drive_key] = round(u.free / (1024 ** 3), 2)
            except Exception:
                pass

        # 4. Power
        power_plugged = True
        battery_pct = None
        try:
            b = psutil.sensors_battery()
            if b:
                power_plugged = b.power_plugged
                battery_pct = b.percent
        except Exception:
            pass

        # 5. Network Connectivity
        net_connected = True
        try:
            stats = psutil.net_if_stats()
            net_connected = any(s.isup and "loopback" not in iface.lower() for iface, s in stats.items())
        except Exception:
            pass

        # 6. GPU & VRAM
        total_vram = 0.0
        free_vram = 0.0
        gpu_util = 0.0

        if include_gpu:
            # 6a. Try NVML via ctypes for instant (<0.2ms) zero-overhead reading
            try:
                import ctypes
                class _NVMLMemory(ctypes.Structure):
                    _fields_ = [
                        ("total", ctypes.c_ulonglong),
                        ("free", ctypes.c_ulonglong),
                        ("used", ctypes.c_ulonglong),
                    ]
                nvml = ctypes.CDLL("nvml.dll")
                nvml.nvmlInit_v2()
                handle = ctypes.c_void_p()
                if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) == 0:
                    mem = _NVMLMemory()
                    if nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem)) == 0:
                        total_vram = round(mem.total / (1024 ** 3), 2)
                        free_vram = round(mem.free / (1024 ** 3), 2)
            except Exception:
                pass

            # 6b. Fallback to PyTorch CUDA if NVML was unavailable
            if total_vram == 0.0:
                try:
                    import torch
                    if torch.cuda.is_available():
                        free_b, total_b = torch.cuda.mem_get_info(0)
                        free_vram = round(free_b / (1024 ** 3), 2)
                        total_vram = round(total_b / (1024 ** 3), 2)
                except Exception:
                    pass

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        logger.debug("ResourceSnapshot captured in %sms: RAM=%.1f/%.1fGB, VRAM=%.1f/%.1fGB",
                     latency_ms, avail_ram, total_ram, free_vram, total_vram)

        return cls(
            timestamp=now,
            cpu_percent=cpu_pct,
            total_ram_gb=total_ram,
            available_ram_gb=avail_ram,
            ram_used_percent=ram_pct,
            commit_pressure_percent=commit_pct,
            total_vram_gb=total_vram,
            free_vram_gb=free_vram,
            gpu_utilization_percent=gpu_util,
            disk_free_gb=disk_free,
            power_plugged=power_plugged,
            battery_percent=battery_pct,
            network_connected=net_connected,
        )
