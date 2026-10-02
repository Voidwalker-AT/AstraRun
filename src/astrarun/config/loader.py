"""Configuration loader with resilient fallbacks for AstraRun."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrarun.core.logging import get_logger
from astrarun.core.models import AppInfo
from astrarun.core.paths import resolve_model_path, resolve_runtime_binary

logger = get_logger("astrarun.config")


DEFAULT_SETTINGS: dict[str, Any] = {
    "hotkey": {
        "modifiers": ["Alt"],
        "key": "Space"
    },
    "ui": {
        "width": 640,
        "height": 56,
        "theme": "dark",
        "placeholder": "What do you want to do?",
        "hide_on_focus_loss": True,
        "opacity": 0.98,
        "max_suggestions": 5
    },
    "telemetry": {
        "enabled": True,
        "file": "data/routing_events.jsonl",
        "store_raw_request": True
    },
    "shadow_models": {
        "laya": True,
        "kev": False
    },
    "laya": {
        "enabled": True,
        "mode": "shadow",
        "model": "convaiinnovations/laya",
        "device": "cpu",
        "confidence_threshold": 0.75,
        "shadow_file": "data/laya_shadow_events.jsonl"
    },
    "kev": {
        "enabled": False,
        "mode": "shadow",
        "model": "jaredpalmer/kev-0.8b",
        "base_model": "Qwen/Qwen3.5-0.8B-Base",
        "device": "cpu",
        "confidence_threshold": 0.75,
        "shadow_file": "data/kev_shadow_events.jsonl"
    },
    "logging": {
        "level": "INFO",
        "file": "logs/astrarun.log",
        "max_bytes": 10485760,
        "backup_count": 3
    },
    "history": {
        "enabled": True,
        "db_path": "data/astra_history.db",
        "store_raw_requests": True,
        "retention_days": 30,
        "max_tasks": 5000,
        "store_result_payloads": False
    },
    "learning": {
        "enabled": True,
        "db_path": "data/astra_learning.db",
        "learn_from_history": True,
        "confidence_threshold": 0.85,
        "min_support_count": 3,
        "allow_training_dataset_export": False,
        "auto_propose_skills": True
    },
    "models": {
        "server_binary": str(resolve_runtime_binary("llama-server.exe", dev_fallback=r"E:\AI_Runtimes\llama.cpp-spark\llama-server.exe")),
        "spark": {
            "model_id": "spark",
            "role": "FAST",
            "endpoint": "http://127.0.0.1:8090",
            "port": 8090,
            "model_path": str(resolve_model_path("Spark-X2.5-1.7B-Q4_K_M.gguf", dev_fallback=r"E:\AI_Models\GGUF\Spark-X2.5-1.7B-Q4_K_M.gguf")),
            "residency": "PINNED",
            "ngl": 99,
            "ctx_size": 4096,
        },
        "qwen": {
            "model_id": "qwen",
            "role": "DEEP",
            "endpoint": "http://127.0.0.1:8089",
            "port": 8089,
            "model_path": str(resolve_model_path("qwen2.5-coder-1.5b-instruct-q4_k_m.gguf", dev_fallback=r"E:\AI_Models\GGUF\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")),
            "residency": "WARM",
            "ngl": 99,
            "ctx_size": 4096,
        },
    },
    "rag": {
        "enabled": True,
        "db_path": "data/astra_memory.db",
        "embedding_model_dir": str(resolve_model_path("bge-small-en-v1.5", dev_fallback=r"E:\AI_Models\ONNX\bge-small-en-v1.5")),
        "dimension": 384,
        "rrf_k": 60,
        "max_retrieved_tokens": 1500,
        "auto_index_workspace": True,
        "batch_size": 16,
    }
}

DEFAULT_URLS: dict[str, str] = {
    "github": "https://github.com",
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "reddit": "https://reddit.com",
    "duckduckgo": "https://duckduckgo.com"
}

DEFAULT_ALIASES: dict[str, str] = {
    "calculator": "calc",
    "editor": "notepad",
    "notes": "notepad",
    "text": "notepad",
    "vscode": "code",
    "vs code": "code",
    "browser": "vivaldi",
    "terminal": "wt",
    "windows terminal": "wt",
    "powershell": "pwsh",
    "pwsh": "pwsh",
    "cmd": "cmd",
    "prompt": "cmd",
    "explorer": "explorer",
    "files": "explorer"
}


@dataclass
class AppConfig:
    """Consolidated application configuration."""
    settings: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    configured_apps: dict[str, AppInfo] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ALIASES))
    urls: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_URLS))

    def get_model_config(self, model_name: str) -> dict[str, Any]:
        """Retrieve model configuration dictionary by name ('spark', 'qwen')."""
        models_cfg = self.settings.get("models", DEFAULT_SETTINGS.get("models", {}))
        return dict(models_cfg.get(model_name.lower(), {}))

    def get_rag_config(self) -> dict[str, Any]:
        """Retrieve RAG and memory subsystem configuration."""
        return dict(self.settings.get("rag", DEFAULT_SETTINGS.get("rag", {})))



def _read_json_file(file_path: Path, fallback: Any) -> Any:
    """Safely read and parse a JSON file, returning fallback on any error."""
    if not file_path.exists():
        logger.debug("Configuration file not found at %s; using fallback.", file_path)
        return fallback

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as err:
        logger.error("JSON decode error reading %s: %s; using fallback.", file_path, err)
        return fallback
    except Exception as err:
        logger.error("Unexpected error reading %s: %s; using fallback.", file_path, err)
        return fallback


def load_config(config_dir: str | Path = "config") -> AppConfig:
    """Load all configuration files from the specified configuration directory."""
    dir_path = Path(config_dir)

    # 1. Load settings
    settings_file = dir_path / "settings.json"
    settings_data = _read_json_file(settings_file, DEFAULT_SETTINGS)
    if not isinstance(settings_data, dict):
        settings_data = DEFAULT_SETTINGS

    # 2. Load configured apps
    apps_file = dir_path / "apps.json"
    apps_data = _read_json_file(apps_file, {})
    configured_apps: dict[str, AppInfo] = {}
    if isinstance(apps_data, dict):
        for key, val in apps_data.items():
            if isinstance(val, dict) and "path" in val:
                configured_apps[key.lower()] = AppInfo(
                    key=key.lower(),
                    name=val.get("name", key),
                    path=val["path"],
                    description=val.get("description", "")
                )

    # 3. Load aliases
    aliases_file = dir_path / "aliases.json"
    aliases_data = _read_json_file(aliases_file, DEFAULT_ALIASES)
    if not isinstance(aliases_data, dict):
        aliases_data = DEFAULT_ALIASES
    aliases = {k.lower(): str(v).lower() for k, v in aliases_data.items()}

    # 4. Load URLs
    urls_file = dir_path / "urls.json"
    urls_data = _read_json_file(urls_file, DEFAULT_URLS)
    if not isinstance(urls_data, dict):
        urls_data = DEFAULT_URLS
    urls = {k.lower(): str(v) for k, v in urls_data.items()}

    logger.info(
        "Configurations loaded: %d apps, %d aliases, %d urls.",
        len(configured_apps), len(aliases), len(urls)
    )
    return AppConfig(
        settings=settings_data,
        configured_apps=configured_apps,
        aliases=aliases,
        urls=urls
    )
