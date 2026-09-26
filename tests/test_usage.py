"""Unit tests for local usage persistence and ranking weighting."""

from pathlib import Path
from astrarun.usage.store import UsageStore


def test_usage_store_lifecycle(tmp_path: Path):
    usage_file = tmp_path / "usage.json"
    store = UsageStore(data_file=usage_file)

    # Initial usage should be 0
    count, is_recent = store.get_usage("app:vscode")
    assert count == 0
    assert not is_recent

    # Record launches
    store.record_launch("app:vscode")
    store.record_launch("app:vscode")
    store.record_launch("app:notepad")

    # Reload from disk
    store_reloaded = UsageStore(data_file=usage_file)
    c_vsc, r_vsc = store_reloaded.get_usage("app:vscode")
    c_np, r_np = store_reloaded.get_usage("app:notepad")

    assert c_vsc == 2
    assert r_vsc is True
    assert c_np == 1
    assert r_np is True


def test_corrupted_usage_file(tmp_path: Path):
    usage_file = tmp_path / "corrupted_usage.json"
    usage_file.write_text("{ broken json content !!")

    store = UsageStore(data_file=usage_file)
    count, is_recent = store.get_usage("app:any")
    assert count == 0
    assert not is_recent
