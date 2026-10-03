"""Natural Language Machine Query Engine for AstraRun 1.0.

Answers user queries regarding workstation hardware, resources, installed tools,
and capabilities directly from the MachineModel and live ResourceSnapshots.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import psutil

from astrarun.core.logging import get_logger
from astrarun.machine.capability_resolver import CapabilityStatus, MachineCapabilityResolver
from astrarun.machine.model import MachineModel
from astrarun.machine.resource_snapshot import ResourceSnapshot

logger = get_logger("astrarun.machine.query_engine")


class MachineQueryEngine:
    """Answers machine-related questions from authoritative observed facts."""

    def __init__(
        self,
        machine_model: Optional[MachineModel] = None,
        resolver: Optional[MachineCapabilityResolver] = None,
    ) -> None:
        self.model = machine_model or MachineModel.get_instance()
        self.resolver = resolver or MachineCapabilityResolver(self.model)

    def answer(self, query: str) -> str:
        """Helper to get string answer directly from natural language query."""
        res = self.answer_query(query)
        return str(res.get("answer", ""))

    def answer_query(self, query: str) -> Dict[str, Any]:
        """Parse natural language machine question and produce authoritative answer."""
        q = query.lower().strip()

        # 1. CPU Query
        if "cpu" in q or "processor" in q:
            model = self.model.get_fact("hardware.cpu.model")
            p_cores = self.model.get_fact("hardware.cpu.physical_cores")
            l_cores = self.model.get_fact("hardware.cpu.logical_cores")
            ans = f"You have an {model.value if model else 'x86_64'} with {p_cores.value if p_cores else 4} physical cores and {l_cores.value if l_cores else 8} logical threads."
            return {
                "query": query,
                "matched_topic": "CPU",
                "answer": ans,
                "facts_used": ["hardware.cpu.model", "hardware.cpu.physical_cores", "hardware.cpu.logical_cores"],
            }

        # 2. VRAM Free
        if "vram" in q and ("free" in q or "available" in q or "much" in q):
            snap = ResourceSnapshot.capture(include_gpu=True)
            ans = f"You currently have {snap.free_vram_gb} GB of free dedicated VRAM available on your GPU (out of {snap.total_vram_gb} GB total)."
            return {
                "query": query,
                "matched_topic": "VRAM_FREE",
                "answer": ans,
                "facts_used": [f"live free_vram_gb={snap.free_vram_gb}"],
            }

        # 3. GPU Query
        if "gpu" in q or "graphics" in q or "video card" in q:
            gpu = self.model.get_fact("hardware.gpu.model")
            vram = self.model.get_fact("hardware.gpu.vram_total_gb")
            cuda = self.model.get_fact("hardware.gpu.cuda_available")
            ans = f"Your graphics adapter is {gpu.value if gpu else 'Integrated'} with {vram.value if vram else 0} GB dedicated VRAM (CUDA Available: {bool(cuda and cuda.value)})."
            return {
                "query": query,
                "matched_topic": "GPU",
                "answer": ans,
                "facts_used": ["hardware.gpu.model", "hardware.gpu.vram_total_gb", "hardware.gpu.cuda_available"],
            }

        # 4. RAM Free / Available
        if "ram" in q and ("free" in q or "available" in q):
            snap = ResourceSnapshot.capture(include_gpu=False)
            ans = f"You have {snap.available_ram_gb} GB of physical RAM free right now (out of {snap.total_ram_gb} GB total)."
            return {
                "query": query,
                "matched_topic": "RAM_FREE",
                "answer": ans,
                "facts_used": [f"live available_ram_gb={snap.available_ram_gb}"],
            }

        # 5. Total RAM
        if "ram" in q or "memory" in q:
            ram = self.model.get_fact("hardware.memory.total_gb")
            snap = ResourceSnapshot.capture(include_gpu=False)
            ans = f"Your PC has {ram.value if ram else 0} GB of physical RAM installed ({snap.available_ram_gb} GB currently available)."
            return {
                "query": query,
                "matched_topic": "RAM_TOTAL",
                "answer": ans,
                "facts_used": ["hardware.memory.total_gb", f"live available_ram_gb={snap.available_ram_gb}"],
            }

        # 6. Monitors / Display
        if "monitor" in q or "screen" in q or "display" in q:
            count = self.model.get_fact("hardware.display.count")
            res = self.model.get_fact("hardware.display.primary.resolution")
            scale = self.model.get_fact("hardware.display.primary.scaling_percent")
            ans = f"You have {count.value if count else 1} monitor(s) connected. Primary display resolution is {res.value if res else '1920x1080'} at {scale.value if scale else 100}% scaling."
            return {
                "query": query,
                "matched_topic": "DISPLAY",
                "answer": ans,
                "facts_used": ["hardware.display.count", "hardware.display.primary.resolution"],
            }

        # 7. Vivaldi installed
        if "vivaldi" in q:
            f = self.model.get_fact("software.app.vivaldi.installed")
            p = self.model.get_fact("software.app.vivaldi.path")
            if f and f.value:
                ans = f"Yes, Vivaldi is installed at: {p.value if p else 'Default Location'}."
            else:
                ans = "No, Vivaldi was not detected on this PC."
            return {
                "query": query,
                "matched_topic": "VIVALDI",
                "answer": ans,
                "facts_used": ["software.app.vivaldi.installed"],
            }

        # 8. VS Code installed
        if "vs code" in q or "vscode" in q or "code" in q:
            f = self.model.get_fact("software.app.vscode.installed")
            p = self.model.get_fact("software.app.vscode.path")
            if f and f.value:
                ans = f"Yes, Visual Studio Code is installed at: {p.value if p else 'Standard Path'}."
            else:
                ans = "No, VS Code was not detected on this PC."
            return {
                "query": query,
                "matched_topic": "VSCODE",
                "answer": ans,
                "facts_used": ["software.app.vscode.installed"],
            }

        # 9. Git installed / location
        if "git" in q:
            f = self.model.get_fact("software.tool.git.installed")
            p = self.model.get_fact("software.tool.git.path")
            v = self.model.get_fact("software.tool.git.version")
            if f and f.value:
                ans = f"Git is installed at {p.value if p else 'PATH'} ({v.value if v else 'Version Detected'})."
            else:
                ans = "Git is not installed on this system."
            return {
                "query": query,
                "matched_topic": "GIT",
                "answer": ans,
                "facts_used": ["software.tool.git.installed", "software.tool.git.path"],
            }

        # 10. Can I run CUDA?
        if "cuda" in q:
            pred = self.resolver.resolve("CAN_USE_CUDA")
            ans = f"CUDA Capability: {pred.status.value}. {pred.reason}"
            return {
                "query": query,
                "matched_topic": "CAN_USE_CUDA",
                "answer": ans,
                "facts_used": pred.supporting_facts,
            }

        # 11. Can I load the visual model now?
        if "visual" in q or "vlm" in q or "vision" in q:
            pred = self.resolver.resolve("CAN_LOAD_LOCAL_VLM_NOW")
            ans = f"Visual Model Status: {pred.status.value}. {pred.reason}"
            if pred.remediation:
                ans += f" Recommended action: {pred.remediation}"
            return {
                "query": query,
                "matched_topic": "LOAD_VLM_NOW",
                "answer": ans,
                "facts_used": pred.supporting_facts,
            }

        # 12. Storage space for 5 GB file
        if "drive" in q or "space" in q or "5 gb" in q or "5gb" in q:
            vols = self.model.get_fact("hardware.storage.volumes")
            eligible = []
            if vols and vols.value:
                for v in vols.value:
                    free_fact = self.model.get_fact(f"hardware.storage.volume.{v}.free_gb")
                    if free_fact and free_fact.value >= 5.0:
                        eligible.append(f"Drive {v}: ({free_fact.value} GB free)")
            if eligible:
                ans = f"The following drives have at least 5 GB of free space: {', '.join(eligible)}."
            else:
                ans = "None of the mounted drives have 5 GB of free space."
            return {
                "query": query,
                "matched_topic": "STORAGE_CHECK",
                "answer": ans,
                "facts_used": ["hardware.storage.volumes"],
            }

        # 13. Port query
        port_match = re.search(r"port\s+(\d+)", q)
        if port_match:
            port = int(port_match.group(1))
            proc_info = "No active process"
            try:
                for conn in psutil.net_connections(kind="inet"):
                    if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
                        if conn.pid:
                            p = psutil.Process(conn.pid)
                            proc_info = f"Process '{p.name()}' (PID {conn.pid})"
                            break
            except Exception:
                pass
            ans = f"Port {port} status: {proc_info}."
            return {
                "query": query,
                "matched_topic": "PORT_QUERY",
                "answer": ans,
                "facts_used": [f"port={port}"],
            }

        # Fallback
        return {
            "query": query,
            "matched_topic": "UNKNOWN",
            "answer": "I don't have a direct machine probe for that specific hardware query.",
            "facts_used": [],
        }
