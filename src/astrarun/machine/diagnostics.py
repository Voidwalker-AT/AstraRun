"""Machine Profile Diagnostics and Sanitized Export for AstraRun 1.0."""

from __future__ import annotations

import getpass
import os
from pathlib import Path
import time
from typing import Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.machine.capability_resolver import MachineCapabilityResolver
from astrarun.machine.fact import FactSensitivity
from astrarun.machine.model import MachineModel
from astrarun.machine.resource_snapshot import ResourceSnapshot
from astrarun.security.secret_broker import SecretBroker

logger = get_logger("astrarun.machine.diagnostics")


class MachineDiagnostics:
    """Generates structured diagnostics reports and sanitized bug-report exports."""

    def __init__(
        self,
        machine_model: Optional[MachineModel] = None,
        resolver: Optional[MachineCapabilityResolver] = None,
        secret_broker: Optional[SecretBroker] = None,
    ) -> None:
        self.model = machine_model or MachineModel.get_instance()
        self.resolver = resolver or MachineCapabilityResolver(self.model)
        self.broker = secret_broker or SecretBroker.get_instance()

    def generate_first_run_summary(self) -> str:
        """User-friendly, clean summary for first-run bootstrap and presentation."""
        cpu = self.model.get_fact("hardware.cpu.model")
        ram = self.model.get_fact("hardware.memory.total_gb")
        gpu = self.model.get_fact("hardware.gpu.model")
        vram = self.model.get_fact("hardware.gpu.vram_total_gb")
        os_ver = self.model.get_fact("os.edition") or self.model.get_fact("os.name")

        # Key detected tools
        tools_detected = []
        for t in ["git", "node", "ffmpeg"]:
            f = self.model.get_fact(f"software.tool.{t}.installed")
            if f and f.value:
                tools_detected.append(t.upper() if t == "git" else t.capitalize())

        for a in ["vivaldi", "vscode"]:
            f = self.model.get_fact(f"software.app.{a}.installed")
            if f and f.value:
                tools_detected.append("Vivaldi" if a == "vivaldi" else "VS Code")

        lines = [
            "Astra configured for this PC",
            "",
            f"• Graphics: {gpu.value if gpu else 'Integrated'} ({vram.value if vram else 0} GB VRAM)",
            f"• Memory:   {ram.value if ram else 0} GB RAM",
            f"• System:   {os_ver.value if os_ver else 'Windows'}",
            f"• Processor: {cpu.value if cpu else 'x86_64 Processor'}",
        ]
        if tools_detected:
            lines.append(f"• Detected:  {', '.join(tools_detected)}")

        return "\n".join(lines)

    def generate_diagnostics_report(self) -> str:
        """Full structured diagnostic view across all sections."""
        snap = ResourceSnapshot.capture(include_gpu=True)
        caps = self.resolver.list_capabilities()

        lines = [
            "=" * 70,
            " ASTRARUN 1.0 — WORKSTATION MACHINE PROFILE & DIAGNOSTICS",
            "=" * 70,
            "",
            "[System]",
            f"  OS Edition:        {self._val('os.edition')}",
            f"  Windows Version:   {self._val('os.version')} (Build {self._val('os.build')})",
            f"  Architecture:      {self._val('os.architecture')}",
            f"  Timezone:          {self._val('os.timezone')}",
            f"  Elevation:         Admin={self._val('os.is_admin')}, UAC={self._val('os.uac_enabled')}",
            "",
            "[Hardware & Compute]",
            f"  CPU Model:         {self._val('hardware.cpu.model')}",
            f"  Cores / Topology:  {self._val('hardware.cpu.physical_cores')} physical, {self._val('hardware.cpu.logical_cores')} logical",
            f"  Installed RAM:     {self._val('hardware.memory.total_gb')} GB (Available: {snap.available_ram_gb} GB)",
            f"  GPU Adapter:       {self._val('hardware.gpu.model')}",
            f"  VRAM (Dedicated):  {self._val('hardware.gpu.vram_total_gb')} GB (Free: {snap.free_vram_gb} GB)",
            f"  CUDA Runtime:      Available={self._val('hardware.gpu.cuda_available')}",
            "",
            "[Storage & Volumes]",
        ]

        vols = self.model.get_fact("hardware.storage.volumes")
        if vols and vols.value:
            for v in vols.value:
                tot = self._val(f"hardware.storage.volume.{v}.total_gb")
                fre = self._val(f"hardware.storage.volume.{v}.free_gb")
                fs = self._val(f"hardware.storage.volume.{v}.filesystem")
                lines.append(f"  Drive {v}:\\          {fre} GB free of {tot} GB ({fs})")

        lines.extend([
            "",
            "[Display & Media]",
            f"  Monitors:          {self._val('hardware.display.count')} (Primary: {self._val('hardware.display.primary.resolution')}, {self._val('hardware.display.primary.scaling_percent')}%)",
            f"  Audio Output:      {self._val('hardware.device.speaker_present')}",
            f"  Microphone:        {self._val('hardware.device.microphone_present')}",
            f"  Camera:            {self._val('hardware.device.camera_present')}",
            "",
            "[Developer Tools & Runtimes]",
            f"  Git:               {self._val('software.tool.git.installed')} ({self._val('software.tool.git.version')})",
            f"  Python (Active):   {self._val('software.python.active.version')} ({self._val('software.python.active.executable')})",
            f"  Node.js:           {self._val('software.tool.node.installed')} ({self._val('software.tool.node.version')})",
            f"  C/C++ Compilers:   MSVC={self._val('software.tool.cl.installed')}, GCC={self._val('software.tool.gcc.installed')}",
            f"  ffmpeg:            {self._val('software.tool.ffmpeg.installed')}",
            f"  7-Zip:             {self._val('software.tool.7zip.installed')}",
            f"  VS Code:           {self._val('software.app.vscode.installed')}",
            f"  Vivaldi:           {self._val('software.app.vivaldi.installed')}",
            "",
            "[Derived Operational Capabilities]",
        ])

        for cname, pred in caps.items():
            lines.append(f"  • {cname:<30} {pred.status.value:<16} ({pred.reason})")

        lines.append("=" * 70)
        return "\n".join(lines)

    def export_sanitized_diagnostics(self) -> str:
        """Export sanitized diagnostic report scrubbed of usernames, personal paths, and secrets."""
        raw = self.generate_diagnostics_report()

        # Redact username
        username = getpass.getuser()
        clean = raw.replace(username, "<USER>")

        # Redact user profile home folder
        user_home = str(Path.home())
        clean = clean.replace(user_home, "<USER_HOME>")

        # Scrub secrets
        scrubbed, _ = self.broker.scrub_text(clean)
        return scrubbed

    def _val(self, key: str) -> str:
        fact = self.model.get_fact(key)
        return str(fact.value) if fact is not None else "Unknown"
