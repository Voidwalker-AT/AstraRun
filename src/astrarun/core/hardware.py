"""Hardware Inspection and System Profile Detection for AstraRun 1.0."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.core.hardware")


@dataclass
class HardwareProfile:
    """Captured host machine hardware specifications."""
    os_name: str
    os_version: str
    cpu_name: str
    cpu_cores: int
    ram_gb: float
    gpu_name: str
    vram_gb: float
    has_cuda: bool
    disk_free_gb: float

    @property
    def supports_gpu_inference(self) -> bool:
        """Return True if GPU has at least 3.5 GB VRAM and CUDA support."""
        return self.has_cuda and self.vram_gb >= 3.5

    @property
    def supports_standard_pack(self) -> bool:
        """Return True if system meets standard cognitive pack requirements (>= 12 GB RAM)."""
        return self.ram_gb >= 11.5


def audit_hardware() -> HardwareProfile:
    """Perform a passive, non-intrusive inspection of host system hardware."""
    os_name = f"Windows {platform.release()}" if sys.platform == "win32" else platform.system()
    os_version = platform.version()
    cpu_cores = os.cpu_count() or 4
    cpu_name = platform.processor() or "x86_64 Processor"

    # 1. Physical RAM
    ram_gb = 16.0
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024.0 ** 3), 1)
    except Exception as e:
        logger.debug("psutil RAM query failed: %s", e)

    # 2. GPU and VRAM
    gpu_name = "Integrated / Software Graphics"
    vram_gb = 0.0
    has_cuda = False

    try:
        import torch
        if torch.cuda.is_available():
            has_cuda = True
            gpu_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_gb = round(props.total_memory / (1024.0 ** 3), 1)
    except Exception:
        # Fallback to WMI / PowerShell query on Windows if torch is not yet imported
        if sys.platform == "win32":
            try:
                import subprocess
                cmd = "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name, AdapterRAM"
                res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=3)
                for line in res.stdout.splitlines():
                    if "RTX" in line or "NVIDIA" in line or "GeForce" in line:
                        gpu_name = line.strip()
                        has_cuda = True
                        vram_gb = 4.0  # RTX 2050 typical
            except Exception:
                pass

    # 3. Available Disk Space
    disk_free_gb = 50.0
    try:
        total, used, free = shutil.disk_usage(os.environ.get("LOCALAPPDATA", "C:\\"))
        disk_free_gb = round(free / (1024.0 ** 3), 1)
    except Exception:
        pass

    profile = HardwareProfile(
        os_name=os_name,
        os_version=os_version,
        cpu_name=cpu_name,
        cpu_cores=cpu_cores,
        ram_gb=ram_gb,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        has_cuda=has_cuda,
        disk_free_gb=disk_free_gb,
    )
    logger.info("Hardware profile audited: RAM=%.1fGB, GPU='%s' (%.1fGB VRAM), Disk=%.1fGB free",
                profile.ram_gb, profile.gpu_name, profile.vram_gb, profile.disk_free_gb)
    return profile
