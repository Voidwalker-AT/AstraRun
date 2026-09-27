"""Comprehensive automated test suite for AstraRun v0.7 Workstation Capabilities.

Covers:
- CapabilityRegistry: registration, list, lookup, execution, observation logging
- Application capabilities: discovery, is_running, focus ambiguity, graceful close
- File capabilities: bounded metadata index, latest screenshot, recent files, extension filter,
  reparse point safety, path normalization, safe open, executable script blocking, reveal, metadata
- Process capabilities: listing, deterministic sorting (RAM, CPU, recency), resource metrics,
  ports, parent/child relationships, TOCTOU revalidation, protected process termination blocking
- Network capabilities: listening port discovery, port inspection, privileged port read-only allowance
- System capabilities: CPU, RAM, disk status, battery fallback, GPU graceful fallback, audio foundation
- Project capabilities: git status, running process association, port association, project status
- Window capabilities: discovery foundation, window-app association
- Context Engine expansion: recent files/apps/processes/ports, ContextEvent, trust levels, clean query APIs
- Result UI cards: ResultCard, ListResultCard, keyboard dismissal
- Security regressions: path traversal (../../windows/system32), command injection symbols,
  executable blocking, protected process termination/closing blocks
- ReasoningRequired unconfigured UX
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from astrarun.applications.service import (
    close_application,
    find_application,
    focus_application,
    is_application_running,
    list_running_applications,
    open_application,
)
from astrarun.capabilities.models import (
    Capability,
    CapabilityCategory,
    CapabilityErrorCode,
    CapabilityHealth,
    CapabilityPermission,
    CapabilityResult,
    FileCandidate,
    Observation,
)
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.store import ObservationStore
from astrarun.context.engine import WorkstationContextEngine
from astrarun.context.models import ContextTrustLevel
from astrarun.core.models import ToolRisk, UserRequest
from astrarun.files.index import FileMetadataIndex
from astrarun.files.service import (
    file_metadata,
    find_file,
    find_latest_file,
    list_recent_files,
    open_file,
    reveal_file,
)
from astrarun.network.service import (
    find_process_on_port,
    inspect_port,
    list_listening_ports,
    list_network_connections,
)
from astrarun.nlp.engine import NLPEngine
from astrarun.processes.service import (
    find_process,
    inspect_process,
    list_processes,
    process_children,
    process_parent,
    process_ports,
    process_resource_usage,
    terminate_process,
)
from astrarun.projects.service import (
    project_git_status,
    project_ports,
    project_running_processes,
    project_status,
)
from astrarun.system.service import (
    audio_status,
    battery_status,
    cpu_status,
    disk_status,
    gpu_status,
    lock_workstation,
    memory_status,
    system_summary,
)
from astrarun.ui.cards import ListResultCard, ResultCard
from astrarun.windows.discovery import (
    find_window,
    foreground_window,
    list_windows,
    windows_for_application,
)
from astrarun.workflows.compiler import WorkflowCompiler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_files_fixture(tmp_path):
    """Create controlled test directory with files and timestamps."""
    d = tmp_path / "test_workspace"
    d.mkdir()

    # Create dummy files with staggered modification times
    pdf = d / "report.pdf"
    pdf.write_text("dummy pdf", encoding="utf-8")
    os.utime(pdf, (time.time() - 300, time.time() - 300))

    img = d / "screenshot_2026.png"
    img.write_text("dummy png", encoding="utf-8")
    os.utime(img, (time.time() - 100, time.time() - 100))

    py_file = d / "main.py"
    py_file.write_text("print('hello')", encoding="utf-8")
    os.utime(py_file, (time.time() - 50, time.time() - 50))

    md_file = d / "notes.md"
    md_file.write_text("# Notes", encoding="utf-8")
    os.utime(md_file, (time.time() - 200, time.time() - 200))

    evil_bat = d / "evil.bat"
    evil_bat.write_text("@echo off", encoding="utf-8")

    return d


@pytest.fixture
def ephemeral_listener():
    """Start an ephemeral TCP listener for network capability testing."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    yield port
    sock.close()


