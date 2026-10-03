"""Python environment and runtime package discovery for AstraRun 1.0."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.machine.fact import FactAuthority, FreshnessClass, MachineFact
from astrarun.machine.providers.base import BaseMachineProvider

logger = get_logger("astrarun.machine.providers.python_env")

KEY_PACKAGES = [
    "numpy",
    "matplotlib",
    "torch",
    "transformers",
    "onnxruntime",
    "pyside6",
    "psutil",
    "scipy",
    "pillow",
]


class PythonEnvProvider(BaseMachineProvider):
    """Scoped Python environment and installed package inventory provider."""

    name = "python_env"

    def discover(self) -> List[MachineFact]:
        facts: List[MachineFact] = []
        now = time.time()

        # 1. Active Astra Runtime Environment
        active_exe = sys.executable
        active_ver = platform.python_version()
        active_arch = platform.architecture()[0]

        facts.append(MachineFact(
            key="software.python.active.executable",
            value=active_exe,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="software.python.active.version",
            value=active_ver,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.IMMUTABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="software.python.active.architecture",
            value=active_arch,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.IMMUTABLE,
            observed_at=now,
        ))

        # Check if running in a virtual environment
        in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        facts.append(MachineFact(
            key="software.python.active.is_venv",
            value=in_venv,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))

        # 2. Host Python launcher (py.exe / system python)
        host_py = shutil.which("py") or shutil.which("python")
        facts.append(MachineFact(
            key="software.python.host.installed",
            value=host_py is not None,
            source=FactAuthority.FILESYSTEM,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        if host_py:
            facts.append(MachineFact(
                key="software.python.host.executable",
                value=host_py,
                source=FactAuthority.FILESYSTEM,
                freshness_class=FreshnessClass.SESSION,
                observed_at=now,
            ))

        # 3. Key Package Inventory in Active Environment
        dists: Dict[str, str] = {}
        try:
            for dist in importlib.metadata.distributions():
                name = dist.metadata.get("Name")
                if name:
                    dists[name.lower()] = dist.metadata.get("Version", "unknown")
        except Exception as e:
            logger.debug("Failed listing importlib distributions: %s", e)

        for pkg in KEY_PACKAGES:
            is_installed = pkg in dists
            facts.append(MachineFact(
                key=f"software.python.package.{pkg}.installed",
                value=is_installed,
                source=FactAuthority.APPLICATION_PROBE,
                freshness_class=FreshnessClass.SESSION,
                observed_at=now,
            ))
            if is_installed:
                facts.append(MachineFact(
                    key=f"software.python.package.{pkg}.version",
                    value=dists[pkg],
                    source=FactAuthority.APPLICATION_PROBE,
                    freshness_class=FreshnessClass.SESSION,
                    observed_at=now,
                ))

        return facts
