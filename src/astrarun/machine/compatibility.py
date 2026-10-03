"""Compatibility Assessment Engine for AstraRun 1.0.

Evaluates proposed workloads (CUDA, vision models, visualization, native builds)
against hardware, drivers, toolchains, and live resources BEFORE execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.machine.capability_resolver import CapabilityPredicate, CapabilityStatus, MachineCapabilityResolver
from astrarun.machine.model import MachineModel
from astrarun.machine.resource_snapshot import ResourceSnapshot

logger = get_logger("astrarun.machine.compatibility")


@dataclass
class CompatibilityReport:
    """Pre-flight compatibility verdict for a proposed workload."""
    target_workload: str
    status: CapabilityStatus
    hardware_compatible: bool
    driver_compatible: bool
    toolkit_compatible: bool
    resource_sufficient: bool
    reason: str
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class CompatibilityEngine:
    """Evaluates workstation compatibility before initiating complex plans."""

    def __init__(
        self,
        machine_model: Optional[MachineModel] = None,
        resolver: Optional[MachineCapabilityResolver] = None,
    ) -> None:
        self.model = machine_model or MachineModel.get_instance()
        self.resolver = resolver or MachineCapabilityResolver(self.model)

    def assess_workload(
        self,
        workload_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> CompatibilityReport:
        """Assess compatibility for a proposed workload."""
        params = parameters or {}
        w = workload_type.lower()

        if "cuda" in w or "gpu" in w:
            return self._assess_cuda(params)
        elif "vlm" in w or "vision" in w:
            return self._assess_vlm(params)
        elif "graph" in w or "plot" in w or "visualization" in w:
            return self._assess_visualization(params)
        elif "compile" in w or "c++" in w or "cpp" in w:
            return self._assess_cpp(params)
        elif "download" in w:
            return self._assess_download(params)
        elif "video" in w or "ffmpeg" in w:
            return self._assess_video(params)

        # Default fallback assessment
        return CompatibilityReport(
            target_workload=workload_type,
            status=CapabilityStatus.AVAILABLE,
            hardware_compatible=True,
            driver_compatible=True,
            toolkit_compatible=True,
            resource_sufficient=True,
            reason=f"Workload '{workload_type}' has no specialized hardware constraints.",
        )

    def _assess_cuda(self, params: Dict[str, Any]) -> CompatibilityReport:
        snap = ResourceSnapshot.capture(include_gpu=True)
        cuda_fact = self.model.get_fact("hardware.gpu.cuda_available")
        has_cuda = cuda_fact.value if cuda_fact is not None else snap.has_cuda_gpu
        has_gpu = snap.has_cuda_gpu or bool(has_cuda) or bool(self.model.get_fact("hardware.gpu.model"))
        vram_req = params.get("vram_required_gb", 2.0)

        if not has_gpu:
            return CompatibilityReport(
                target_workload="cuda_workload",
                status=CapabilityStatus.UNAVAILABLE,
                hardware_compatible=False,
                driver_compatible=False,
                toolkit_compatible=False,
                resource_sufficient=False,
                reason="No NVIDIA CUDA GPU detected on host.",
                recommendations=["Run on CPU alternative or cloud compute."],
            )

        if not has_cuda:
            return CompatibilityReport(
                target_workload="cuda_workload",
                status=CapabilityStatus.DEGRADED,
                hardware_compatible=True,
                driver_compatible=False,
                toolkit_compatible=False,
                resource_sufficient=True,
                reason="NVIDIA GPU detected but CUDA driver runtime is uninitialized or incompatible.",
                recommendations=["Verify NVIDIA Game Ready or Studio display driver installation."],
            )

        vram_free = snap.free_vram_gb
        vram_fact = self.model.get_fact("hardware.gpu.vram_free_mb")
        if vram_fact and vram_fact.value:
            vram_free = round(float(vram_fact.value) / 1024.0, 2)
        elif vram_free == 0.0 and has_cuda:
            vram_free = 4.0

        if vram_free < vram_req:
            return CompatibilityReport(
                target_workload="cuda_workload",
                status=CapabilityStatus.RESOURCE_BLOCKED,
                hardware_compatible=True,
                driver_compatible=True,
                toolkit_compatible=True,
                resource_sufficient=False,
                reason=f"Free VRAM ({vram_free} GB) is less than required ({vram_req} GB).",
                recommendations=["Evict resident models to free VRAM before launch."],
            )

        return CompatibilityReport(
            target_workload="cuda_workload",
            status=CapabilityStatus.AVAILABLE,
            hardware_compatible=True,
            driver_compatible=True,
            toolkit_compatible=True,
            resource_sufficient=True,
            reason=f"CUDA workload compatible: {vram_free} GB free VRAM available.",
        )

    def _assess_vlm(self, params: Dict[str, Any]) -> CompatibilityReport:
        pred = self.resolver.resolve("CAN_LOAD_LOCAL_VLM_NOW")
        snap = ResourceSnapshot.capture(include_gpu=True)
        return CompatibilityReport(
            target_workload="local_vlm",
            status=pred.status,
            hardware_compatible=snap.has_cuda_gpu or snap.total_ram_gb >= 12.0,
            driver_compatible=True,
            toolkit_compatible=True,
            resource_sufficient=pred.status == CapabilityStatus.AVAILABLE,
            reason=pred.reason,
            recommendations=[pred.remediation] if pred.remediation else [],
        )

    def _assess_visualization(self, params: Dict[str, Any]) -> CompatibilityReport:
        pred = self.resolver.resolve("CAN_RUN_PYTHON_VISUALIZATION")
        return CompatibilityReport(
            target_workload="python_visualization",
            status=pred.status,
            hardware_compatible=True,
            driver_compatible=True,
            toolkit_compatible=pred.status == CapabilityStatus.AVAILABLE,
            resource_sufficient=True,
            reason=pred.reason,
            recommendations=[pred.remediation] if pred.remediation else [],
        )

    def _assess_cpp(self, params: Dict[str, Any]) -> CompatibilityReport:
        pred = self.resolver.resolve("CAN_COMPILE_CPP")
        return CompatibilityReport(
            target_workload="cpp_compilation",
            status=pred.status,
            hardware_compatible=True,
            driver_compatible=True,
            toolkit_compatible=pred.status == CapabilityStatus.AVAILABLE,
            resource_sufficient=True,
            reason=pred.reason,
            recommendations=[pred.remediation] if pred.remediation else [],
        )

    def _assess_download(self, params: Dict[str, Any]) -> CompatibilityReport:
        pred = self.resolver.resolve("CAN_DOWNLOAD")
        return CompatibilityReport(
            target_workload="network_download",
            status=pred.status,
            hardware_compatible=True,
            driver_compatible=True,
            toolkit_compatible=True,
            resource_sufficient=pred.status == CapabilityStatus.AVAILABLE,
            reason=pred.reason,
            recommendations=[pred.remediation] if pred.remediation else [],
        )

    def _assess_video(self, params: Dict[str, Any]) -> CompatibilityReport:
        pred = self.resolver.resolve("CAN_RENDER_VIDEO")
        return CompatibilityReport(
            target_workload="video_rendering",
            status=pred.status,
            hardware_compatible=True,
            driver_compatible=True,
            toolkit_compatible=pred.status == CapabilityStatus.AVAILABLE,
            resource_sufficient=True,
            reason=pred.reason,
            recommendations=[pred.remediation] if pred.remediation else [],
        )
