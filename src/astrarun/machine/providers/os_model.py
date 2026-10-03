"""Operating System discovery provider for AstraRun 1.0."""

from __future__ import annotations

import ctypes
import os
import platform
import sys
import time
from typing import List

from astrarun.core.logging import get_logger
from astrarun.machine.fact import FactAuthority, FreshnessClass, MachineFact
from astrarun.machine.providers.base import BaseMachineProvider

logger = get_logger("astrarun.machine.providers.os_model")


class OSModelProvider(BaseMachineProvider):
    """Discovers and normalizes Windows OS configuration facts."""

    name = "os_model"

    def discover(self) -> List[MachineFact]:
        facts: List[MachineFact] = []
        now = time.time()

        os_name = f"Windows {platform.release()}" if sys.platform == "win32" else platform.system()
        edition = "Windows"
        build_num = "Unknown"
        long_paths = False
        uac_enabled = True

        if sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                    prod_name, _ = winreg.QueryValueEx(key, "ProductName")
                    edition = str(prod_name)
                    b_num, _ = winreg.QueryValueEx(key, "CurrentBuild")
                    build_num = str(b_num)
            except Exception as e:
                logger.debug("Registry OS query fallback: %s", e)

            # Long path support
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
                    val, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
                    long_paths = bool(val)
            except Exception:
                pass

            # UAC enabled
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System") as key:
                    val, _ = winreg.QueryValueEx(key, "EnableLUA")
                    uac_enabled = bool(val)
            except Exception:
                pass

        # Is process elevated (Administrator)
        is_admin = False
        if sys.platform == "win32":
            try:
                is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            except Exception:
                is_admin = False

        facts.append(MachineFact(
            key="os.name",
            value=os_name,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.IMMUTABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="os.edition",
            value=edition,
            source=FactAuthority.REGISTRY if sys.platform == "win32" else FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="os.version",
            value=platform.version(),
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="os.build",
            value=build_num,
            source=FactAuthority.REGISTRY if sys.platform == "win32" else FactAuthority.OS_API,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="os.architecture",
            value=platform.machine(),
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.IMMUTABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="os.timezone",
            value=time.tzname[0] if time.tzname else "UTC",
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="os.is_admin",
            value=is_admin,
            source=FactAuthority.OS_API,
            freshness_class=FreshnessClass.SESSION,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="os.uac_enabled",
            value=uac_enabled,
            source=FactAuthority.REGISTRY,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        facts.append(MachineFact(
            key="os.long_paths_enabled",
            value=long_paths,
            source=FactAuthority.REGISTRY,
            freshness_class=FreshnessClass.STABLE,
            observed_at=now,
        ))
        return facts
