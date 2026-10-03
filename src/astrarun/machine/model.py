"""Authoritative MachineModel for AstraRun 1.0.

Maintains normalized, provenanced, and freshness-aware workstation intelligence.
Persists in isolated SQLite database (data/machine/machine_facts.db).
Supports incremental change detection and lazy freshness-driven refresh.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.machine.fact import FactAuthority, FactSensitivity, FreshnessClass, MachineFact
from astrarun.machine.providers.base import BaseMachineProvider
from astrarun.machine.providers.hardware import HardwareProvider
from astrarun.machine.providers.os_model import OSModelProvider
from astrarun.machine.providers.python_env import PythonEnvProvider
from astrarun.machine.providers.software import SoftwareProvider
from astrarun.machine.providers.topology import TopologyProvider
from astrarun.machine.resource_snapshot import ResourceSnapshot

logger = get_logger("astrarun.machine.model")


@dataclass
class MachineChangeEvent:
    """Emitted when critical machine hardware or environment state changes."""
    change_type: str  # STORAGE_CHANGED, NETWORK_CHANGED, POWER_CHANGED, VRAM_DROPPED
    key: str
    old_value: Any
    new_value: Any
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_type": self.change_type,
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "timestamp": self.timestamp,
        }


class MachineModel:
    """Central authoritative machine intelligence model."""

    _instance: Optional[MachineModel] = None

    def __init__(
        self,
        db_path: Optional[Path] = None,
        providers: Optional[List[BaseMachineProvider]] = None,
    ) -> None:
        self.db_path = Path(db_path or Path("data/machine/machine_facts.db")).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.providers: Dict[str, BaseMachineProvider] = {}
        prov_list = providers or [
            HardwareProvider(),
            OSModelProvider(),
            SoftwareProvider(),
            PythonEnvProvider(),
            TopologyProvider(),
        ]
        for p in prov_list:
            self.providers[p.name] = p

        self._facts: Dict[str, MachineFact] = {}
        self._recent_changes: List[MachineChangeEvent] = []
        self._init_db()
        self._load_from_db()

    @classmethod
    def get_instance(cls) -> MachineModel:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_db(self) -> None:
        """Initialize machine intelligence database."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS machine_facts (
                        key TEXT PRIMARY KEY,
                        value_json TEXT NOT NULL,
                        unit TEXT,
                        source TEXT NOT NULL,
                        observed_at REAL NOT NULL,
                        freshness_class TEXT NOT NULL,
                        ttl_sec REAL,
                        confidence REAL NOT NULL,
                        authority TEXT NOT NULL,
                        sensitivity TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                """)
        finally:
            conn.close()

    def _load_from_db(self) -> None:
        """Load stored facts from database into memory."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("SELECT key, value_json, unit, source, observed_at, freshness_class, ttl_sec, confidence, authority, sensitivity, metadata_json FROM machine_facts")
            for row in cur.fetchall():
                try:
                    val = json.loads(row[1])
                    meta = json.loads(row[10])
                    fact = MachineFact(
                        key=row[0],
                        value=val,
                        unit=row[2],
                        source=FactAuthority(row[3]),
                        observed_at=row[4],
                        freshness_class=FreshnessClass(row[5]),
                        ttl_sec=row[6],
                        confidence=row[7],
                        authority=row[8],
                        sensitivity=FactSensitivity(row[9]),
                        metadata=meta,
                    )
                    self._facts[fact.key] = fact
                except Exception as e:
                    logger.debug("Failed parsing row for fact %s: %s", row[0], e)
        finally:
            conn.close()

    def _persist_fact(self, fact: MachineFact) -> None:
        """Persist a single fact to SQLite."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            with conn:
                conn.execute("""
                    INSERT OR REPLACE INTO machine_facts (
                        key, value_json, unit, source, observed_at, freshness_class,
                        ttl_sec, confidence, authority, sensitivity, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fact.key,
                    json.dumps(fact.value),
                    fact.unit,
                    fact.source.value,
                    fact.observed_at,
                    fact.freshness_class.value,
                    fact.ttl_sec,
                    fact.confidence,
                    fact.authority,
                    fact.sensitivity.value,
                    json.dumps(fact.metadata),
                ))
        finally:
            conn.close()

    def set_fact(self, fact: MachineFact) -> None:
        """Store fact and detect changes."""
        old_fact = self._facts.get(fact.key)
        if old_fact is not None and old_fact.value != fact.value:
            self._check_for_critical_change(fact.key, old_fact.value, fact.value)

        self._facts[fact.key] = fact
        self._persist_fact(fact)

    def _check_for_critical_change(self, key: str, old_val: Any, new_val: Any) -> None:
        """Identify critical system state transitions."""
        if key == "hardware.storage.volumes":
            event = MachineChangeEvent("STORAGE_CHANGED", key, old_val, new_val)
            self._recent_changes.append(event)
            logger.info("Machine Change Detected: Storage volumes changed from %s to %s", old_val, new_val)
        elif key == "hardware.network.connected":
            event = MachineChangeEvent("NETWORK_CHANGED", key, old_val, new_val)
            self._recent_changes.append(event)
            logger.info("Machine Change Detected: Network connected changed to %s", new_val)
        elif key == "hardware.power.ac_connected":
            event = MachineChangeEvent("POWER_CHANGED", key, old_val, new_val)
            self._recent_changes.append(event)
            logger.info("Machine Change Detected: Power state changed to %s", new_val)

    def bootstrap(self, quick: bool = False) -> None:
        """Execute bounded machine discovery across all registered providers."""
        t0 = time.perf_counter()
        logger.info("Bootstrapping MachineModel discovery...")

        for prov_name, provider in self.providers.items():
            try:
                facts = provider.discover()
                for f in facts:
                    self.set_fact(f)
            except Exception as e:
                logger.error("Provider '%s' failed during bootstrap: %s", prov_name, e)

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        logger.info("MachineModel bootstrapped: %d facts cataloged in %sms", len(self._facts), duration_ms)
        return len(self._facts)

    def get_fact(self, key: str, allow_stale: bool = False) -> Optional[MachineFact]:
        """Retrieve fact by key with freshness validation."""
        fact = self._facts.get(key)
        if fact is None:
            return None

        if not allow_stale and fact.needs_refresh():
            # Trigger lazy provider refresh for the relevant domain
            self._refresh_key_domain(key)
            return self._facts.get(key)

        return fact

    def query_facts(
        self,
        prefix: Optional[str] = None,
        fresh_only: bool = False,
        sensitivity_max: Optional[FactSensitivity] = None,
    ) -> List[MachineFact]:
        """Query matching facts with optional filtering."""
        res: List[MachineFact] = []
        now = time.time()

        for k, f in self._facts.items():
            if prefix and not k.startswith(prefix):
                continue
            if fresh_only and not f.is_fresh(now):
                continue
            if sensitivity_max == FactSensitivity.PUBLIC and f.sensitivity != FactSensitivity.PUBLIC:
                continue
            res.append(f)

        return res

    def _refresh_key_domain(self, key: str) -> None:
        """Targeted lazy refresh for an expired fact domain."""
        if key.startswith("hardware.") and "hardware" in self.providers:
            for f in self.providers["hardware"].refresh():
                self.set_fact(f)
        elif key.startswith("software.") and "software" in self.providers:
            for f in self.providers["software"].refresh():
                self.set_fact(f)

    def refresh_volatile(self) -> None:
        """Refresh dynamic volatile metrics (RAM, disk, power, network)."""
        snap = ResourceSnapshot.capture(include_gpu=False)
        now = time.time()
        self.set_fact(MachineFact("hardware.memory.available_gb", snap.available_ram_gb, unit="GB", freshness_class=FreshnessClass.VOLATILE, observed_at=now))
        self.set_fact(MachineFact("hardware.network.connected", snap.network_connected, freshness_class=FreshnessClass.VOLATILE, observed_at=now))
        self.set_fact(MachineFact("hardware.power.ac_connected", snap.power_plugged, freshness_class=FreshnessClass.VOLATILE, observed_at=now))
        if snap.battery_percent is not None:
            self.set_fact(MachineFact("hardware.power.battery_percent", snap.battery_percent, unit="%", freshness_class=FreshnessClass.VOLATILE, observed_at=now))

    def refresh_realtime(self) -> None:
        """Refresh realtime metrics (free VRAM)."""
        snap = ResourceSnapshot.capture(include_gpu=True)
        now = time.time()
        self.set_fact(MachineFact("hardware.gpu.vram_free_gb", snap.free_vram_gb, unit="GB", freshness_class=FreshnessClass.REALTIME, observed_at=now))

    def get_recent_changes(self) -> List[MachineChangeEvent]:
        return list(self._recent_changes)
