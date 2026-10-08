"""Unit tests for Phase F0-15: Astra-Owned Application / Window Lifecycle Cleanup."""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astrarun.tasks.models import TaskStatus
from astrarun.tasks.resource_ledger import (
    AstraResourceLedger,
    CleanupPolicy,
    ContentClassification,
    OwnedResource,
    PreLaunchSnapshot,
    ResourceLifecycleState,
    ResourceType,
)


@pytest.fixture
def temp_ledger(tmp_path):
    db_file = tmp_path / "test_resource_ledger.db"
    return AstraResourceLedger(db_path=db_file)


def test_resource_ledger_registration_and_retrieval(temp_ledger):
    res = OwnedResource(
        task_id="task_001",
        resource_type=ResourceType.APPLICATION,
        launching_capability="open_application",
        pid=1234,
        hwnd=5678,
        process_creation_time=100000.0,
        astra_created=True,
        existed_before=False,
        cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
    )
    temp_ledger.register_resource(res)

    fetched = temp_ledger.get_resource(res.resource_id)
    assert fetched is not None
    assert fetched.task_id == "task_001"
    assert fetched.pid == 1234
    assert fetched.hwnd == 5678
    assert fetched.astra_created is True
    assert fetched.existed_before is False
    assert fetched.cleanup_policy == CleanupPolicy.AUTO_CLOSE_ON_COMPLETION


def test_critical_ownership_rule_never_close_non_astra_resource(temp_ledger):
    """Astra must NEVER close pre-existing resources that Astra did not create."""
    res = OwnedResource(
        task_id="task_002",
        resource_type=ResourceType.APPLICATION,
        launching_capability="open_application",
        pid=9999,
        hwnd=8888,
        astra_created=False,  # Existed before Astra ran
        existed_before=True,
    )
    temp_ledger.register_resource(res)

    # Attempt closure
    closed = temp_ledger.close_owned_resource(res)
    assert closed is False
    assert res.lifecycle_state != ResourceLifecycleState.CLOSED


def test_save_before_close_requires_verified_file(temp_ledger, tmp_path):
    """SAVE_BEFORE_CLOSE must verify the artifact file exists on disk before closing."""
    test_artifact = tmp_path / "report.txt"
    res = OwnedResource(
        task_id="task_003",
        resource_type=ResourceType.DOCUMENT,
        launching_capability="open_application",
        pid=4321,
        hwnd=8765,
        document_path=str(test_artifact),
        astra_created=True,
        cleanup_policy=CleanupPolicy.SAVE_BEFORE_CLOSE,
        content_classification=ContentClassification.TASK_ARTIFACT,
    )
    temp_ledger.register_resource(res)

    # File does NOT exist yet -> closure must be rejected
    assert not test_artifact.exists()
    ok = temp_ledger.close_owned_resource(res)
    assert ok is False

    # Now create the artifact
    test_artifact.write_text("Verified content", encoding="utf-8")
    with patch("ctypes.windll.user32.PostMessageW", return_value=1), \
         patch("ctypes.windll.user32.IsWindow", return_value=False), \
         patch("psutil.pid_exists", return_value=False):
        ok2 = temp_ledger.close_owned_resource(res)
        assert ok2 is True
        fetched = temp_ledger.get_resource(res.resource_id)
        assert fetched.lifecycle_state == ResourceLifecycleState.CLOSED


def test_user_takeover_detaches_from_auto_cleanup(temp_ledger):
    """User intervention immediately detaches owned resources from automatic cleanup."""
    res = OwnedResource(
        task_id="task_004",
        resource_type=ResourceType.APPLICATION,
        launching_capability="open_application",
        pid=5555,
        hwnd=6666,
        astra_created=True,
        cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
    )
    temp_ledger.register_resource(res)

    # Mark user takeover
    count = temp_ledger.mark_user_takeover_for_task("task_004")
    assert count == 1

    fetched = temp_ledger.get_resource(res.resource_id)
    assert fetched.user_interacted is True
    assert fetched.lifecycle_state == ResourceLifecycleState.USER_TAKEOVER_DETACHED

    # Attempt to close via task cleanup
    summary = temp_ledger.cleanup_task_resources("task_004", TaskStatus.COMPLETED)
    assert summary["detached_count"] == 1
    assert summary["cleaned_count"] == 0


