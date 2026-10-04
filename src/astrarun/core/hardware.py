"""Hardware Inspection and System Profile Detection for AstraRun 1.0."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.core.hardware")


@dataclass
class GpuDevice:
    """Detailed specification for an individual GPU / display adapter."""
    index: int
    name: str
    vendor: str  # "NVIDIA", "Intel", "AMD", "Generic"
    vram_gb: float
    is_discrete: bool
    has_cuda: bool
    is_integrated: bool
    driver_version: str = ""
    status_summary: str = ""

    @property
    def display_label(self) -> str:
        """Formatted label for UI and CLI displays."""
        if self.is_discrete and self.has_cuda:
            return f"{self.name} - {self.vram_gb:.1f} GB VRAM (Local AI acceleration available)"
        if self.is_integrated:
            return f"{self.name} - Integrated"
        return f"{self.name} - {self.vram_gb:.1f} GB VRAM"


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
    gpus: List[GpuDevice] = field(default_factory=list)
    preferred_compute_gpu: Optional[GpuDevice] = None

    @property
    def supports_gpu_inference(self) -> bool:
        """Return True if GPU has at least 3.5 GB VRAM and CUDA support."""
        return self.has_cuda and self.vram_gb >= 3.5

    @property
    def supports_standard_pack(self) -> bool:
        """Return True if system meets standard cognitive pack requirements (>= 12 GB RAM)."""
        return self.ram_gb >= 11.5


def audit_hardware() -> HardwareProfile:
    """Perform a passive, non-intrusive inspection of host system hardware with multi-GPU discovery."""
    os_name = f"Windows {platform.release()}" if sys.platform == "win32" else platform.system()
    os_version = platform.version()
    cpu_cores = os.cpu_count() or 4
    cpu_name = platform.processor() or "x86_64 Processor"
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                reg_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                if reg_name and str(reg_name).strip():
                    cpu_name = str(reg_name).strip()
        except Exception as e:
            logger.debug("Registry CPU query fallback: %s", e)

    # 1. Physical RAM
    ram_gb = 16.0
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024.0 ** 3), 1)
    except Exception as e:
        logger.debug("psutil RAM query failed: %s", e)

    # 2. Comprehensive Multi-GPU Discovery
    detected_gpus: List[GpuDevice] = []

    # Source A: nvidia-smi (authoritative for NVIDIA discrete GPUs)
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            import subprocess
            cmd = [
                nvidia_smi,
                "--query-gpu=index,name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ]
            res = subprocess.run(
                cmd, capture_output=True, text=True, timeout=2.5,
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        idx = int(parts[0]) if parts[0].isdigit() else len(detected_gpus)
                        name = parts[1]
                        vram_mb = float(parts[2]) if parts[2].replace(".", "").isdigit() else 0.0
                        driver = parts[3] if len(parts) > 3 else ""
                        detected_gpus.append(GpuDevice(
                            index=idx,
                            name=name,
                            vendor="NVIDIA",
                            vram_gb=round(vram_mb / 1024.0, 1),
                            is_discrete=True,
                            has_cuda=True,
                            is_integrated=False,
                            driver_version=driver,
                            status_summary=f"{name} (4 GB VRAM, Local AI acceleration available)",
                        ))
        except Exception as e:
            logger.debug("nvidia-smi audit failed: %s", e)

    # Source B: WMI Win32_VideoController (all adapters on Windows)
    if sys.platform == "win32":
        try:
            import subprocess
            cmd = "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=3.5,
                creationflags=0x08000000,
            )
            if res.returncode == 0:
                existing_names = [g.name.lower() for g in detected_gpus]
                lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
                for name in lines:
                    is_nvidia = any(k in name.lower() for k in ("nvidia", "geforce", "rtx", "quadro"))
                    is_intel = any(k in name.lower() for k in ("intel", "uhd", "iris", "arc"))
                    is_amd = any(k in name.lower() for k in ("amd", "radeon"))

                    if not name or any(name.lower() in en or en in name.lower() for en in existing_names):
                        continue

                    # Classify
                    vendor = "Intel" if is_intel else ("NVIDIA" if is_nvidia else ("AMD" if is_amd else "Generic"))
                    is_integ = is_intel or ("radeon graphics" in name.lower() and not "rx" in name.lower())
                    is_disc = not is_integ
                    has_cu = is_nvidia
                    vram_est = 4.0 if is_nvidia else (0.0 if is_integ else 2.0)

                    detected_gpus.append(GpuDevice(
                        index=len(detected_gpus),
                        name=name,
                        vendor=vendor,
                        vram_gb=vram_est,
                        is_discrete=is_disc,
                        has_cuda=has_cu,
                        is_integrated=is_integ,
                        driver_version="",
                        status_summary=f"{name} ({'Integrated' if is_integ else f'{vram_est:.0f} GB VRAM'})",
                    ))
        except Exception as e:
            logger.debug("Win32_VideoController query failed: %s", e)

    # Source C: PyTorch CUDA if available and no NVIDIA found yet
    if not any(g.has_cuda for g in detected_gpus):
        try:
            import torch
            if torch.cuda.is_available():
                for i in range(torch.cuda.device_count()):
                    name = torch.cuda.get_device_name(i)
                    props = torch.cuda.get_device_properties(i)
                    vram = round(props.total_memory / (1024.0 ** 3), 1)
                    detected_gpus.append(GpuDevice(
                        index=i,
                        name=name,
                        vendor="NVIDIA",
                        vram_gb=vram,
                        is_discrete=True,
                        has_cuda=True,
                        is_integrated=False,
                        driver_version="",
                        status_summary=f"{name} ({vram:.1f} GB VRAM, CUDA Available)",
                    ))
        except Exception:
            pass

    # Resolve preferred compute GPU
    preferred_gpu: Optional[GpuDevice] = None
    # 1. Discrete GPU with CUDA (e.g. RTX 2050)
    for g in detected_gpus:
        if g.is_discrete and g.has_cuda:
            preferred_gpu = g
            break
    # 2. Any discrete GPU
    if not preferred_gpu:
        for g in detected_gpus:
            if g.is_discrete:
                preferred_gpu = g
                break
    # 3. Any detected GPU
    if not preferred_gpu and detected_gpus:
        preferred_gpu = detected_gpus[0]

    if preferred_gpu:
        gpu_name = preferred_gpu.name
        vram_gb = preferred_gpu.vram_gb
        has_cuda = preferred_gpu.has_cuda
    else:
        gpu_name = "Integrated / Software Graphics"
        vram_gb = 0.0
        has_cuda = False

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
        gpus=detected_gpus,
        preferred_compute_gpu=preferred_gpu,
    )
    logger.info(
        "Hardware profile audited: RAM=%.1fGB, Preferred GPU='%s' (%.1fGB VRAM, CUDA=%s), Total GPUs=%d, Disk=%.1fGB free",
        profile.ram_gb, profile.gpu_name, profile.vram_gb, profile.has_cuda, len(profile.gpus), profile.disk_free_gb
    )
    return profile
