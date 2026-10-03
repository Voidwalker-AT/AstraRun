"""Versioned Model and Runtime Manifest for AstraRun 1.0.

Specifies:
- Standard Model Packs (Thin core installer + Managed first-run download)
- Roles: FAST_COGNITION, DEEP_COGNITION, EMBEDDING, VISUAL_GROUNDER, VISUAL_REASONER
- Strong integrity hashing (SHA-256)
- Explicit licensing, size constraints, and hardware requirements
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ModelRole(str, Enum):
    """Functional role of an AI model in AstraRun architecture."""
    FAST_COGNITION = "FAST_COGNITION"
    DEEP_COGNITION = "DEEP_COGNITION"
    EMBEDDING = "EMBEDDING"
    VISUAL_GROUNDER = "VISUAL_GROUNDER"
    VISUAL_REASONER = "VISUAL_REASONER"
    RUNTIME_SERVER = "RUNTIME_SERVER"


@dataclass
class ModelArtifact:
    """Individual downloadable model or runtime binary artifact."""
    id: str
    name: str
    role: ModelRole
    version: str
    source_url: str
    license: str
    size_bytes: int
    sha256: str
    runtime: str
    required: bool
    relative_path: str
    min_ram_gb: float = 8.0
    min_vram_gb: float = 0.0

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024.0 * 1024.0)

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024.0 * 1024.0 * 1024.0)


@dataclass
class ManagedModelPack:
    """Group of complementary model artifacts forming a coherent execution profile."""
    id: str
    name: str
    description: str
    min_ram_gb: float
    min_vram_gb: float
    artifacts: List[ModelArtifact] = field(default_factory=list)

    @property
    def total_download_bytes(self) -> int:
        return sum(a.size_bytes for a in self.artifacts)

    @property
    def total_download_mb(self) -> float:
        return self.total_download_bytes / (1024.0 * 1024.0)

    @property
    def total_download_gb(self) -> float:
        return self.total_download_bytes / (1024.0 * 1024.0 * 1024.0)


def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-256 hash of a file streaming in chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest().lower()


def verify_artifact_hash(file_path: Path, expected_sha256: str) -> bool:
    """Verify that a local file exactly matches the expected SHA-256 hash."""
    if not file_path.exists():
        return False
    actual_hash = compute_sha256(file_path)
    return actual_hash == expected_sha256.lower().strip()


# =============================================================================
# CANONICAL MODEL PACKS SPECIFICATION FOR ASTRARUN 1.0
# =============================================================================

ARTIFACT_BGE_EMBEDDING = ModelArtifact(
    id="bge-small-en-v1.5",
    name="BAAI BGE-small-en-v1.5 ONNX Embedding Model",
    role=ModelRole.EMBEDDING,
    version="1.5",
    source_url="https://huggingface.co/BAAI/bge-small-en-v1.5/resolve/main/onnx/model.onnx",
    license="MIT",
    size_bytes=133_093_490,  # 133.09 MB
    sha256="828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
    runtime="onnx",
    required=True,
    relative_path="bge-small-en-v1.5/model.onnx",
    min_ram_gb=4.0,
    min_vram_gb=0.0,
)

ARTIFACT_SPARK_FAST = ModelArtifact(
    id="spark-x2.5-1.7b-q4",
    name="Liquid AI Spark-X2.5-1.7B (Q4_K_M)",
    role=ModelRole.FAST_COGNITION,
    version="2.5",
    source_url="https://huggingface.co/LiquidAI/Spark-X2.5-1.7B-GGUF/resolve/main/Spark-X2.5-1.7B-Q4_K_M.gguf",
    license="Apache-2.0",
    size_bytes=1_107_457_856,  # 1.03 GB
    sha256="902bde2522394954ac17821b3e5fd0df02defbc6944f122253f2580acf0503f4",
    runtime="llama.cpp",
    required=True,
    relative_path="Spark-X2.5-1.7B-Q4_K_M.gguf",
    min_ram_gb=8.0,
    min_vram_gb=2.0,
)

ARTIFACT_QWEN_DEEP = ModelArtifact(
    id="qwen2.5-coder-1.5b-q4",
    name="Qwen 2.5 Coder 1.5B Instruct (Q4_K_M)",
    role=ModelRole.DEEP_COGNITION,
    version="2.5",
    source_url="https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
    license="Apache-2.0",
    size_bytes=1_117_320_768,  # 1.04 GB
    sha256="cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046",
    runtime="llama.cpp",
    required=True,
    relative_path="qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
    min_ram_gb=8.0,
    min_vram_gb=2.0,
)

ARTIFACT_OMNIPARSER_YOLO = ModelArtifact(
    id="omniparser-v2-icon-detect",
    name="Microsoft OmniParser v2.0 Icon Detector (YOLOv8)",
    role=ModelRole.VISUAL_GROUNDER,
    version="2.0",
    source_url="https://huggingface.co/microsoft/OmniParser-v2.0/resolve/main/icon_detect/model.pt",
    license="MIT",
    size_bytes=40_623_819,  # 40.62 MB
    sha256="dab3d4351ad00b035db829909a4db98354d5a90f6990e4ac00222a9a95d4bf57",
    runtime="torch/yolo",
    required=False,
    relative_path="OmniParser/icon_detect/model.pt",
    min_ram_gb=8.0,
    min_vram_gb=0.0,
)

ARTIFACT_SMOLVLM = ModelArtifact(
    id="smolvlm-500m",
    name="Hugging Face SmolVLM-500M Instruct",
    role=ModelRole.VISUAL_REASONER,
    version="1.0",
    source_url="https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct/resolve/main/model.safetensors",
    license="Apache-2.0",
    size_bytes=1_015_025_832,  # 1.01 GB
    sha256="d05b567eeaf534e83d375551f068ed57b5f52d37c657197f644af5ef9db091a2",
    runtime="transformers",
    required=False,
    relative_path="SmolVLM-500M/model.safetensors",
    min_ram_gb=12.0,
    min_vram_gb=0.0,
)


STANDARD_COGNITIVE_PACK = ManagedModelPack(
    id="pack-standard-cognition",
    name="Astra Standard Cognitive Pack",
    description="Dual Spark/Qwen cognition engines with BGE-small semantic embedding index.",
    min_ram_gb=12.0,
    min_vram_gb=3.5,
    artifacts=[ARTIFACT_BGE_EMBEDDING, ARTIFACT_SPARK_FAST, ARTIFACT_QWEN_DEEP],
)

VISION_ADDON_PACK = ManagedModelPack(
    id="pack-vision-extension",
    name="Astra Visual Perception Pack",
    description="OmniParser icon detector and SmolVLM visual reasoner for GUI control surfaces.",
    min_ram_gb=16.0,
    min_vram_gb=4.0,
    artifacts=[ARTIFACT_OMNIPARSER_YOLO, ARTIFACT_SMOLVLM],
)

ALL_MANAGED_PACKS = [STANDARD_COGNITIVE_PACK, VISION_ADDON_PACK]
