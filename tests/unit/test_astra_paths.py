"""Unit tests for authoritative AstraPaths directory layout and invariants."""

import os
import sys
from pathlib import Path
import pytest

from astrarun.core.paths import AstraPaths, get_app_data_dir, get_install_root, resolve_model_path


def test_astra_paths_hierarchy(monkeypatch, tmp_path):
    fake_localappdata = tmp_path / "AppData" / "Local"
    fake_temp = tmp_path / "Temp"
    fake_localappdata.mkdir(parents=True)
    fake_temp.mkdir(parents=True)

    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))
    monkeypatch.setenv("TEMP", str(fake_temp))
    monkeypatch.delenv("ASTRARUN_DATA_DIR", raising=False)
    monkeypatch.delenv("ASTRARUN_TEMP_DIR", raising=False)

    user_data = AstraPaths.user_data_dir()
    assert user_data == fake_localappdata / "AstraRun"

    temp_dir = AstraPaths.temp_dir()
    assert temp_dir == fake_temp / "AstraRun"

    assert AstraPaths.config_dir() == user_data / "config"
    assert AstraPaths.data_dir() == user_data / "data"
    assert AstraPaths.logs_dir() == user_data / "logs"
    assert AstraPaths.models_dir() == user_data / "models"


def test_cwd_independence(monkeypatch, tmp_path):
    """Verify that changing CWD does not alter AstraPaths destinations."""
    cwd_a = tmp_path / "dir_a"
    cwd_b = tmp_path / "dir_b"
    cwd_a.mkdir()
    cwd_b.mkdir()

    monkeypatch.chdir(cwd_a)
    path_a = AstraPaths.machine_db_path()

    monkeypatch.chdir(cwd_b)
    path_b = AstraPaths.machine_db_path()

    assert path_a == path_b
    assert not str(path_a).startswith(str(cwd_a))
    assert not str(path_b).startswith(str(cwd_b))


def test_model_resolution_preserves_external(monkeypatch, tmp_path):
    """External models must resolve without moving or deleting."""
    external_models = tmp_path / "external_models"
    external_models.mkdir()
    dummy_model = external_models / "test_model.gguf"
    dummy_model.write_text("model_bytes")

    # In development mode with fallback provided
    resolved = resolve_model_path("test_model.gguf", dev_fallback=dummy_model)
    assert resolved == dummy_model
    assert dummy_model.exists()
    assert dummy_model.read_text() == "model_bytes"


def test_release_mode_model_resolution_clean_user(monkeypatch, tmp_path):
    """Clean-user release mode must resolve strictly to managed locations without E: drive fallbacks."""
    clean_localappdata = tmp_path / "CleanUser" / "AppData" / "Local"
    clean_localappdata.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(clean_localappdata))

    monkeypatch.delenv("ASTRA_DEV", raising=False)
    monkeypatch.setenv("ASTRARUN_ENV", "release")
    monkeypatch.delenv("ASTRARUN_DATA_DIR", raising=False)

    resolved = resolve_model_path("qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
    expected = clean_localappdata / "AstraRun" / "models" / "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"

    assert resolved == expected
    assert "E:\\" not in str(resolved)
    assert "E:/" not in str(resolved)

