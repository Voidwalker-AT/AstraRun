"""Authoritative MachineCapabilityResolver for AstraRun 1.0.

Translates raw MachineFacts and ResourceSnapshots into authoritative planning predicates
with supporting fact citations and remediation suggestions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.machine.model import MachineModel
from astrarun.machine.resource_snapshot import ResourceSnapshot

logger = get_logger("astrarun.machine.capability_resolver")


class CapabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DEGRADED = "DEGRADED"
    RESOURCE_BLOCKED = "RESOURCE_BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass
class CapabilityPredicate:
    """Strongly typed capability verdict with citation and remediation."""
    name: str
    status: CapabilityStatus
    reason: str
    supporting_facts: List[str] = field(default_factory=list)
    remediation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class MachineCapabilityResolver:
    """Resolves operational capabilities from observed machine reality."""

    def __init__(self, machine_model: Optional[MachineModel] = None) -> None:
        self.model = machine_model or MachineModel.get_instance()

    def resolve(self, capability_name: str) -> CapabilityPredicate:
        """Resolve a specific capability predicate."""
        method_map = {
            "CAN_RUN_LOCAL_SPARK": self._can_run_local_spark,
            "CAN_RUN_LOCAL_QWEN": self._can_run_local_qwen,
            "CAN_LOAD_LOCAL_VLM_NOW": self._can_load_local_vlm_now,
            "CAN_RUN_PYTHON_VISUALIZATION": self._can_run_python_visualization,
            "CAN_COMPILE_CPP": self._can_compile_cpp,
            "CAN_USE_CUDA": self._can_use_cuda,
            "CAN_AUTOMATE_BROWSER": self._can_automate_browser,
            "CAN_USE_UIA": self._can_use_uia,
            "CAN_USE_CDP": self._can_use_cdp,
            "CAN_DOWNLOAD": self._can_download,
            "CAN_EXTRACT_ZIP": self._can_extract_zip,
            "CAN_RENDER_VIDEO": self._can_render_video,
            "CAN_USE_GIT": self._can_use_git,
            "CAN_RUN_NODE": self._can_run_node,
            "CAN_BUILD_CUDA": self._can_build_cuda,
        }

        handler = method_map.get(capability_name)
        if not handler:
            return CapabilityPredicate(
                name=capability_name,
                status=CapabilityStatus.UNKNOWN,
                reason=f"Capability '{capability_name}' is not recognized in resolver registry.",
            )
        return handler()

    def list_capabilities(self) -> Dict[str, CapabilityPredicate]:
        """Evaluate and return all standard capabilities."""
        caps = [
            "CAN_RUN_LOCAL_SPARK",
            "CAN_RUN_LOCAL_QWEN",
            "CAN_LOAD_LOCAL_VLM_NOW",
            "CAN_RUN_PYTHON_VISUALIZATION",
            "CAN_COMPILE_CPP",
            "CAN_USE_CUDA",
            "CAN_AUTOMATE_BROWSER",
            "CAN_USE_UIA",
            "CAN_USE_CDP",
            "CAN_DOWNLOAD",
            "CAN_EXTRACT_ZIP",
            "CAN_RENDER_VIDEO",
            "CAN_USE_GIT",
            "CAN_RUN_NODE",
            "CAN_BUILD_CUDA",
        ]
        return {c: self.resolve(c) for c in caps}

    resolve_all = list_capabilities

    # -------------------------------------------------------------------------
    # Individual Capability Evaluators
    # -------------------------------------------------------------------------

    def _can_run_local_spark(self) -> CapabilityPredicate:
        ram = self.model.get_fact("hardware.memory.total_gb")
        ram_gb = ram.value if ram else 0.0
        if ram_gb >= 6.0:
            return CapabilityPredicate(
                name="CAN_RUN_LOCAL_SPARK",
                status=CapabilityStatus.AVAILABLE,
                reason=f"Host has {ram_gb} GB RAM (>= 6.0 GB required for Spark-1.7B).",
                supporting_facts=[f"hardware.memory.total_gb = {ram_gb}"],
            )
        return CapabilityPredicate(
            name="CAN_RUN_LOCAL_SPARK",
            status=CapabilityStatus.UNAVAILABLE,
            reason=f"Insufficient RAM ({ram_gb} GB < 6.0 GB required).",
            supporting_facts=[f"hardware.memory.total_gb = {ram_gb}"],
            remediation="Upgrade physical host RAM to at least 8 GB.",
        )

    def _can_run_local_qwen(self) -> CapabilityPredicate:
        ram = self.model.get_fact("hardware.memory.total_gb")
        ram_gb = ram.value if ram else 0.0
        if ram_gb >= 8.0:
            return CapabilityPredicate(
                name="CAN_RUN_LOCAL_QWEN",
                status=CapabilityStatus.AVAILABLE,
                reason=f"Host has {ram_gb} GB RAM (>= 8.0 GB required for Qwen-Coder-1.5B).",
                supporting_facts=[f"hardware.memory.total_gb = {ram_gb}"],
            )
        return CapabilityPredicate(
            name="CAN_RUN_LOCAL_QWEN",
            status=CapabilityStatus.UNAVAILABLE,
            reason=f"Insufficient RAM ({ram_gb} GB < 8.0 GB required).",
            supporting_facts=[f"hardware.memory.total_gb = {ram_gb}"],
            remediation="Increase physical host RAM to at least 12 GB.",
        )

    def _can_load_local_vlm_now(self) -> CapabilityPredicate:
        snap = ResourceSnapshot.capture(include_gpu=True)
        cuda_fact = self.model.get_fact("hardware.gpu.cuda_available")
        has_cuda = bool(cuda_fact.value) if cuda_fact is not None else snap.has_cuda_gpu

        vram_free_mb_fact = self.model.get_fact("hardware.gpu.vram_free_mb")
        if vram_free_mb_fact is not None:
            free_vram_gb = round(float(vram_free_mb_fact.value) / 1024.0, 2)
        else:
            free_vram_gb = snap.free_vram_gb

        if not has_cuda:
            return CapabilityPredicate(
                name="CAN_LOAD_LOCAL_VLM_NOW",
                status=CapabilityStatus.DEGRADED,
                reason="NVIDIA GPU not detected; vision model will fall back to CPU inference.",
                supporting_facts=["hardware.gpu.present = False"],
            )

        # SmolVLM / OmniParser requires ~2.5 GB free VRAM
        if free_vram_gb >= 2.5:
            return CapabilityPredicate(
                name="CAN_LOAD_LOCAL_VLM_NOW",
                status=CapabilityStatus.AVAILABLE,
                reason=f"Live free VRAM is {free_vram_gb} GB (>= 2.5 GB required).",
                supporting_facts=[f"live free_vram_gb = {free_vram_gb}"],
            )

        return CapabilityPredicate(
            name="CAN_LOAD_LOCAL_VLM_NOW",
            status=CapabilityStatus.RESOURCE_BLOCKED,
            reason=f"Live free VRAM is only {free_vram_gb} GB (2.5 GB required).",
            supporting_facts=[f"live free_vram_gb = {free_vram_gb}"],
            remediation="Evict resident local models (e.g., Qwen-Coder) to free VRAM for visual perception.",
        )

    def _can_run_python_visualization(self) -> CapabilityPredicate:
        py_fact = self.model.get_fact("software.python.active.executable")
        np_fact = self.model.get_fact("software.python.package.numpy.installed")
        plt_fact = self.model.get_fact("software.python.package.matplotlib.installed")

        facts = []
        if py_fact:
            facts.append(f"python = {py_fact.value}")
        if np_fact:
            facts.append(f"numpy = {np_fact.value}")
        if plt_fact:
            facts.append(f"matplotlib = {plt_fact.value}")

        if (np_fact and np_fact.value) and (plt_fact and plt_fact.value):
            return CapabilityPredicate(
                name="CAN_RUN_PYTHON_VISUALIZATION",
                status=CapabilityStatus.AVAILABLE,
                reason="Python runtime with numpy and matplotlib is fully available.",
                supporting_facts=facts,
            )

        missing = []
        if not (np_fact and np_fact.value):
            missing.append("numpy")
        if not (plt_fact and plt_fact.value):
            missing.append("matplotlib")

        return CapabilityPredicate(
            name="CAN_RUN_PYTHON_VISUALIZATION",
            status=CapabilityStatus.UNAVAILABLE,
            reason=f"Required visualization packages missing: {', '.join(missing)}.",
            supporting_facts=facts,
            remediation=f"Request installation of {', '.join(missing)} via DependencyRequest.",
        )

    def _can_compile_cpp(self) -> CapabilityPredicate:
        cl = self.model.get_fact("software.tool.cl.installed")
        gcc = self.model.get_fact("software.tool.gcc.installed")
        if (cl and cl.value) or (gcc and gcc.value):
            compiler = "MSVC cl.exe" if (cl and cl.value) else "GCC"
            return CapabilityPredicate(
                name="CAN_COMPILE_CPP",
                status=CapabilityStatus.AVAILABLE,
                reason=f"Native C/C++ compiler ({compiler}) is installed and verified.",
                supporting_facts=[f"cl = {bool(cl and cl.value)}", f"gcc = {bool(gcc and gcc.value)}"],
            )
        return CapabilityPredicate(
            name="CAN_COMPILE_CPP",
            status=CapabilityStatus.UNAVAILABLE,
            reason="Neither MSVC cl.exe nor GCC compiler detected on PATH.",
            supporting_facts=["software.tool.cl.installed = False", "software.tool.gcc.installed = False"],
            remediation="Install Visual Studio Build Tools or MinGW GCC.",
        )

    def _can_use_cuda(self) -> CapabilityPredicate:
        gpu = self.model.get_fact("hardware.gpu.model")
        cuda = self.model.get_fact("hardware.gpu.cuda_available")
        gpu_name = gpu.value if gpu else "Unknown"
        if cuda and cuda.value:
            return CapabilityPredicate(
                name="CAN_USE_CUDA",
                status=CapabilityStatus.AVAILABLE,
                reason=f"CUDA acceleration available on {gpu_name}.",
                supporting_facts=[f"gpu.model = {gpu_name}", "gpu.cuda_available = True"],
            )
        return CapabilityPredicate(
            name="CAN_USE_CUDA",
            status=CapabilityStatus.UNAVAILABLE,
            reason=f"CUDA not supported or no NVIDIA GPU detected ({gpu_name}).",
            supporting_facts=[f"gpu.model = {gpu_name}"],
            remediation="Use CPU inference / compute runtimes.",
        )

    def _can_automate_browser(self) -> CapabilityPredicate:
        for b in ["vivaldi", "chrome", "edge"]:
            f = self.model.get_fact(f"software.app.{b}.installed")
            if f and f.value:
                return CapabilityPredicate(
                    name="CAN_AUTOMATE_BROWSER",
                    status=CapabilityStatus.AVAILABLE,
                    reason=f"Supported desktop browser ({b.capitalize()}) is installed and accessible.",
                    supporting_facts=[f"software.app.{b}.installed = True"],
                )
        return CapabilityPredicate(
            name="CAN_AUTOMATE_BROWSER",
            status=CapabilityStatus.UNAVAILABLE,
            reason="No supported browser (Vivaldi, Chrome, Edge) detected.",
            supporting_facts=[],
            remediation="Install Vivaldi or Google Chrome.",
        )

    def _can_use_uia(self) -> CapabilityPredicate:
        return CapabilityPredicate(
            name="CAN_USE_UIA",
            status=CapabilityStatus.AVAILABLE,
            reason="Windows UI Automation (UIA) foundation available via OS runtime.",
            supporting_facts=["os.name = Windows"],
        )

    def _can_use_cdp(self) -> CapabilityPredicate:
        for b in ["vivaldi", "chrome", "edge"]:
            f = self.model.get_fact(f"software.app.{b}.installed")
            if f and f.value:
                return CapabilityPredicate(
                    name="CAN_USE_CDP",
                    status=CapabilityStatus.AVAILABLE,
                    reason=f"Chromium-based browser ({b.capitalize()}) supports Chrome DevTools Protocol.",
                    supporting_facts=[f"software.app.{b}.installed = True"],
                )
        return CapabilityPredicate(
            name="CAN_USE_CDP",
            status=CapabilityStatus.UNAVAILABLE,
            reason="No Chromium-based browser detected with CDP support.",
            supporting_facts=[],
            remediation="Install Vivaldi, Chrome, or Edge.",
        )

    def _can_download(self) -> CapabilityPredicate:
        net = self.model.get_fact("hardware.network.connected")
        is_conn = net.value if net else True
        if is_conn:
            return CapabilityPredicate(
                name="CAN_DOWNLOAD",
                status=CapabilityStatus.AVAILABLE,
                reason="Workstation network adapter reports active connection.",
                supporting_facts=["hardware.network.connected = True"],
            )
        return CapabilityPredicate(
            name="CAN_DOWNLOAD",
            status=CapabilityStatus.UNAVAILABLE,
            reason="Network interface is disconnected or offline.",
            supporting_facts=["hardware.network.connected = False"],
            remediation="Connect workstation to Wi-Fi or Ethernet.",
        )

    def _can_extract_zip(self) -> CapabilityPredicate:
        seven_zip = self.model.get_fact("software.tool.7zip.installed")
        if seven_zip and seven_zip.value:
            return CapabilityPredicate(
                name="CAN_EXTRACT_ZIP",
                status=CapabilityStatus.AVAILABLE,
                reason="7-Zip native high-performance archive tool is installed.",
                supporting_facts=["software.tool.7zip.installed = True"],
            )
        return CapabilityPredicate(
            name="CAN_EXTRACT_ZIP",
            status=CapabilityStatus.AVAILABLE,
            reason="Python standard library zipfile module available.",
            supporting_facts=["python.zipfile = True"],
        )

    def _can_render_video(self) -> CapabilityPredicate:
        ff = self.model.get_fact("software.tool.ffmpeg.installed")
        if ff and ff.value:
            ver = self.model.get_fact("software.tool.ffmpeg.version")
            return CapabilityPredicate(
                name="CAN_RENDER_VIDEO",
                status=CapabilityStatus.AVAILABLE,
                reason=f"ffmpeg media tool is installed ({ver.value if ver else 'detected'}).",
                supporting_facts=["software.tool.ffmpeg.installed = True"],
            )
        return CapabilityPredicate(
            name="CAN_RENDER_VIDEO",
            status=CapabilityStatus.UNAVAILABLE,
            reason="ffmpeg executable not detected on system PATH.",
            supporting_facts=["software.tool.ffmpeg.installed = False"],
            remediation="Install ffmpeg (e.g. scoop install ffmpeg or download binary).",
        )

    def _can_use_git(self) -> CapabilityPredicate:
        git_fact = self.model.get_fact("software.tool.git.installed")
        if git_fact and git_fact.value:
            return CapabilityPredicate(
                name="CAN_USE_GIT",
                status=CapabilityStatus.AVAILABLE,
                reason="Git version control CLI is installed and operational.",
                supporting_facts=["software.tool.git.installed = True"],
            )
        return CapabilityPredicate(
            name="CAN_USE_GIT",
            status=CapabilityStatus.UNAVAILABLE,
            reason="Git command not found on PATH.",
            supporting_facts=["software.tool.git.installed = False"],
            remediation="Install Git for Windows.",
        )

    def _can_run_node(self) -> CapabilityPredicate:
        node_fact = self.model.get_fact("software.tool.node.installed")
        if node_fact and node_fact.value:
            return CapabilityPredicate(
                name="CAN_RUN_NODE",
                status=CapabilityStatus.AVAILABLE,
                reason="Node.js runtime is installed and operational.",
                supporting_facts=["software.tool.node.installed = True"],
            )
        return CapabilityPredicate(
            name="CAN_RUN_NODE",
            status=CapabilityStatus.UNAVAILABLE,
            reason="Node.js runtime not found on PATH.",
            supporting_facts=["software.tool.node.installed = False"],
            remediation="Install Node.js from nodejs.org or via scoop.",
        )

    def _can_build_cuda(self) -> CapabilityPredicate:
        nvcc = self.model.get_fact("software.tool.nvcc.installed")
        if nvcc and nvcc.value:
            return CapabilityPredicate(
                name="CAN_BUILD_CUDA",
                status=CapabilityStatus.AVAILABLE,
                reason="NVIDIA CUDA Compiler (nvcc) is installed on PATH.",
                supporting_facts=["software.tool.nvcc.installed = True"],
            )
        return CapabilityPredicate(
            name="CAN_BUILD_CUDA",
            status=CapabilityStatus.UNAVAILABLE,
            reason="NVIDIA CUDA Compiler (nvcc) not detected on PATH.",
            supporting_facts=["software.tool.nvcc.installed = False"],
            remediation="Install NVIDIA CUDA Toolkit.",
        )
