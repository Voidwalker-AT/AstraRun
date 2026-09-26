"""Unit tests for configuration loading and resilience."""

import json
from pathlib import Path
from astrarun.config.loader import load_config, DEFAULT_SETTINGS


def test_load_default_config(tmp_path: Path):
    # Non-existent directory returns safe defaults
    empty_dir = tmp_path / "empty_config"
    cfg = load_config(empty_dir)

    assert cfg.settings["hotkey"]["key"] == "Space"
    assert "github" in cfg.urls
    assert "calculator" in cfg.aliases


def test_load_custom_config(tmp_path: Path):
    config_dir = tmp_path / "custom_config"
    config_dir.mkdir()

    settings_file = config_dir / "settings.json"
    settings_file.write_text(json.dumps({
        "hotkey": {"modifiers": ["Ctrl"], "key": "K"},
        "ui": {"placeholder": "Custom Astra"}
    }))

    urls_file = config_dir / "urls.json"
    urls_file.write_text(json.dumps({
        "mywork": "https://company.internal"
    }))

    cfg = load_config(config_dir)
    assert cfg.settings["hotkey"]["key"] == "K"
    assert cfg.urls["mywork"] == "https://company.internal"


def test_corrupted_json_resilience(tmp_path: Path):
    config_dir = tmp_path / "corrupt_config"
    config_dir.mkdir()

    # Broken JSON file
    (config_dir / "settings.json").write_text("{ this is NOT valid JSON }")

    cfg = load_config(config_dir)
    # Should safely fallback to default settings without crashing
    assert cfg.settings["hotkey"]["key"] == DEFAULT_SETTINGS["hotkey"]["key"]
