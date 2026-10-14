"""
AU-1.1A Downstream Parity Tests.

Verifies that operational requests dispatched through the ingress seam preserve
exact existing execution paths and behaviors across all downstream branches.
"""

import pytest
from astrarun.app import AstraApplication
from astrarun.ingress.models import RequestEnvelope, RequestOrigin


@pytest.fixture
def astra_app():
    return AstraApplication()


def test_computational_math_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("calculate 2 + 2", origin=RequestOrigin.CLI)
    res = astra_app.handle_request(env)
    assert res.success is True
    assert res.type == "computational"
    assert "2 + 2 = 4" in res.message


def test_computational_count_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("count to 5", origin=RequestOrigin.CLI)
    res = astra_app.handle_request(env)
    assert res.success is True
    assert res.type == "computational"
    assert "Counted to 5: 1, 2, 3, 4, 5" in res.message


def test_fast_path_open_app_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("open notepad", origin=RequestOrigin.CLI, dry_run=True)
    res = astra_app.handle_request(env)
    assert res.success is True
    assert res.type == "fast_path"
    assert "notepad" in res.message.lower()


def test_fast_path_launch_app_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("launch calculator", origin=RequestOrigin.CLI, dry_run=True)
    res = astra_app.handle_request(env)
    assert res.success is True
    assert res.type == "fast_path"
    assert "calc" in res.message.lower()


def test_agent_goal_battery_report_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("battery report", origin=RequestOrigin.CLI, dry_run=True)
    res = astra_app.handle_request(env)
    assert res.success is True
    assert res.type == "capability_result"
    assert res.task is not None


def test_read_only_observation_is_app_running_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("is notepad running", origin=RequestOrigin.CLI, dry_run=True)
    res = astra_app.handle_request(env)
    assert res.success is True
    assert res.type == "observation"
    assert "running" in res.message.lower()


def test_ui_interaction_inspect_ui_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("inspect ui", origin=RequestOrigin.CLI, dry_run=True)
    res = astra_app.handle_request(env)
    assert res.type == "capability_result"


def test_system_status_cpu_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("cpu status", origin=RequestOrigin.CLI, dry_run=True)
    res = astra_app.handle_request(env)
    assert res.success is True
    assert res.type == "capability_result"
    assert "CPU" in res.message


def test_system_status_memory_parity(astra_app: AstraApplication):
    env = RequestEnvelope.create("memory status", origin=RequestOrigin.CLI, dry_run=True)
    res = astra_app.handle_request(env)
    assert res.success is True
    assert res.type == "capability_result"
    assert "RAM" in res.message or "Memory" in res.message or "GB" in res.message
