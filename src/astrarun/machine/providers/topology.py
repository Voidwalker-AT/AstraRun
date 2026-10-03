"""Filesystem and workspace topology provider for AstraRun 1.0.

Discovers well-known machine locations and authorized workspace boundaries
without recursive personal file scanning or content indexing.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from astrarun.core.logging import get_logger
from astrarun.machine.fact import FactAuthority, FactSensitivity, FreshnessClass, MachineFact
from astrarun.machine.providers.base import BaseMachineProvider

logger = get_logger("astrarun.machine.providers.topology")


class TopologyProvider(BaseMachineProvider):
    """Authoritative filesystem boundary and workspace registry provider."""

    name = "topology"

    def __init__(self, authorized_roots: Optional[List[Path]] = None) -> None:
        self.authorized_roots = authorized_roots or [
            Path(r"E:\Workspace"),
            Path(r"E:\AI_Models"),
        ]

    def discover(self) -> List[MachineFact]:
        facts: List[MachineFact] = []
        now = time.time()

        # 1. Standard System & User Locations
        home = Path.home()
        desktop = home / "Desktop"
        docs = home / "Documents"
        downloads = home / "Downloads"
        temp_dir = Path(tempfile.gettempdir())
        local_app_data = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        prog_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))

        locations = {
            "user_profile": home,
            "desktop": desktop,
            "documents": docs,
            "downloads": downloads,
            "temp": temp_dir,
            "local_app_data": local_app_data,
            "program_files": prog_files,
        }

        for loc_name, p in locations.items():
            facts.append(MachineFact(
                key=f"topology.path.{loc_name}",
                value=str(p),
                source=FactAuthority.FILESYSTEM,
                freshness_class=FreshnessClass.STABLE,
                observed_at=now,
                sensitivity=FactSensitivity.INTERNAL,
            ))
            facts.append(MachineFact(
                key=f"topology.path.{loc_name}.exists",
                value=p.exists(),
                source=FactAuthority.FILESYSTEM,
                freshness_class=FreshnessClass.STABLE,
                observed_at=now,
            ))

        # 2. Configured AI Model Storage
        models_root = Path(r"E:\AI_Models")
        has_models_root = models_root.exists() and models_root.is_dir()
        facts.append(MachineFact(
            key="topology.models.root",
            value=str(models_root),
            source=FactAuthority.FILESYSTEM,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
            sensitivity=FactSensitivity.INTERNAL,
        ))
        facts.append(MachineFact(
            key="topology.models.available",
            value=has_models_root,
            source=FactAuthority.FILESYSTEM,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))

        # 3. Scoped Workspace Registry
        workspaces: List[Dict[str, Any]] = []
        ws_root = Path(r"E:\Workspace")
        if ws_root.exists() and ws_root.is_dir():
            # Check known subdirectories (Active, Tools, Academic)
            for sub in ["Active", "Tools"]:
                sub_dir = ws_root / sub
                if sub_dir.exists() and sub_dir.is_dir():
                    try:
                        for child in sub_dir.iterdir():
                            if child.is_dir() and not child.name.startswith("."):
                                has_git = (child / ".git").exists()
                                workspaces.append({
                                    "name": child.name,
                                    "root": str(child),
                                    "has_git": has_git,
                                    "category": sub,
                                })
                    except Exception as e:
                        logger.debug("Error iterating workspace dir %s: %s", sub_dir, e)

        facts.append(MachineFact(
            key="topology.workspaces.registered",
            value=workspaces,
            source=FactAuthority.FILESYSTEM,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
            sensitivity=FactSensitivity.INTERNAL,
        ))

        return facts
