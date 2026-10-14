"""Unit tests for ResourceType.SANDBOX_DIR ledger tracking and cleanup."""

import shutil
import tempfile
from pathlib import Path

import pytest

from astrarun.core.telemetry import CausalTelemetry, CausalEventType
from astrarun.tasks.resource_ledger import (
    AstraResourceLedger,
    CleanupPolicy,
    OwnedResource,
    ResourceLifecycleState,
    ResourceType,
)


@pytest.fixture
def temp_ledger(tmp_path: Path):
    db_file = tmp_path / "test_ledger.db"
    ledger = AstraResourceLedger(db_path=db_file)
    return ledger


def test_sandbox_dir_registration_and_auto_close(temp_ledger: AstraResourceLedger, tmp_path: Path):
    sandbox_dir = tmp_path / "sandbox_run_1"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sandbox_dir / "test_file.txt").write_text("sample content")

    res = OwnedResource(
        task_id="task_sb_1",
        resource_type=ResourceType.SANDBOX_DIR,
        launching_capability="execute_candidate",
        document_path=str(sandbox_dir),
        astra_created=True,
        cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
    )
    temp_ledger.register_resource(res)

    assert sandbox_dir.exists()
    assert (sandbox_dir / "test_file.txt").exists()

    closed = temp_ledger.close_owned_resource(res)
    assert closed is True
    assert not sandbox_dir.exists()

    persisted = temp_ledger.get_resource(res.resource_id)
    assert persisted is not None
    assert persisted.lifecycle_state == ResourceLifecycleState.CLOSED


def test_sandbox_dir_preserve_on_failure(temp_ledger: AstraResourceLedger, tmp_path: Path):
    sandbox_dir = tmp_path / "sandbox_run_preserve"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sandbox_dir / "error.log").write_text("stack trace")

    res = OwnedResource(
        task_id="task_sb_preserve",
        resource_type=ResourceType.SANDBOX_DIR,
        launching_capability="execute_candidate",
        document_path=str(sandbox_dir),
        astra_created=True,
        cleanup_policy=CleanupPolicy.PRESERVE_ON_FAILURE,
    )
    temp_ledger.register_resource(res)

    closed = temp_ledger.close_owned_resource(res)
    assert closed is True
    # Directory should still exist because it was preserved
    assert sandbox_dir.exists()
    assert (sandbox_dir / "error.log").exists()

    persisted = temp_ledger.get_resource(res.resource_id)
    assert persisted is not None
    assert persisted.lifecycle_state == ResourceLifecycleState.SAVED


def test_cleanup_task_resources_cleans_sandbox(temp_ledger: AstraResourceLedger, tmp_path: Path):
    sandbox_dir = tmp_path / "sandbox_run_cleanup"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sandbox_dir / "artifact.dat").write_bytes(b"\x00\x01\x02")

    res = OwnedResource(
        task_id="task_sb_cleanup",
        resource_type=ResourceType.SANDBOX_DIR,
        launching_capability="execute_candidate",
        document_path=str(sandbox_dir),
        astra_created=True,
        cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
    )
    temp_ledger.register_resource(res)

    report = temp_ledger.cleanup_task_resources("task_sb_cleanup", task_status="COMPLETED")
    assert not sandbox_dir.exists()
    assert report["cleaned_count"] >= 1
    assert report["process_cleaned_up"] is True
