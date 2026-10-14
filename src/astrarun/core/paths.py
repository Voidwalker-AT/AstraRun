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
- Zero required dependency on developer drives in RELEASE mode.
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


class AstraPaths:
    """Authoritative Central Path Service for AstraRun.

    Enforces that NO production subsystem resolves runtime paths relative to CWD.
    """

    @classmethod
    def install_dir(cls) -> Path:
        return get_install_root()

    @classmethod
    def user_data_dir(cls) -> Path:
        return get_app_data_dir()

    @classmethod
    def config_dir(cls) -> Path:
        return get_config_dir()

    @classmethod
    def data_dir(cls) -> Path:
        return get_data_dir()

    @classmethod
    def logs_dir(cls) -> Path:
        return get_logs_dir()

    @classmethod
    def cache_dir(cls) -> Path:
        return get_cache_dir()

    @classmethod
    def models_dir(cls) -> Path:
        return get_models_dir()

    @classmethod
    def skills_dir(cls) -> Path:
        return get_skills_dir()

    @classmethod
    def runtimes_dir(cls) -> Path:
        return get_runtimes_dir()

    @classmethod
    def temp_dir(cls) -> Path:
        custom_temp = os.environ.get("ASTRARUN_TEMP_DIR")
        if custom_temp:
            p = Path(custom_temp).resolve()
        elif sys.platform == "win32":
            temp_base = os.environ.get("TEMP") or os.environ.get("TMP") or str(Path.home() / "AppData" / "Local" / "Temp")
            p = Path(temp_base) / "AstraRun"
        else:
            p = Path("/tmp/astrarun")
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def sandbox_dir(cls) -> Path:
        if sys.platform == "win32":
            p = Path.home() / "AppData" / "LocalLow" / "AstraRun" / "sandbox"
        else:
            p = cls.data_dir() / "sandbox"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def machine_db_path(cls) -> Path:
        p = cls.data_dir() / "machine" / "machine_facts.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def state_file_path(cls) -> Path:
        return cls.data_dir() / "astrarun_state.json"

    @classmethod
    def summon_trigger_path(cls) -> Path:
        return cls.data_dir() / "astrarun_summon.trigger"

    @classmethod
    def program_dir(cls) -> Path:
        """Return the installation root for program binaries (%LOCALAPPDATA%\\Programs\\AstraRun or get_install_root())."""
        if getattr(sys, "frozen", False):
            return get_install_root()
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidate = Path(local_app) / "Programs" / "AstraRun"
            if candidate.exists():
                return candidate
        return get_install_root()

    @classmethod
    def workspace_root(cls) -> Path:
        """Resolve workspace root dynamically via env, discovery, or parent traversal."""
        ws_env = os.environ.get("WORKSPACE_ROOT")
        if ws_env and Path(ws_env).exists():
            return Path(ws_env).resolve()

        current = get_install_root()
        for parent in [current] + list(current.parents):
            if (parent / "workspace.json").exists():
                return parent
            if parent.name.lower() == "workspace":
                return parent

        home_ws = Path.home() / "Workspace"
        if home_ws.exists():
            return home_ws

        try:
            import string
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        except Exception:
            drives = ["C:\\"]
        for drive in drives:
            cand = Path(drive) / "Workspace"
            if cand.exists():
                return cand

        return current

    @classmethod
    def resolve_model(cls, relative_name: str, dev_fallback: Optional[str | Path] = None) -> Path:
        """Resolve model without ever moving or deleting external user assets."""
        return resolve_model_path(relative_name, dev_fallback)

    @classmethod
    def resolve_runtime(cls, binary_name: str, dev_fallback: Optional[str | Path] = None) -> Path:
        return resolve_runtime_binary(binary_name, dev_fallback)

    @classmethod
    def ensure_all_dirs(cls) -> None:
        ensure_app_dirs()
        cls.temp_dir()
        cls.sandbox_dir()
        cls.machine_db_path().parent.mkdir(parents=True, exist_ok=True)



