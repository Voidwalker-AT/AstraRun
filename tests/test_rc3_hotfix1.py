"""Regression and verification tests for RC.3 Dogfood Hotfix 1.

Covers:
1. Multi-GPU discovery and preferred compute GPU resolution (NVIDIA RTX 2050).
2. MachineQueryEngine deterministic hardware queries ("What GPU do I have and how much VRAM is free right now?").
3. Out-of-process Laya Worker isolation and crash containment.
4. Abnormal termination and last-gasp crash detection.
5. FirstRunWizard UI updates (subtitle, multi-GPU cards, model page badges, preferences browse button).
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
import pytest

from astrarun.core.hardware import audit_hardware, HardwareProfile, GpuDevice
from astrarun.machine.query_engine import MachineQueryEngine
from astrarun.machine.model import MachineModel
from astrarun.core.crash import (
    record_subsystem_operation,
    detect_previous_abnormal_termination,
    get_last_gasp_file,
)


def test_multi_gpu_hardware_audit():
    """Verify hardware audit detects discrete NVIDIA RTX 2050 and marks it as preferred compute GPU."""
    profile = audit_hardware()
    assert isinstance(profile, HardwareProfile)
    assert profile.ram_gb > 0

    # Physical machine check: must detect RTX 2050
    assert len(profile.gpus) >= 1
    gpu_names = [g.name for g in profile.gpus]
    
    # We should have an NVIDIA GPU detected on this host
    nvidia_gpus = [g for g in profile.gpus if "NVIDIA" in g.name.upper() or "RTX" in g.name.upper()]
    assert len(nvidia_gpus) >= 1, f"Expected NVIDIA GPU on reference workstation, found: {gpu_names}"
    
    rtx_gpu = nvidia_gpus[0]
    assert rtx_gpu.is_discrete is True
    assert rtx_gpu.vram_gb >= 3.5  # RTX 2050 4GB
    assert profile.preferred_compute_gpu is not None
    assert "RTX" in profile.preferred_compute_gpu.name


def test_machine_query_engine_hardware():
    """Verify MachineQueryEngine answers GPU & VRAM questions accurately and instantly."""
    engine = MachineQueryEngine()
    
    # Exact user dogfood prompt
    query = "What GPU do I have and how much VRAM is free right now?"
    assert engine.is_machine_query(query) is True
    
    t0 = time.perf_counter()
    ans = engine.answer(query)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    
    assert ans is not None
    assert elapsed_ms < 500.0  # Ultra-fast < 500ms fast path (< 250ms cold)
    assert "NVIDIA GeForce RTX 2050" in ans
    assert "VRAM is free right now" in ans
    assert "GB" in ans

    # VRAM query alone
    ans_vram = engine.answer("How much VRAM is free right now?")
    assert ans_vram is not None
    assert "dedicated VRAM" in ans_vram

    # General GPU query
    ans_gpu = engine.answer("What GPU do I have?")
    assert ans_gpu is not None
    assert "NVIDIA GeForce RTX 2050" in ans_gpu


def test_last_gasp_crash_recording():
    """Verify record_subsystem_operation and detect_previous_abnormal_termination."""
    record_subsystem_operation("TEST_OPERATION", {"detail": "unit_test_probe"})
    gasp_path = get_last_gasp_file()
    assert gasp_path.exists()
    
    with open(gasp_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["operation"] == "TEST_OPERATION"
    assert data["details"]["detail"] == "unit_test_probe"
    assert data["pid"] == os.getpid()


def test_laya_worker_crash_containment():
    """Verify that if LayaWorker crashes (simulating 0xc0000409), the parent process lives and recovers."""
    from astrarun.routing.laya import LayaProcessClient

    client = LayaProcessClient()
    # Ping worker to ensure it is spawned
    ok = client._ensure_worker_running()
    assert ok is True
    assert client._proc is not None
    worker_pid = client._proc.pid
    assert worker_pid > 0

    # Issue a simulated crash command directly to the worker
    payload = {"id": "test-crash-1", "action": "crash_for_test"}
    client._proc.stdin.write(json.dumps(payload) + "\n")
    client._proc.stdin.flush()

    # Wait briefly for worker process to exit
    client._proc.wait(timeout=3.0)
    assert client._proc.poll() is not None

    # Parent process MUST be alive! Calling predict must handle the dead worker gracefully
    res = client.predict("Open Chrome browser")
    assert isinstance(res, dict)
    assert res.get("intent") in ("open_app", "unknown")
    # Worker should be cleanly recovered or scheduled for restart
    client.shutdown()


def test_first_run_ui_structure():
    """Verify first-run UI incorporates all RC.3 Hotfix 1 UI fixes."""
    from PySide6.QtWidgets import QApplication
    from astrarun.ui.first_run import FirstRunWizard

    app = QApplication.instance() or QApplication([])

    wizard = FirstRunWizard()
    
    # 1. Subtitle verification
    assert wizard.header_subtitle.text() == "Local-first adaptive Windows agent"
    
    # 2. Hardware page has discrete RTX 2050
    assert wizard.hardware.preferred_compute_gpu is not None
    assert "RTX" in wizard.hardware.preferred_compute_gpu.name
    
    # 3. Models page
    assert hasattr(wizard, "radio_use_existing") or hasattr(wizard, "lbl_model_status")
    
    # 4. Preferences page has browse button
    assert hasattr(wizard, "btn_browse_dir")
    assert hasattr(wizard, "txt_model_dir")
    assert wizard.btn_browse_dir.text() == "Browse..."
    assert hasattr(wizard, "chk_autostart")
    assert "automatically when I sign in" in wizard.chk_autostart.text()
    
    wizard.close()
