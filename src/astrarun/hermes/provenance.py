"""Provenance and Environmental Scoping for Hermes Experiential Memory.

Guarantees cryptographic anchoring of learned knowledge to:
- Specific host OS build and display topology (prevents invalid cross-machine reuse)
- Specific binary executable hash (prevents cross-version contamination)
- Specific task trace, model prompt, and frame transitions
"""

from __future__ import annotations

import hashlib
import os
import platform
import sys
from pathlib import Path
from typing import Optional


class HermesProvenance:
    """Computes deterministic environment hashes and binary identity hashes."""

    @staticmethod
    def compute_env_hash() -> str:
        """Compute a deterministic hash of the host execution environment."""
        items = [
            platform.system(),
            platform.release(),
            platform.version(),
            platform.machine(),
        ]
        # In Windows, capture display metrics if win32 API is accessible
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                w = user32.GetSystemMetrics(0) # SM_CXSCREEN
                h = user32.GetSystemMetrics(1) # SM_CYSCREEN
                items.append(f"{w}x{h}")
            except Exception:
                pass

        raw = "|".join(items).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    @staticmethod
    def compute_binary_hash(binary_path: str | Path) -> Optional[str]:
        """Compute SHA-256 of the target executable binary if accessible."""
        p = Path(binary_path)
        if not p.exists() or not p.is_file():
            return None
        try:
            h = hashlib.sha256()
            with open(p, "rb") as fp:
                while chunk := fp.read(65536):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    @staticmethod
    def hash_text(text: str) -> str:
        """Deterministic SHA-256 of text payload."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
