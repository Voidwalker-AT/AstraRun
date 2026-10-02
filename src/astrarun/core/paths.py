"""Canonical Windows Application Directory Layout and Runtime Path Resolution.

Complies with AstraRun 1.0 Release Specifications:
- Immutable Installation Directory (Application binaries, assets)
- Per-user Writable State: %LOCALAPPDATA%\\AstraRun\\
    - config/
    - data/
    - logs/
    - cache/
    - models/
    - skills/
    - runtimes/
- Zero required dependency on developer drives (E:\\) in RELEASE mode.
- Seamless fallback to developer overrides in DEVELOPMENT mode.
"""

from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path
from typing import Optional


class AppMode(str, Enum):
    """Runtime operating mode."""
    DEVELOPMENT = "DEVELOPMENT"
    RELEASE = "RELEASE"


def get_app_mode() -> AppMode:
    """Determine whether the application is running in DEVELOPMENT or RELEASE mode."""
    env_mode = os.environ.get("ASTRARUN_MODE", "").strip().upper()
    if env_mode == "RELEASE":
        return AppMode.RELEASE
    if env_mode == "DEVELOPMENT":
        return AppMode.DEVELOPMENT

    # When packaged via PyInstaller, sys.frozen is True
    if getattr(sys, "frozen", False):
        return AppMode.RELEASE

    # Check for marker file in installation root
    install_root = get_install_root()
    if (install_root / "installed.marker").exists():
        return AppMode.RELEASE

    return AppMode.DEVELOPMENT


def is_release_mode() -> bool:
    """Return True if running in RELEASE mode."""
    return get_app_mode() == AppMode.RELEASE


def get_install_root() -> Path:
    """Return the base directory where application binaries and assets reside."""
    if getattr(sys, "frozen", False):
        # PyInstaller one-file extracts to _MEIPASS; one-dir resides in executable parent dir
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).resolve().parent

    # Development: src/astrarun/core/paths.py -> 4 levels up to project root
    return Path(__file__).resolve().parent.parent.parent.parent


def get_app_data_dir() -> Path:
    """Return the per-user writable application data root (%LOCALAPPDATA%\\AstraRun)."""
    custom_root = os.environ.get("ASTRARUN_DATA_DIR")
    if custom_root:
        return Path(custom_root).resolve()

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "AstraRun"
        return Path.home() / "AppData" / "Local" / "AstraRun"

    # Posix fallback
    return Path.home() / ".astrarun"


def get_config_dir() -> Path:
    """Return %LOCALAPPDATA%\\AstraRun\\config."""
    return get_app_data_dir() / "config"


def get_data_dir() -> Path:
    """Return %LOCALAPPDATA%\\AstraRun\\data."""
    return get_app_data_dir() / "data"


def get_logs_dir() -> Path:
    """Return %LOCALAPPDATA%\\AstraRun\\logs."""
    return get_app_data_dir() / "logs"


def get_cache_dir() -> Path:
    """Return %LOCALAPPDATA%\\AstraRun\\cache."""
    return get_app_data_dir() / "cache"


def get_models_dir() -> Path:
    """Return %LOCALAPPDATA%\\AstraRun\\models."""
    return get_app_data_dir() / "models"


def get_skills_dir() -> Path:
    """Return %LOCALAPPDATA%\\AstraRun\\skills."""
    return get_app_data_dir() / "skills"


def get_runtimes_dir() -> Path:
    """Return %LOCALAPPDATA%\\AstraRun\\runtimes."""
    return get_app_data_dir() / "runtimes"


def ensure_app_dirs() -> None:
    """Create all required per-user writable directories if they do not exist."""
    for d in (
        get_config_dir(),
        get_data_dir(),
        get_logs_dir(),
        get_cache_dir(),
        get_models_dir(),
        get_skills_dir(),
        get_runtimes_dir(),
    ):
        d.mkdir(parents=True, exist_ok=True)


def resolve_model_path(relative_name: str, dev_fallback: Optional[str | Path] = None) -> Path:
    """
    Resolve a model path.
    1. Checks user models directory (%LOCALAPPDATA%\\AstraRun\\models).
    2. Checks bundled models directory inside installation root.
    3. In DEVELOPMENT mode: if neither exists, falls back to dev_fallback (e.g. E:\\AI_Models\\...).
    4. In RELEASE mode: strictly returns the models directory path.
    """
    user_model_path = get_models_dir() / relative_name
    if user_model_path.exists():
        return user_model_path

    bundle_model_path = get_install_root() / "models" / relative_name
    if bundle_model_path.exists():
        return bundle_model_path

    if not is_release_mode() and dev_fallback:
        dev_path = Path(dev_fallback)
        if dev_path.exists():
            return dev_path

    return user_model_path


def resolve_runtime_binary(binary_name: str, dev_fallback: Optional[str | Path] = None) -> Path:
    """
    Resolve a runtime executable (e.g. llama-server.exe).
    1. Checks bundled runtimes directory ({INSTALL_DIR}\\runtimes\\binary_name).
    2. Checks user runtimes directory (%LOCALAPPDATA%\\AstraRun\\runtimes\\binary_name).
    3. In DEVELOPMENT mode: falls back to dev_fallback if found on disk.
    4. In RELEASE mode: returns bundled or user runtime path.
    """
    bundled_binary = get_install_root() / "runtimes" / binary_name
    if bundled_binary.exists():
        return bundled_binary

    user_binary = get_runtimes_dir() / binary_name
    if user_binary.exists():
        return user_binary

    if not is_release_mode() and dev_fallback:
        dev_path = Path(dev_fallback)
        if dev_path.exists():
            return dev_path

    return bundled_binary
