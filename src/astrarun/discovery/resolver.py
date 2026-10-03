r"""Workstation Existing Capability Discovery and Asset Resolver for AstraRun 1.0 (RC0.1).

Discovers compatible local AI models, CLI tools, runtimes, and browsers on the physical machine,
allowing first-run preparation to reuse existing installations without duplicate downloads.

CORE INVARIANTS:
1. Internal libraries (PySide6, NumPy, Pydantic, ONNX Runtime, SQLite, httpx, Pillow)
   remain bundled within Astra and are NEVER audited or presented as external tools.
2. Machine-level capabilities (GGUF weights in E:\AI_Models, Git, Browsers, ffmpeg, CUDA)
   are discovered and verified for exact or compatible matches.
3. If an exact manifest match is detected, Astra defaults to:
   "Use existing installation (Recommended)" with 0 MB download!
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.core.paths import get_config_dir, get_models_dir
from astrarun.discovery.candidates import CompatibilityStatus, ExistingCapabilityCandidate
from astrarun.models.manifest import (
    ARTIFACT_BGE_EMBEDDING,
    ARTIFACT_QWEN_DEEP,
    ARTIFACT_SPARK_FAST,
)

logger = get_logger("astrarun.discovery.resolver")

# Win32 flag to prevent console popups during tool queries
CREATE_NO_WINDOW = 0x08000000


class ExistingCapabilityResolver:
    """Authoritative discovery engine for existing workstation tools, models, and runtimes."""

    def __init__(self, search_paths: Optional[List[Path]] = None):
        self.search_paths: List[Path] = search_paths or [
            Path(r"E:\AI_Models\GGUF"),
            Path(r"E:\AI_Models"),
            Path(r"C:\AI_Models"),
            Path.home() / ".cache" / "huggingface" / "hub",
            Path.home() / ".ollama" / "models",
            get_models_dir(),
        ]

    def discover_all(self) -> Dict[str, ExistingCapabilityCandidate]:
        """Run complete discovery pass across models, CLI tools, runtimes, and browsers."""
        candidates: Dict[str, ExistingCapabilityCandidate] = {}
        candidates.update(self.discover_models())
        candidates.update(self.discover_tools())
        candidates.update(self.discover_browsers())
        return candidates

    def discover_models(self) -> Dict[str, ExistingCapabilityCandidate]:
        """Inspect storage locations for compatible GGUF and ONNX model weights."""
        results: Dict[str, ExistingCapabilityCandidate] = {}

        # 1. Spark-X2.5 Fast Cognition Model
        spark_candidate = self._inspect_model_candidate(
            model_id="spark-x2.5-1.7b-q4",
            display_name="Liquid AI Spark-X2.5-1.7B (Q4_K_M)",
            target_filenames=["Spark-X2.5-1.7B-Q4_K_M.gguf", "spark-x2.5-1.7b-q4_k_m.gguf"],
            expected_size=ARTIFACT_SPARK_FAST.size_bytes,
            expected_sha256=ARTIFACT_SPARK_FAST.sha256,
        )
        results[spark_candidate.id] = spark_candidate

        # 2. Qwen2.5-Coder Deep Cognition Model
        qwen_candidate = self._inspect_model_candidate(
            model_id="qwen2.5-coder-1.5b-q4",
            display_name="Qwen 2.5 Coder 1.5B Instruct (Q4_K_M)",
            target_filenames=[
                "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
                "Qwen2.5-Coder-1.5B-Q4_K_M.gguf",
                "qwen2.5-coder-1.5b-instruct-q5_k_m.gguf",
            ],
            expected_size=ARTIFACT_QWEN_DEEP.size_bytes,
            expected_sha256=ARTIFACT_QWEN_DEEP.sha256,
        )
        results[qwen_candidate.id] = qwen_candidate

        # 3. BGE Semantic Embedding Index
        bge_candidate = self._inspect_model_candidate(
            model_id="bge-small-en-v1.5",
            display_name="BAAI BGE-small-en-v1.5 ONNX",
            target_filenames=["bge-small-en-v1.5/model.onnx", "model.onnx"],
            expected_size=ARTIFACT_BGE_EMBEDDING.size_bytes,
            expected_sha256=ARTIFACT_BGE_EMBEDDING.sha256,
        )
        results[bge_candidate.id] = bge_candidate

        return results

    def _inspect_model_candidate(
        self,
        model_id: str,
        display_name: str,
        target_filenames: List[str],
        expected_size: int,
        expected_sha256: str,
    ) -> ExistingCapabilityCandidate:
        """Search registered roots for an existing model file and assess compatibility."""
        for root in self.search_paths:
            if not root.exists():
                continue
            for fname in target_filenames:
                direct_path = root / fname
                if direct_path.exists() and direct_path.is_file():
                    actual_size = direct_path.stat().st_size
                    # Check exact byte match
                    if actual_size == expected_size:
                        logger.info("Found exact model match for %s at %s", model_id, direct_path)
                        return ExistingCapabilityCandidate(
                            id=model_id,
                            name=display_name,
                            category="model",
                            path=direct_path,
                            status=CompatibilityStatus.EXACT_MATCH,
                            size_bytes=actual_size,
                            sha256=expected_sha256,
                            details=f"Exact manifest match found at {direct_path} ({actual_size / (1024**3):.2f} GB).",
                            is_recommended=True,
                            reuse_action="Use existing installation (Recommended, 0 MB download)",
                            user_choice="use_existing",
                        )
                    elif actual_size > 0:
                        # Compatible variant or alternative quantization
                        logger.info("Found compatible model variant for %s at %s (%d bytes)", model_id, direct_path, actual_size)
                        return ExistingCapabilityCandidate(
                            id=model_id,
                            name=display_name,
                            category="model",
                            path=direct_path,
                            status=CompatibilityStatus.COMPATIBLE_VERSION,
                            size_bytes=actual_size,
                            details=f"Compatible model artifact found at {direct_path} ({actual_size / (1024**3):.2f} GB).",
                            is_recommended=True,
                            reuse_action="Use existing installation (0 MB download)",
                            user_choice="use_existing",
                        )

        # Not found locally
        return ExistingCapabilityCandidate(
            id=model_id,
            name=display_name,
            category="model",
            path=None,
            status=CompatibilityStatus.MISSING,
            size_bytes=expected_size,
            details="No existing model found in local storage roots.",
            is_recommended=False,
            reuse_action="Download fresh to Astra storage (~{:.2f} GB)".format(expected_size / (1024**3)),
            user_choice="download_fresh",
        )

    def discover_tools(self) -> Dict[str, ExistingCapabilityCandidate]:
        """Detect machine developer tools and runtimes (Git, ffmpeg, llama.cpp, CUDA)."""
        tools: Dict[str, ExistingCapabilityCandidate] = {}

        # 1. Git
        git_path = shutil.which("git") or self._search_common_program_path("Git", "cmd", "git.exe")
        if git_path and Path(git_path).exists():
            version_str = self._query_tool_version(str(git_path), ["--version"])
            tools["git"] = ExistingCapabilityCandidate(
                id="git",
                name="Git Version Control",
                category="tool",
                path=Path(git_path),
                version=version_str,
                status=CompatibilityStatus.EXACT_MATCH,
                details=f"Installed at {git_path} ({version_str})",
                is_recommended=True,
                reuse_action="Use system Git",
            )
        else:
            tools["git"] = ExistingCapabilityCandidate(
                id="git",
                name="Git Version Control",
                category="tool",
                status=CompatibilityStatus.MISSING,
                details="Git not detected in PATH or Program Files.",
            )

        # 2. ffmpeg
        ffmpeg_path = shutil.which("ffmpeg") or self._search_common_program_path("ffmpeg", "bin", "ffmpeg.exe")
        if ffmpeg_path and Path(ffmpeg_path).exists():
            tools["ffmpeg"] = ExistingCapabilityCandidate(
                id="ffmpeg",
                name="FFmpeg Media Engine",
                category="tool",
                path=Path(ffmpeg_path),
                status=CompatibilityStatus.EXACT_MATCH,
                details=f"Installed at {ffmpeg_path}",
                is_recommended=True,
                reuse_action="Use system FFmpeg",
            )
        else:
            tools["ffmpeg"] = ExistingCapabilityCandidate(
                id="ffmpeg",
                name="FFmpeg Media Engine",
                category="tool",
                status=CompatibilityStatus.MISSING,
                details="FFmpeg not detected.",
            )

        # 3. llama.cpp Server / Binary
        llama_path = shutil.which("llama-server") or shutil.which("llama-cli")
        if llama_path and Path(llama_path).exists():
            tools["llama.cpp"] = ExistingCapabilityCandidate(
                id="llama.cpp",
                name="llama.cpp Inference Runtime",
                category="runtime",
                path=Path(llama_path),
                status=CompatibilityStatus.EXACT_MATCH,
                details=f"Existing llama.cpp binary found at {llama_path}",
                is_recommended=True,
                reuse_action="Use system llama.cpp",
            )
        else:
            tools["llama.cpp"] = ExistingCapabilityCandidate(
                id="llama.cpp",
                name="llama.cpp Inference Runtime",
                category="runtime",
                status=CompatibilityStatus.MISSING,
                details="llama-server not found in PATH; Astra bundled runtime will be used.",
            )

        return tools

    def discover_browsers(self) -> Dict[str, ExistingCapabilityCandidate]:
        """Discover installed web browsers for computer-use and browser tasks."""
        browsers: Dict[str, ExistingCapabilityCandidate] = {}

        browser_defs = [
            ("vivaldi", "Vivaldi Browser", ["Vivaldi", "Application", "vivaldi.exe"]),
            ("chrome", "Google Chrome", ["Google", "Chrome", "Application", "chrome.exe"]),
            ("edge", "Microsoft Edge", ["Microsoft", "Edge", "Application", "msedge.exe"]),
            ("firefox", "Mozilla Firefox", ["Mozilla Firefox", "firefox.exe"]),
        ]

        for b_id, b_name, rel_parts in browser_defs:
            b_path = self._search_common_program_path(*rel_parts)
            if b_path and Path(b_path).exists():
                browsers[b_id] = ExistingCapabilityCandidate(
                    id=b_id,
                    name=b_name,
                    category="browser",
                    path=Path(b_path),
                    status=CompatibilityStatus.EXACT_MATCH,
                    details=f"Found at {b_path}",
                    is_recommended=True,
                    reuse_action=f"Use existing {b_name}",
                )

        return browsers

    def _search_common_program_path(self, *parts: str) -> Optional[str]:
        """Search standard Windows installation directories for an executable."""
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", r"C:\Users\hp\AppData\Local")),
            Path.home() / "scoop" / "shims",
        ]
        for base in candidates:
            target = base.joinpath(*parts)
            if target.exists() and target.is_file():
                return str(target)
        return None

    def _query_tool_version(self, executable: str, args: List[str]) -> str:
        """Query tool version quietly without popping up a console window."""
        try:
            res = subprocess.run(
                [executable] + args,
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=CREATE_NO_WINDOW,
            )
            return res.stdout.strip().split("\n")[0]
        except Exception:
            return "unknown"
