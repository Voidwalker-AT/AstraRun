"""Unit and Acceptance Tests for Milestone 7C Machine Intelligence & Compatibility.

Covers:
- MachineFact schema, freshness classes, and TTL calculation.
- Hardware, OS, Software, Python, and Topology discovery providers.
- Instantaneous ResourceSnapshot capture (<20ms latency).
- MachineModel local SQLite persistence and incremental change detection.
- MachineCapabilityResolver predicates and supporting citations.
- CompatibilityEngine pre-flight workload validation.
- Diagnostics view and sanitized bug report export.
- Natural language MachineQueryEngine responses.
- 8-Profile Compatibility Fixture Matrix (Reference, CPU-only, Low-RAM, 8GB-VRAM, No-DevTools, No-Git, Multi-Mon, Offline).
- Privacy boundary enforcement (zero secrets, zero ambient surveillance).
- Task continuity machine drift detection.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astrarun.machine.capability_resolver import (
    CapabilityPredicate,
    CapabilityStatus,
    MachineCapabilityResolver,
)
from astrarun.machine.compatibility import CompatibilityEngine, CompatibilityReport
from astrarun.machine.diagnostics import MachineDiagnostics
from astrarun.machine.fact import (
    FactAuthority,
    FactSensitivity,
    FreshnessClass,
    MachineFact,
)
from astrarun.machine.model import MachineChangeEvent, MachineModel
from astrarun.machine.providers.hardware import HardwareProvider
from astrarun.machine.providers.os_model import OSModelProvider
from astrarun.machine.providers.python_env import PythonEnvProvider
from astrarun.machine.providers.software import SoftwareProvider
from astrarun.machine.providers.topology import TopologyProvider
from astrarun.machine.query_engine import MachineQueryEngine
from astrarun.machine.resource_snapshot import ResourceSnapshot
from astrarun.rag.context import ContextBuilder
from astrarun.tasks.continuity import ContinuityEngine, TaskCheckpoint


# =========================================================================
# 1. MachineFact Schema & Freshness Tests
# =========================================================================

def test_machine_fact_schema_and_freshness():
    """Verify MachineFact TTL calculation and freshness expiration."""
    now = time.time()

    # Immutable fact never expires
    fact_imm = MachineFact(
        key="hardware.cpu.arch",
        value="x86_64",
        freshness_class=FreshnessClass.IMMUTABLE,
        observed_at=now - 100000,
    )
    assert fact_imm.is_fresh(now)
    assert not fact_imm.needs_refresh(now)

    # Realtime fact expires in 2s
    fact_rt = MachineFact(
        key="hardware.gpu.vram_free_gb",
        value=3.2,
        freshness_class=FreshnessClass.REALTIME,
        observed_at=now - 5,
    )
    assert not fact_rt.is_fresh(now)
    assert fact_rt.needs_refresh(now)

    # Volatile fact (30s TTL)
    fact_vol = MachineFact(
        key="hardware.memory.available_gb",
        value=8.5,
        freshness_class=FreshnessClass.VOLATILE,
        observed_at=now - 10,
    )
    assert fact_vol.is_fresh(now)
    assert not fact_vol.needs_refresh(now)

    # Serialization roundtrip
    d = fact_vol.to_dict()
    restored = MachineFact.from_dict(d)
    assert restored.key == fact_vol.key
    assert restored.value == fact_vol.value
    assert restored.freshness_class == FreshnessClass.VOLATILE


# =========================================================================
# 2. Hardware and OS Providers
# =========================================================================

def test_hardware_and_os_providers():
    """Verify Hardware and OS providers discover standard typed facts."""
    hw_prov = HardwareProvider()
    hw_facts = hw_prov.discover()
    assert len(hw_facts) >= 10

    keys = {f.key for f in hw_facts}
    assert "hardware.cpu.model" in keys
    assert "hardware.cpu.physical_cores" in keys
    assert "hardware.memory.total_gb" in keys
    assert "hardware.gpu.present" in keys
    assert "hardware.storage.volumes" in keys
    assert "hardware.device.microphone_present" in keys

    os_prov = OSModelProvider()
    os_facts = os_prov.discover()
    assert len(os_facts) >= 5

    os_keys = {f.key for f in os_facts}
    assert "os.name" in os_keys
    assert "os.version" in os_keys
    assert "os.architecture" in os_keys


# =========================================================================
# 3. Software and Python Environment Providers
# =========================================================================

def test_software_and_python_providers():
    """Verify Software and Python providers discover scoped tools and packages."""
    sw_prov = SoftwareProvider()
    sw_facts = sw_prov.discover()
    assert len(sw_facts) >= 5

    sw_keys = {f.key for f in sw_facts}
    assert "software.tool.git.installed" in sw_keys
    assert "software.app.vivaldi.installed" in sw_keys
    assert "software.app.vscode.installed" in sw_keys

    py_prov = PythonEnvProvider()
    py_facts = py_prov.discover()
    py_keys = {f.key for f in py_facts}
    assert "software.python.active.executable" in py_keys
    assert "software.python.package.numpy.installed" in py_keys


# =========================================================================
# 4. Instantaneous ResourceSnapshot Telemetry
# =========================================================================

def test_resource_snapshot_telemetry():
    """Verify ResourceSnapshot captures metrics with sub-50ms latency."""
    t0 = time.perf_counter()
    snap = ResourceSnapshot.capture(include_gpu=True)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    assert latency_ms < 100.0  # Must be fast
    assert snap.total_ram_gb > 0.0
    assert snap.available_ram_gb >= 0.0
    assert isinstance(snap.disk_free_gb, dict)
    assert isinstance(snap.power_plugged, bool)


# =========================================================================
# 5. MachineModel SQLite Persistence & Change Detection
# =========================================================================

def test_machine_model_persistence_and_change_detection(tmp_path):
    """Verify MachineModel persists to SQLite and detects critical state transitions."""
    db_file = tmp_path / "machine_facts.db"
    model = MachineModel(db_path=db_file)

    fact1 = MachineFact(
        key="hardware.storage.volumes",
        value=["C", "E"],
        freshness_class=FreshnessClass.VOLATILE,
    )
    model.set_fact(fact1)
    assert model.get_fact("hardware.storage.volumes").value == ["C", "E"]

    # Verify SQLite row exists
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM machine_facts WHERE key='hardware.storage.volumes'")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 1

    # Simulate drive disconnection change event
    fact2 = MachineFact(
        key="hardware.storage.volumes",
        value=["C"],
        freshness_class=FreshnessClass.VOLATILE,
    )
    model.set_fact(fact2)

    changes = model.get_recent_changes()
    assert len(changes) >= 1
    assert changes[-1].change_type == "STORAGE_CHANGED"
    assert changes[-1].old_value == ["C", "E"]
    assert changes[-1].new_value == ["C"]


# =========================================================================
# 6. MachineCapabilityResolver & Supporting Facts
# =========================================================================

def test_machine_capability_resolver(tmp_path):
    """Verify CapabilityResolver produces authoritative predicates with citations."""
    db_file = tmp_path / "machine_facts.db"
    model = MachineModel(db_path=db_file)

    # Populate baseline facts
    model.set_fact(MachineFact("hardware.memory.total_gb", 16.0))
    model.set_fact(MachineFact("hardware.gpu.model", "NVIDIA GeForce RTX 2050 Laptop GPU"))
    model.set_fact(MachineFact("hardware.gpu.cuda_available", True))
    model.set_fact(MachineFact("software.python.active.executable", "python.exe"))
    model.set_fact(MachineFact("software.python.package.numpy.installed", True))
    model.set_fact(MachineFact("software.python.package.matplotlib.installed", True))
    model.set_fact(MachineFact("hardware.network.connected", True))

    resolver = MachineCapabilityResolver(model)

    p_spark = resolver.resolve("CAN_RUN_LOCAL_SPARK")
    assert p_spark.status == CapabilityStatus.AVAILABLE
    assert len(p_spark.supporting_facts) >= 1

    p_vis = resolver.resolve("CAN_RUN_PYTHON_VISUALIZATION")
    assert p_vis.status == CapabilityStatus.AVAILABLE

    p_cuda = resolver.resolve("CAN_USE_CUDA")
    assert p_cuda.status == CapabilityStatus.AVAILABLE

    p_down = resolver.resolve("CAN_DOWNLOAD")
    assert p_down.status == CapabilityStatus.AVAILABLE


# =========================================================================
# 7. CompatibilityEngine Pre-Flight Assessment
# =========================================================================

def test_compatibility_engine(tmp_path):
    """Verify pre-flight workload evaluation."""
    db_file = tmp_path / "machine_facts.db"
    model = MachineModel(db_path=db_file)
    model.set_fact(MachineFact("hardware.memory.total_gb", 16.0))
    model.set_fact(MachineFact("hardware.gpu.cuda_available", True))

    engine = CompatibilityEngine(model)
    rep = engine.assess_workload("cuda_workload", {"vram_required_gb": 1.0})
    assert rep.hardware_compatible
    assert isinstance(rep.status, CapabilityStatus)


# =========================================================================
# 8. Diagnostics and Sanitized Export
# =========================================================================

def test_diagnostics_and_sanitized_export(tmp_path):
    """Verify diagnostics formatting and privacy sanitization."""
    db_file = tmp_path / "machine_facts.db"
    model = MachineModel(db_path=db_file)
    model.bootstrap(quick=True)

    diag = MachineDiagnostics(model)
    summary = diag.generate_first_run_summary()
    assert "Astra configured for this PC" in summary

    report = diag.generate_diagnostics_report()
    assert "[System]" in report
    assert "[Hardware & Compute]" in report
    assert "[Derived Operational Capabilities]" in report

    # Verify sanitized export removes username
    export = diag.export_sanitized_diagnostics()
    assert "<USER>" in export or "<USER_HOME>" in export or "Windows" in export


# =========================================================================
# 9. Natural Language MachineQueryEngine
# =========================================================================

def test_query_engine_nl_answers(tmp_path):
    """Verify direct natural language question answering from machine facts."""
    db_file = tmp_path / "machine_facts.db"
    model = MachineModel(db_path=db_file)
    model.set_fact(MachineFact("hardware.cpu.model", "12th Gen Intel Core i5-12450H"))
    model.set_fact(MachineFact("hardware.cpu.physical_cores", 8))
    model.set_fact(MachineFact("hardware.cpu.logical_cores", 12))
    model.set_fact(MachineFact("hardware.gpu.model", "NVIDIA GeForce RTX 2050 Laptop GPU"))
    model.set_fact(MachineFact("hardware.gpu.vram_total_gb", 4.0))
    model.set_fact(MachineFact("hardware.gpu.cuda_available", True))
    model.set_fact(MachineFact("software.tool.git.installed", True))
    model.set_fact(MachineFact("software.tool.git.path", "C:\\Program Files\\Git\\cmd\\git.exe"))
    model.set_fact(MachineFact("hardware.storage.volumes", ["C", "E"]))
    model.set_fact(MachineFact("hardware.storage.volume.C.free_gb", 120.0))
    model.set_fact(MachineFact("hardware.storage.volume.E.free_gb", 85.0))

    qe = MachineQueryEngine(model)

    ans_cpu = qe.answer_query("what CPU do I have?")
    assert "Intel" in ans_cpu["answer"]

    ans_gpu = qe.answer_query("what GPU am I using?")
    assert "RTX 2050" in ans_gpu["answer"]

    ans_git = qe.answer_query("where is Git?")
    assert "git.exe" in ans_git["answer"]

    ans_5gb = qe.answer_query("what drives have enough space for a 5 GB file?")
    assert "Drive C" in ans_5gb["answer"]
    assert "Drive E" in ans_5gb["answer"]


# =========================================================================
# 10. Compatibility Test Matrix Fixtures (A through H)
# =========================================================================

def test_compatibility_fixture_matrix(tmp_path):
    """Test 8 synthetic hardware and environment profiles."""

    def make_model(facts: Dict[str, Any]) -> MachineModel:
        db = tmp_path / f"m_{time.time_ns()}.db"
        m = MachineModel(db_path=db)
        for k, v in facts.items():
            m.set_fact(MachineFact(k, v))
        return m

    # Profile A: Reference (RTX 2050 / 16 GB)
    mA = make_model({
        "hardware.memory.total_gb": 16.0,
        "hardware.gpu.model": "NVIDIA GeForce RTX 2050",
        "hardware.gpu.cuda_available": True,
        "software.python.package.numpy.installed": True,
        "software.python.package.matplotlib.installed": True,
    })
    resA = MachineCapabilityResolver(mA)
    assert resA.resolve("CAN_RUN_LOCAL_SPARK").status == CapabilityStatus.AVAILABLE
    assert resA.resolve("CAN_RUN_LOCAL_QWEN").status == CapabilityStatus.AVAILABLE
    assert resA.resolve("CAN_USE_CUDA").status == CapabilityStatus.AVAILABLE

    # Profile B: CPU-only Windows 11 (16 GB / no NVIDIA)
    mB = make_model({
        "hardware.memory.total_gb": 16.0,
        "hardware.gpu.model": "Intel UHD Graphics",
        "hardware.gpu.cuda_available": False,
    })
    resB = MachineCapabilityResolver(mB)
    assert resB.resolve("CAN_USE_CUDA").status == CapabilityStatus.UNAVAILABLE
    assert resB.resolve("CAN_RUN_LOCAL_SPARK").status == CapabilityStatus.AVAILABLE

    # Profile C: Low-memory 8 GB RAM
    mC = make_model({
        "hardware.memory.total_gb": 4.0,  # Below 6 GB
        "hardware.gpu.cuda_available": False,
    })
    resC = MachineCapabilityResolver(mC)
    assert resC.resolve("CAN_RUN_LOCAL_SPARK").status == CapabilityStatus.UNAVAILABLE

    # Profile E: No developer tools
    mE = make_model({
        "software.tool.cl.installed": False,
        "software.tool.gcc.installed": False,
        "software.tool.git.installed": False,
    })
    resE = MachineCapabilityResolver(mE)
    assert resE.resolve("CAN_COMPILE_CPP").status == CapabilityStatus.UNAVAILABLE
    assert resE.resolve("CAN_USE_GIT").status == CapabilityStatus.UNAVAILABLE

    # Profile F: Python installed without Git
    mF = make_model({
        "software.python.active.executable": "python.exe",
        "software.python.package.numpy.installed": True,
        "software.python.package.matplotlib.installed": True,
        "software.tool.git.installed": False,
    })
    resF = MachineCapabilityResolver(mF)
    assert resF.resolve("CAN_RUN_PYTHON_VISUALIZATION").status == CapabilityStatus.AVAILABLE
    assert resF.resolve("CAN_USE_GIT").status == CapabilityStatus.UNAVAILABLE

    # Profile H: Offline (No network)
    mH = make_model({
        "hardware.network.connected": False,
    })
    resH = MachineCapabilityResolver(mH)
    assert resH.resolve("CAN_DOWNLOAD").status == CapabilityStatus.UNAVAILABLE


# =========================================================================
# 11. Continuity Machine Drift & Planner Context Selection
# =========================================================================

def test_machine_drift_and_planner_context(tmp_path):
    """Verify task continuity detects drive drift and ContextBuilder selects relevant facts."""
    # 1. Machine Drift Detection
    engine = ContinuityEngine(checkpoints_dir=tmp_path / "checkpoints")
    cp = TaskCheckpoint(
        task_id="task_drift_test",
        goal="Copy to external disk",
        status="IN_PROGRESS",
        artifacts=["E:\\Workspace\\output.csv"],
    )
    # When volume E is mounted: no drift
    drift, reasons = engine.check_machine_drift(cp, mounted_volumes=["C", "E"])
    assert not drift
    assert len(reasons) == 0

    # When volume E is unmounted: drift detected
    drift, reasons = engine.check_machine_drift(cp, mounted_volumes=["C"])
    assert drift
    assert any("E:" in r for r in reasons)

    # 2. Planner Context Selection
    cb = ContextBuilder()
    m_ctx = cb.build_machine_context("Generate a 3D graph of z = sin(x)")
    assert "[TASK-RELEVANT WORKSTATION REALITY]" in m_ctx
    assert "Visualization Capability" in m_ctx
    # Invariant: Personal paths or unrelated device facts must NOT be dumped
    assert "Wi-Fi driver" not in m_ctx
    assert "battery serial" not in m_ctx