def test_pid_reuse_hazard_aborts_termination(temp_ledger):
    """Strictly protect against Windows PID reuse: if create_time differs, do not terminate."""
    res = OwnedResource(
        task_id="task_005",
        resource_type=ResourceType.APPLICATION,
        launching_capability="open_application",
        pid=7777,
        process_creation_time=1000.0,  # Recorded creation time
        astra_created=True,
        cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
    )
    temp_ledger.register_resource(res)

    mock_proc = MagicMock()
    mock_proc.create_time.return_value = 2500.0  # Different process has reused PID 7777!

    with patch("psutil.pid_exists", return_value=True), \
         patch("psutil.Process", return_value=mock_proc):
        ok = temp_ledger.close_owned_resource(res)
        assert ok is False
        mock_proc.terminate.assert_not_called()
        mock_proc.kill.assert_not_called()

        fetched = temp_ledger.get_resource(res.resource_id)
        assert fetched.lifecycle_state == ResourceLifecycleState.STALE_REUSED


def test_preserve_on_failure_policy(temp_ledger):
    """Tasks failing must preserve resources when PRESERVE_ON_FAILURE policy is configured."""
    res = OwnedResource(
        task_id="task_006",
        resource_type=ResourceType.APPLICATION,
        launching_capability="open_application",
        pid=1111,
        astra_created=True,
        cleanup_policy=CleanupPolicy.PRESERVE_ON_FAILURE,
    )
    temp_ledger.register_resource(res)

    summary = temp_ledger.cleanup_task_resources("task_006", TaskStatus.FAILED)
    assert summary["preserved_count"] == 1
    assert summary["cleaned_count"] == 0

    fetched = temp_ledger.get_resource(res.resource_id)
    assert fetched.lifecycle_state == ResourceLifecycleState.ACTIVE


def test_orphan_recovery_across_restart(temp_ledger):
    """Crash recovery cleans disposable test debris while respecting PID creation times."""
    # 1. Vanished process
    res_vanished = OwnedResource(
        task_id="prior_task_1",
        pid=8001,
        process_creation_time=500.0,
        astra_created=True,
        content_classification=ContentClassification.TEMPORARY_TEST_CONTENT,
    )
    # 2. Lingering test process with matching create_time
    res_lingering = OwnedResource(
        task_id="prior_task_2",
        pid=8002,
        process_creation_time=600.0,
        astra_created=True,
        content_classification=ContentClassification.TEMPORARY_TEST_CONTENT,
    )
    # 3. PID reused by new system process
    res_reused = OwnedResource(
        task_id="prior_task_3",
        pid=8003,
        process_creation_time=700.0,
        astra_created=True,
        content_classification=ContentClassification.TEMPORARY_TEST_CONTENT,
    )

    temp_ledger.register_resource(res_vanished)
    temp_ledger.register_resource(res_lingering)
    temp_ledger.register_resource(res_reused)

    def mock_pid_exists(pid):
        return pid in (8002, 8003)

    def mock_process_factory(pid):
        m = MagicMock()
        if pid == 8002:
            m.create_time.return_value = 600.0  # Matches
            m.name.return_value = "notepad.exe"
        elif pid == 8003:
            m.create_time.return_value = 9999.0  # Reused!
        return m

    with patch("psutil.pid_exists", side_effect=mock_pid_exists), \
         patch("psutil.Process", side_effect=mock_process_factory):
        results = temp_ledger.recover_orphaned_resources()
        actions = {r["resource_id"]: r["action"] for r in results}

        assert actions[res_vanished.resource_id] == "CLOSED_NOT_FOUND"
        assert actions[res_lingering.resource_id] == "ORPHANED_CLEANED"
        assert actions[res_reused.resource_id] == "STALE_REUSED"
