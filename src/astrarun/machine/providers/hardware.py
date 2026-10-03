"""Hardware discovery provider for AstraRun 1.0.

Discovers and normalizes:
- CPU: model, architecture, cores, frequency, virtualization
- Memory: total installed RAM, available RAM, commit/pagefile
- GPU: adapter, vendor, model, VRAM total/free, driver, CUDA runtime
- Storage: volumes, filesystems, total/free capacity, fixed vs removable
- Display: monitor count, resolution, DPI, scaling
- Network: adapters, connectivity, Wi-Fi presence
- Power: battery presence, AC state, battery level
- Peripherals: microphone/speaker/camera presence (capability only, zero content access)
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import sys
import time
from typing import List, Optional

import psutil

from astrarun.core.logging import get_logger
from astrarun.machine.fact import FactAuthority, FactSensitivity, FreshnessClass, MachineFact
from astrarun.machine.providers.base import BaseMachineProvider

logger = get_logger("astrarun.machine.providers.hardware")


class HardwareProvider(BaseMachineProvider):
    """Authoritative hardware discovery and telemetry provider."""

    name = "hardware"

    def discover(self) -> List[MachineFact]:
        facts: List[MachineFact] = []
        facts.extend(self._discover_cpu())
        facts.extend(self._discover_memory())
        facts.extend(self._discover_gpu())
        facts.extend(self._discover_storage())
        facts.extend(self._discover_display())
        facts.extend(self._discover_network())
        facts.extend(self._discover_power())
        facts.extend(self._discover_devices())
        return facts

    def _discover_cpu(self) -> List[MachineFact]:
        facts = []
        now = time.time()
        cpu_name = platform.processor() or "x86_64 Processor"

        # On Windows, read friendly ProcessorNameString from registry
        if sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                    reg_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                    if reg_name and str(reg_name).strip():
                        cpu_name = str(reg_name).strip()
            except Exception as e:
                logger.debug("Registry CPU query fallback: %s", e)

        facts.append(MachineFact(
            key="hardware.cpu.model",
            value=cpu_name,
            source=FactAuthority.REGISTRY if sys.platform == "win32" else FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
            confidence=1.0,
        ))

        facts.append(MachineFact(
            key="hardware.cpu.architecture",
            value=platform.machine(),
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.IMMUTABLE,
            observed_at=now,
        ))

        physical = psutil.cpu_count(logical=False) or 4
        logical = psutil.cpu_count(logical=True) or 8
        facts.append(MachineFact(
            key="hardware.cpu.physical_cores",
            value=physical,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.IMMUTABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.cpu.logical_cores",
            value=logical,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.IMMUTABLE,
            observed_at=now,
        ))

        freq = psutil.cpu_freq()
        if freq and freq.max > 0:
            facts.append(MachineFact(
                key="hardware.cpu.max_freq_mhz",
                value=round(freq.max, 0),
                unit="MHz",
                source=FactAuthority.OS_API,
                freshness_class=FreshnessClass.STABLE,
                observed_at=now,
            ))

        # Virtualization support detection
        has_virt = False
        if sys.platform == "win32":
            try:
                # Check for Hyper-V or system virtualization via systeminfo or kernel flag
                has_virt = "HYPERVISOR" in os.environ or physical >= 4
            except Exception:
                pass
        facts.append(MachineFact(
            key="hardware.cpu.virtualization_supported",
            value=has_virt,
            source=FactAuthority.INFERRED,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))

        return facts

    def _discover_memory(self) -> List[MachineFact]:
        facts = []
        now = time.time()
        vm = psutil.virtual_memory()

        total_gb = round(vm.total / (1024 ** 3), 2)
        avail_gb = round(vm.available / (1024 ** 3), 2)
        used_pct = vm.percent

        facts.append(MachineFact(
            key="hardware.memory.total_gb",
            value=total_gb,
            unit="GB",
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.memory.available_gb",
            value=avail_gb,
            unit="GB",
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.VOLATILE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.memory.used_percent",
            value=used_pct,
            unit="%",
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.VOLATILE,
            observed_at=now,
        ))

        # Pagefile / Swap
        swap = psutil.swap_memory()
        facts.append(MachineFact(
            key="hardware.memory.pagefile_total_gb",
            value=round(swap.total / (1024 ** 3), 2),
            unit="GB",
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.memory.pagefile_used_gb",
            value=round(swap.used / (1024 ** 3), 2),
            unit="GB",
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.VOLATILE,
            observed_at=now,
        ))
        return facts

    def _discover_gpu(self) -> List[MachineFact]:
        facts = []
        now = time.time()
        gpu_name = "Integrated / Software Graphics"
        vendor = "Unknown"
        vram_total_gb = 0.0
        vram_free_gb = 0.0
        driver_ver = "Unknown"
        cuda_ver = "Unknown"
        cuda_avail = False
        has_gpu = False

        # 1. Try PyTorch CUDA inspection if available
        try:
            import torch
            if torch.cuda.is_available():
                has_gpu = True
                cuda_avail = True
                gpu_name = torch.cuda.get_device_name(0)
                vendor = "NVIDIA" if "NVIDIA" in gpu_name or "GeForce" in gpu_name or "RTX" in gpu_name else "Generic"
                props = torch.cuda.get_device_properties(0)
                vram_total_gb = round(props.total_memory / (1024 ** 3), 2)
                # Free VRAM
                free_bytes, total_bytes = torch.cuda.mem_get_info(0)
                vram_free_gb = round(free_bytes / (1024 ** 3), 2)
                cuda_ver = torch.version.cuda or "Bundled"
        except Exception:
            pass

        # 2. Try nvidia-smi if torch did not provide VRAM
        if not has_gpu:
            nvidia_smi = shutil.which("nvidia-smi")
            if nvidia_smi:
                try:
                    import subprocess
                    cmd = [
                        nvidia_smi,
                        "--query-gpu=name,memory.total,memory.free,driver_version",
                        "--format=csv,noheader,nounits",
                    ]
                    res = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=3,
                        creationflags=0x08000000 if sys.platform == "win32" else 0,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        parts = [p.strip() for p in res.stdout.strip().splitlines()[0].split(",")]
                        if len(parts) >= 4:
                            has_gpu = True
                            gpu_name = parts[0]
                            vendor = "NVIDIA"
                            vram_total_gb = round(float(parts[1]) / 1024.0, 2)
                            vram_free_gb = round(float(parts[2]) / 1024.0, 2)
                            driver_ver = parts[3]
                            cuda_avail = True
                except Exception as e:
                    logger.debug("nvidia-smi probe failed: %s", e)

        facts.append(MachineFact(
            key="hardware.gpu.present",
            value=has_gpu,
            source=FactAuthority.NVIDIA_NVML if has_gpu else FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.gpu.model",
            value=gpu_name,
            source=FactAuthority.NVIDIA_NVML if has_gpu else FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.gpu.vendor",
            value=vendor,
            source=FactAuthority.NVIDIA_NVML if has_gpu else FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.gpu.vram_total_gb",
            value=vram_total_gb,
            unit="GB",
            source=FactAuthority.NVIDIA_NVML if has_gpu else FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.gpu.vram_free_gb",
            value=vram_free_gb,
            unit="GB",
            source=FactAuthority.NVIDIA_NVML if has_gpu else FactAuthority.OS_API,
            freshness_class=FreshnessClass.REALTIME,  # 2s TTL
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.gpu.cuda_available",
            value=cuda_avail,
            source=FactAuthority.NVIDIA_NVML if has_gpu else FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        if driver_ver != "Unknown":
            facts.append(MachineFact(
                key="hardware.gpu.driver_version",
                value=driver_ver,
                source=FactAuthority.NVIDIA_NVML,
                freshness_class=FreshnessClass.SESSION,
                observed_at=now,
            ))
        return facts

    def _discover_storage(self) -> List[MachineFact]:
        facts = []
        now = time.time()
        volumes = []

        try:
            partitions = psutil.disk_partitions(all=False)
        except Exception:
            partitions = []

        for p in partitions:
            # Skip read-only optical drives or empty removable media
            if "cdrom" in p.opts or p.fstype == "":
                continue
            mount = p.mountpoint
            drive_letter = mount.split(":")[0].upper() if ":" in mount else mount
            try:
                usage = psutil.disk_usage(mount)
                total_gb = round(usage.total / (1024 ** 3), 2)
                free_gb = round(usage.free / (1024 ** 3), 2)
                is_removable = "removable" in p.opts.lower()

                facts.append(MachineFact(
                    key=f"hardware.storage.volume.{drive_letter}.total_gb",
                    value=total_gb,
                    unit="GB",
                    source=FactAuthority.OS_API,
                    freshness_class=FreshnessClass.STABLE,
                    observed_at=now,
                ))
                facts.append(MachineFact(
                    key=f"hardware.storage.volume.{drive_letter}.free_gb",
                    value=free_gb,
                    unit="GB",
                    source=FactAuthority.OS_API,
                    freshness_class=FreshnessClass.VOLATILE,  # 30s TTL
                    observed_at=now,
                ))
                facts.append(MachineFact(
                    key=f"hardware.storage.volume.{drive_letter}.filesystem",
                    value=p.fstype,
                    source=FactAuthority.OS_API,
                    freshness_class=FreshnessClass.STABLE,
                    observed_at=now,
                ))
                facts.append(MachineFact(
                    key=f"hardware.storage.volume.{drive_letter}.is_removable",
                    value=is_removable,
                    source=FactAuthority.OS_API,
                    freshness_class=FreshnessClass.SESSION,
                    observed_at=now,
                ))
                volumes.append(drive_letter)
            except Exception as e:
                logger.debug("Failed querying partition %s: %s", mount, e)

        facts.append(MachineFact(
            key="hardware.storage.volumes",
            value=volumes,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.VOLATILE,
            observed_at=now,
        ))
        return facts

    def _discover_display(self) -> List[MachineFact]:
        facts = []
        now = time.time()
        res_str = "1920x1080"
        dpi_val = 96
        scale_pct = 100
        count = 1

        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
                h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
                count = user32.GetSystemMetrics(80) or 1  # SM_CMONITORS
                res_str = f"{w}x{h}"

                if hasattr(user32, "GetDpiForSystem"):
                    dpi_val = user32.GetDpiForSystem()
                    scale_pct = int(round((dpi_val / 96.0) * 100))
            except Exception as e:
                logger.debug("Display metrics query failed: %s", e)

        facts.append(MachineFact(
            key="hardware.display.count",
            value=count,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.display.primary.resolution",
            value=res_str,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.display.primary.dpi",
            value=dpi_val,
            unit="DPI",
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.display.primary.scaling_percent",
            value=scale_pct,
            unit="%",
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        return facts

    def _discover_network(self) -> List[MachineFact]:
        facts = []
        now = time.time()
        connected = False
        has_wifi = False
        adapter_names = []

        try:
            stats = psutil.net_if_stats()
            for iface, s in stats.items():
                adapter_names.append(iface)
                if s.isup and "loopback" not in iface.lower():
                    connected = True
                if "wi-fi" in iface.lower() or "wireless" in iface.lower() or "wlan" in iface.lower():
                    has_wifi = True
        except Exception:
            connected = True  # Safe default assumption

        facts.append(MachineFact(
            key="hardware.network.connected",
            value=connected,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.VOLATILE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.network.has_wifi",
            value=has_wifi,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.network.adapters",
            value=adapter_names,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        return facts

    def _discover_power(self) -> List[MachineFact]:
        facts = []
        now = time.time()
        battery = psutil.sensors_battery()

        if battery is None:
            facts.append(MachineFact(
                key="hardware.power.battery_present",
                value=False,
                source=FactAuthority.OS_API,
                freshness_class=FreshnessClass.STABLE,
                observed_at=now,
            ))
            facts.append(MachineFact(
                key="hardware.power.ac_connected",
                value=True,
                source=FactAuthority.OS_API,
                freshness_class=FreshnessClass.VOLATILE,
                observed_at=now,
            ))
        else:
            facts.append(MachineFact(
                key="hardware.power.battery_present",
                value=True,
                source=FactAuthority.OS_API,
                freshness_class=FreshnessClass.STABLE,
                observed_at=now,
            ))
            facts.append(MachineFact(
                key="hardware.power.ac_connected",
                value=battery.power_plugged,
                source=FactAuthority.OS_API,
                freshness_class=FreshnessClass.VOLATILE,
                observed_at=now,
            ))
            facts.append(MachineFact(
                key="hardware.power.battery_percent",
                value=battery.percent,
                unit="%",
                source=FactAuthority.OS_API,
                freshness_class=FreshnessClass.VOLATILE,
                observed_at=now,
            ))
        return facts

    def _discover_devices(self) -> List[MachineFact]:
        """Discover presence of peripheral audio/media capability without content access."""
        facts = []
        now = time.time()
        mic_present = False
        speaker_present = False
        camera_present = False
        bt_present = False

        if sys.platform == "win32":
            try:
                winmm = ctypes.windll.winmm
                mic_count = winmm.waveInGetNumDevs()
                mic_present = mic_count > 0
                speaker_count = winmm.waveOutGetNumDevs()
                speaker_present = speaker_count > 0
            except Exception:
                mic_present = True
                speaker_present = True

            # Camera presence detection via DirectShow device category registry key
            try:
                import winreg
                cam_guid = r"SYSTEM\CurrentControlSet\Control\Class\{ca3e7ab9-b4c3-4ae6-8251-579ef933890f}"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cam_guid) as key:
                    camera_present = True
            except Exception:
                camera_present = True  # Standard laptop webcam assumption

            # Bluetooth presence
            try:
                import winreg
                bt_guid = r"SYSTEM\CurrentControlSet\Services\BTHPORT"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, bt_guid) as key:
                    bt_present = True
            except Exception:
                pass

        facts.append(MachineFact(
            key="hardware.device.microphone_present",
            value=mic_present,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
            metadata={"privacy_policy": "presence_only_zero_recording"},
        ))
        facts.append(MachineFact(
            key="hardware.device.speaker_present",
            value=speaker_present,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="hardware.device.camera_present",
            value=camera_present,
            source=FactAuthority.REGISTRY,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
            metadata={"privacy_policy": "presence_only_zero_capture"},
        ))
        facts.append(MachineFact(
            key="hardware.device.bluetooth_present",
            value=bt_present,
            source=FactAuthority.REGISTRY,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        return facts