def resolve_model_path(relative_name: str, dev_fallback: Optional[str | Path] = None) -> Path:
    """
    Resolve a model path.
    1. Checks models_config.json in config directory (configured existing assets).
    2. Checks user models directory (%LOCALAPPDATA%\\AstraRun\\models).
    3. Checks bundled models directory inside installation root.
    4. Checks configured machine model directories.
    5. In DEVELOPMENT mode: falls back to dev_fallback if found on disk.
    6. In RELEASE mode: defaults to user models directory path.
    """
    # 0. Check explicit models_config.json mapping
    config_map = get_config_dir() / "models_config.json"
    if config_map.exists():
        try:
            import json
            mapping = json.loads(config_map.read_text(encoding="utf-8"))
            if relative_name in mapping:
                p = Path(mapping[relative_name])
                if p.exists():
                    return p
        except Exception:
            pass

    user_model_path = get_models_dir() / relative_name
    if user_model_path.exists():
        return user_model_path

    bundle_model_path = get_install_root() / "models" / relative_name
    if bundle_model_path.exists():
        return bundle_model_path

    # 4. Check explicit development fallback or configured models repository
    if os.environ.get("ASTRARUN_ENV") != "release":
        if dev_fallback:
            dev_path = Path(dev_fallback)
            if dev_path.exists():
                return dev_path

        dev_models_dir = os.environ.get("ASTRARUN_MODELS_DIR")
        if dev_models_dir:
            dev_repo = Path(dev_models_dir) / relative_name
            if dev_repo.exists():
                return dev_repo

    return user_model_path


def resolve_runtime_binary(binary_name: str, dev_fallback: Optional[str | Path] = None) -> Path:
    """
    Resolve a runtime executable (e.g. llama-server.exe).
    1. Checks bundled runtimes directory ({INSTALL_DIR}\\runtimes\\binary_name).
    2. Checks user runtimes directory (%LOCALAPPDATA%\\AstraRun\\runtimes\\binary_name).
    3. Falls back to dev_fallback if found on disk.
    4. Defaults to bundled binary path.
    """
    bundled_binary = get_install_root() / "runtimes" / binary_name
    if bundled_binary.exists():
        return bundled_binary

    user_binary = get_runtimes_dir() / binary_name
    if user_binary.exists():
        return user_binary

    if dev_fallback:
        dev_path = Path(dev_fallback)
        if dev_path.exists():
            return dev_path

    return bundled_binary


def resolve_python_executable(explicit: Optional[str | Path] = None) -> str:
    """Resolve an authoritative Python interpreter for sandbox script execution."""
    if explicit and Path(explicit).exists():
        return str(explicit)

    # 1. Prefer current Python interpreter if running under Python (e.g. local .venv)
    if getattr(sys, "executable", None) and "astrarun" not in Path(sys.executable).name.lower() and Path(sys.executable).exists():
        return str(Path(sys.executable).resolve())

    # 2. Check project-relative venv
    proj_root = Path(__file__).resolve().parent.parent.parent.parent
    proj_venv = proj_root / ".venv" / "Scripts" / "python.exe"
    if proj_venv.exists():
        return str(proj_venv.resolve())

    if sys.prefix and (Path(sys.prefix) / "Scripts" / "python.exe").exists():
        return str((Path(sys.prefix) / "Scripts" / "python.exe").resolve())

    # 3. Check PATH system python
    import shutil
    py_path = shutil.which("python.exe") or shutil.which("python")
    if py_path and Path(py_path).exists() and "astrarun" not in Path(py_path).name.lower():
        return str(Path(py_path).resolve())

    # 4. Standard python installations
    local_app = os.environ.get("LOCALAPPDATA", "")
    for ver in ("Python313", "Python312", "Python311", "Python310"):
        cand = Path(local_app) / "Programs" / "Python" / ver / "python.exe"
        if cand.exists():
            return str(cand.resolve())

    return "python.exe"
