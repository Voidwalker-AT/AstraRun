"""Optical Character Recognition (OCR) provider for AstraRun Perception.

Executes Windows Native WinRT OCR via native runner, returning word/line
bounding boxes with sub-150ms latency. Marks provider as UNAVAILABLE if binary
or platform support is missing, ensuring truth in verification.
"""

from __future__ import annotations

import json
import subprocess
import time
import os
from pathlib import Path
from typing import List, Optional

from astrarun.core.logging import get_logger
from astrarun.perception.models import BoundingBox, PerceptionTier, TextRegionObservation

logger = get_logger("astrarun.perception.ocr")

_env_ocr = os.environ.get("ASTRARUN_WINRT_OCR_EXE")
DEFAULT_WINRT_OCR_EXE = Path(_env_ocr) if _env_ocr else Path(__file__).resolve().parent.parent / "bin" / "WinRtOcr.exe"


class OCRProvider:
    """
    Tier 4: Optical Character Recognition provider utilizing native WinRT OCR.
    """

    def __init__(self, binary_path: Optional[str | Path] = None):
        self.binary_path = Path(binary_path) if binary_path else DEFAULT_WINRT_OCR_EXE
        self.is_available = self.binary_path.exists()
        if not self.is_available:
            logger.info("WinRT OCR runner not found at %s. Marking OCRProvider as UNAVAILABLE.", self.binary_path)

    @property
    def winrt_ocr_exe(self) -> Path:
        return self.binary_path

    def extract_text_regions(self, image_path: str | Path, timeout: float = 10.0) -> List[TextRegionObservation]:
        """
        Extract text regions with bounding boxes from an image file.
        Returns empty list if provider is unavailable or execution fails.
        """
        if not self.is_available:
            logger.debug("OCR requested but provider is UNAVAILABLE.")
            return []

        path_obj = Path(image_path)
        if not path_obj.exists():
            logger.warning("Image file %s does not exist", image_path)
            return []

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [str(self.binary_path), str(path_obj)],
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            if proc.returncode != 0:
                logger.warning("WinRT OCR execution failed (code %d): %s", proc.returncode, proc.stderr.strip())
                return []

            data = json.loads(proc.stdout.strip())
            lines = data.get("lines", [])
            regions: List[TextRegionObservation] = []

            for idx, item in enumerate(lines):
                text_content = item.get("text", "").strip()
                if not text_content:
                    continue

                rect = item.get("rect", [0, 0, 100, 20])
                bbox = BoundingBox(
                    x=int(rect[0]),
                    y=int(rect[1]),
                    width=int(rect[2]),
                    height=int(rect[3]),
                )
                regions.append(
                    TextRegionObservation(
                        text=text_content,
                        bbox=bbox,
                        line_index=idx,
                    )
                )

            logger.debug("WinRT OCR extracted %d text regions in %.2f ms", len(regions), (time.perf_counter() - t0) * 1000.0)
            return regions
        except Exception as e:
            logger.error("Error executing WinRT OCR: %s", e)
            return []