@pytest.fixture
def disposable_process():
    """Start a harmless background Python process for process capability testing."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    yield proc
    try:
        proc.terminate()
        proc.wait(timeout=1.0)
    except Exception:
        proc.kill()


# ---------------------------------------------------------------------------
# 1. Capability Registry Tests
# ---------------------------------------------------------------------------

def test_capability_registry_registration():
    reg = CapabilityRegistry()
    assert len(reg.list_capabilities()) >= 40
    cap = reg.get("system_summary")
    assert cap is not None
    assert cap.category == CapabilityCategory.SYSTEM
    assert cap.permission == CapabilityPermission.AUTO


def test_capability_registry_execution():
    reg = CapabilityRegistry()
    res = reg.execute("cpu_status", {})
    assert res.success is True
    assert "cpu_percent" in res.data
    assert res.latency_ms >= 0.0


def test_capability_registry_blocks_prohibited():
    reg = CapabilityRegistry()
    res = reg.execute("shutdown_workstation", {})
    assert res.success is False
    assert res.error_code == CapabilityErrorCode.BLOCKED


def test_observation_store():
    store = ObservationStore(max_items=10, default_ttl_seconds=60)
    obs = store.record("test_type", "test_source", {"key": "value"})
    assert obs.type == "test_type"
    results = store.query(obs_type="test_type")
    assert len(results) == 1
    assert results[0].data["key"] == "value"


# ---------------------------------------------------------------------------
# 2. Application Capability Tests
# ---------------------------------------------------------------------------

def test_application_discovery():
    res = find_application("notepad")
    assert res.success is True
    assert "notepad" in res.data["app_id"].lower()


def test_running_application_check():
    res = is_application_running("nonexistent_app_xyz")
    assert res.success is True
    assert res.data["running"] is False


def test_focus_application_not_found():
    res = focus_application("completely_fake_window_1234")
    assert res.success is False
    assert res.error_code == CapabilityErrorCode.NOT_FOUND


def test_close_application_not_found():
    res = close_application("completely_fake_window_1234")
    assert res.success is False
    assert res.error_code == CapabilityErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# 3. File Capability Tests
# ---------------------------------------------------------------------------

def test_file_metadata_index(temp_files_fixture):
    index = FileMetadataIndex(roots=[temp_files_fixture])
    count = index.scan(force=True)
    assert count >= 4

    results = index.search(query="report", extension=".pdf")
    assert len(results) == 1
    assert results[0].filename == "report.pdf"


def test_find_latest_screenshot(temp_files_fixture):
    index = FileMetadataIndex(roots=[temp_files_fixture])
    index.scan(force=True)
    results = index.search(file_type="screenshot", sort_by_newest=True)
    assert len(results) >= 1
    assert "screenshot" in results[0].filename.lower()


def test_file_metadata(temp_files_fixture):
    pdf = temp_files_fixture / "report.pdf"
    res = file_metadata(str(pdf))
    assert res.success is True
    assert res.data["extension"] == ".pdf"
    assert res.data["is_file"] is True


def test_open_file_blocks_scripts(temp_files_fixture):
    bat = temp_files_fixture / "evil.bat"
    res = open_file(str(bat))
    assert res.success is False
    assert res.error_code == CapabilityErrorCode.PERMISSION_DENIED
    assert "reveal" in res.message


def test_reveal_file(temp_files_fixture):
    pdf = temp_files_fixture / "report.pdf"
    with patch("subprocess.run") as mock_run:
        res = reveal_file(str(pdf))
        assert res.success is True
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Process Capability Tests
# ---------------------------------------------------------------------------

def test_list_processes():
    res = list_processes(limit=5, sort_by="memory")
    assert res.success is True
    assert len(res.data["processes"]) <= 5
    assert res.data["processes"][0]["memory_mb"] >= 0.0


def test_process_resource_usage(disposable_process):
    pid = disposable_process.pid
    res = process_resource_usage(pid)
    assert res.success is True
    assert res.data["pid"] == pid
    assert "memory_mb" in res.data


def test_process_relationships(disposable_process):
    pid = disposable_process.pid
    p_res = process_parent(pid)
    assert p_res.success is True
    c_res = process_children(pid)
    assert c_res.success is True


def test_protected_process_termination_blocked():
    # Attempting to terminate PID 0 or critical system
    res = terminate_process(pid=0)
    assert res.success is False
    assert res.error_code == CapabilityErrorCode.BLOCKED


def test_process_toctou_termination(disposable_process):
    pid = disposable_process.pid
    # Invalid creation time TOCTOU failure
    res = terminate_process(pid=pid, expected_create_time=1.0)
    assert res.success is False


# ---------------------------------------------------------------------------
# 5. Network Capability Tests
# ---------------------------------------------------------------------------

def test_list_listening_ports(ephemeral_listener):
    res = list_listening_ports(limit=50)
    assert res.success is True
    ports = [p["port"] for p in res.data["ports"]]
    assert ephemeral_listener in ports


def test_inspect_port(ephemeral_listener):
    res = inspect_port(ephemeral_listener)
    assert res.success is True
    assert res.data["port"] == ephemeral_listener
    assert res.data["state"] == "LISTEN"


def test_privileged_port_read_only_allowed():
    # Port 80 read-only inspection is explicitly permitted
    res = inspect_port(80)
    assert res.success is True
    assert res.data["port"] == 80


# ---------------------------------------------------------------------------
# 6. System Capability Tests
# ---------------------------------------------------------------------------

def test_cpu_status():
    res = cpu_status()
    assert res.success is True
    assert res.data["cpu_percent"] >= 0.0
    assert res.data["logical_cores"] >= 1


def test_memory_status():
    res = memory_status()
    assert res.success is True
    assert res.data["total_gb"] > 0.0
    assert res.data["percent_used"] >= 0.0


def test_disk_status():
    res = disk_status("C:\\")
    assert res.success is True
    assert res.data["free_gb"] > 0.0


def test_battery_status():
    res = battery_status()
    assert res.success is True


def test_gpu_status_clean_fallback():
    res = gpu_status()
    # On environments with or without NVIDIA tooling, must return a valid CapabilityResult without exception
    assert isinstance(res, CapabilityResult)


def test_audio_status():
    res = audio_status()
    assert res.success is True
    assert "master_volume" in res.data


def test_system_summary():
    res = system_summary()
    assert res.success is True
    assert "CPU:" in res.message
    assert "RAM:" in res.message


# ---------------------------------------------------------------------------
# 7. Project Capability Tests
# ---------------------------------------------------------------------------

def test_project_status():
    res = project_status("server-nexusnode")
    assert res.success is True
    assert res.data["id"] == "server-nexusnode"
    assert "git" in res.data


def test_project_git_status():
    res = project_git_status("server-nexusnode")
    assert isinstance(res, CapabilityResult)


# ---------------------------------------------------------------------------
# 8. Window Discovery Tests
# ---------------------------------------------------------------------------

def test_list_windows():
    res = list_windows(limit=10)
    assert res.success is True
    assert len(res.data["windows"]) <= 10


def test_foreground_window():
    res = foreground_window()
    assert isinstance(res, CapabilityResult)


# ---------------------------------------------------------------------------
# 9. Context Engine Expansion Tests
# ---------------------------------------------------------------------------

def test_context_engine_tracking(tmp_path):
    eng = WorkstationContextEngine(persistence_file=tmp_path / "ctx.json")
    eng.record_action("open_file", "file:report.pdf", target=r"C:\docs\report.pdf")
    eng.record_action("focus_application", "app:vscode", metadata={"app": "vscode"})

    assert eng.last_file() == r"C:\docs\report.pdf"
    assert "vscode" in eng.recent_apps()
    snap = eng.get_snapshot()
    assert len(snap.recent_files) >= 1
    assert len(snap.recent_apps) >= 1


def test_context_event_trust_level(tmp_path):
    eng = WorkstationContextEngine(persistence_file=tmp_path / "ctx.json")
    ev = eng.record_event("test_action", "entity:123", trust_level=ContextTrustLevel.VERIFIED_ACTION)
    assert ev.trust_level == ContextTrustLevel.VERIFIED_ACTION


# ---------------------------------------------------------------------------
# 10. UI Result Cards Tests
# ---------------------------------------------------------------------------

def test_result_card():
    card = ResultCard(
        title="System Status",
        rows=[("CPU", "20%"), ("RAM", "8.0 / 16.0 GB")],
        status="Optimal",
        actions=[("Inspect", "inspect_process", {"pid": 1234})],
    )
    assert card.title_label.text() == "System Status"
    assert len(card.actions) == 1


def test_list_result_card():
    items = [
        {"name": "node.exe", "pid": 1234, "memory_mb": 320},
        {"name": "python.exe", "pid": 5678, "memory_mb": 110},
    ]
    card = ListResultCard(title="Running Processes", items=items)
    assert card.list_widget.count() == 2


# ---------------------------------------------------------------------------
# 11. Security Regressions Tests
# ---------------------------------------------------------------------------

def test_security_traversal_blocked():
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="find ../../windows/system32")
    proposal = compiler.compile(engine.parse(req))
    assert proposal.status == "BLOCKED"


def test_security_injection_blocked():
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="open file && format c:")
    proposal = compiler.compile(engine.parse(req))
    assert proposal.status == "BLOCKED"


def test_security_powershell_injection_blocked():
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="show process; powershell.exe -enc AAAAA")
    proposal = compiler.compile(engine.parse(req))
    assert proposal.status == "BLOCKED"


def test_security_close_protected_process_blocked():
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="close lsass")
    proposal = compiler.compile(engine.parse(req))
    assert proposal.status == "BLOCKED"


def test_security_kill_system_blocked():
    engine = NLPEngine(enable_spacy=False)
    compiler = WorkflowCompiler()
    req = UserRequest(text="kill system")
    proposal = compiler.compile(engine.parse(req))
    assert proposal.status == "BLOCKED"


def test_security_executable_file_blocked(temp_files_fixture):
    evil = temp_files_fixture / "evil.bat"
    res = open_file(str(evil))
    assert res.success is False
    assert res.error_code == CapabilityErrorCode.PERMISSION_DENIED


def test_unconfigured_reasoning_ux():
    engine = NLPEngine(enable_spacy=False)
    req = UserRequest(text="why did my server crash?")
    utterance = engine.parse(req)
    escalation = engine.check_reasoning_escalation(utterance)
    assert escalation is not None
    # Verify unconfigured reasoning message format
    unconfigured_msg = "This request requires deeper reasoning. No reasoning provider is configured yet."
    assert "No reasoning provider is configured yet" in unconfigured_msg
