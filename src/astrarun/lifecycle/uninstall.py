"""AstraRun 1.0 — Component Ownership & Uninstallation Lifecycle Engine.

Complies strictly with AstraRun 1.0 Product Specifications:
1. Strict Component Ownership: Distinguishes Astra-managed artifacts from external user-owned models/runtimes.
2. Zero-Loss Policy: External models (e.g. E:\\AI_Models\\GGUF\\...) are NEVER deleted under any circumstances.
3. Active Task Protection: Detects in-progress tasks before uninstallation and supports Pause/Checkpoint or Stop.
4. Measured Sizes: Computes real filesystem byte sizes dynamically.
5. IPC Graceful Shutdown: Requests clean resident termination before binary or state deletion.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from astrarun.core.logging import get_logger
from astrarun.core.paths import (
    get_app_data_dir,
    get_config_dir,
    get_data_dir,
    get_logs_dir,
    get_cache_dir,
    get_models_dir,
    get_skills_dir,
    get_runtimes_dir,
    get_install_root,
)

logger = get_logger("astrarun.lifecycle.uninstall")


class ComponentOwnership(str, Enum):
    """Classification of files and directories referenced by AstraRun."""
    APPLICATION_BINARIES = "APPLICATION_BINARIES"
    CONFIGURATION = "CONFIGURATION"
    LOGS = "LOGS"
    CACHE = "CACHE"
    TASK_HISTORY = "TASK_HISTORY"
    MEMORY_DATABASE = "MEMORY_DATABASE"
    RAG_INDEX = "RAG_INDEX"
    SKILLS = "SKILLS"
    GENERATED_TEMP_FILES = "GENERATED_TEMP_FILES"
    ASTRA_MANAGED_MODELS = "ASTRA_MANAGED_MODELS"
    EXTERNAL_EXISTING_MODELS = "EXTERNAL_EXISTING_MODELS"
    ASTRA_MANAGED_RUNTIMES = "ASTRA_MANAGED_RUNTIMES"
    EXTERNAL_EXISTING_RUNTIMES = "EXTERNAL_EXISTING_RUNTIMES"
    QUARANTINE_DOWNLOADS = "QUARANTINE_DOWNLOADS"


@dataclass
class ComponentInventoryItem:
    """An inventory record of an asset or state directory owned or referenced by Astra."""
    id: str
    label: str
    category: ComponentOwnership
    path: Path
    size_bytes: int
    is_external: bool
    removable: bool
    selected_default: bool
    status_note: str

    @property
    def formatted_size(self) -> str:
        """Human-readable size string."""
        if self.is_external:
            return "External"
        if self.size_bytes == 0:
            return "0 KB"
        kb = self.size_bytes / 1024
        if kb < 1024:
            return f"{kb:.1f} KB"
        mb = kb / 1024
        if mb < 1024:
            return f"{mb:.1f} MB"
        gb = mb / 1024
        return f"{gb:.2f} GB"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["path"] = str(self.path)
        d["formatted_size"] = self.formatted_size
        return d


def compute_path_size(p: Path) -> int:
    """Calculate total byte size of a file or directory recursively."""
    if not p.exists():
        return 0
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return 0

    total = 0
    try:
        for entry in os.scandir(p):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += compute_path_size(Path(entry.path))
            except OSError:
                continue
    except OSError:
        pass
    return total


def scan_uninstall_inventory(
    base_data_dir: Optional[Path] = None,
    install_root: Optional[Path] = None,
) -> List[ComponentInventoryItem]:
    """
    Produce a complete, typed inventory of all components owned or referenced by AstraRun.
    
    Categorizes internal user state vs managed assets vs external user-owned models/runtimes.
    """
    app_data = base_data_dir or get_app_data_dir()
    inst_root = install_root or get_install_root()
    items: List[ComponentInventoryItem] = []

    # 1. Application Binaries (Always removed by uninstaller)
    items.append(
        ComponentInventoryItem(
            id="binaries",
            label="AstraRun Application Binaries",
            category=ComponentOwnership.APPLICATION_BINARIES,
            path=inst_root,
            size_bytes=compute_path_size(inst_root),
            is_external=False,
            removable=True,
            selected_default=True,
            status_note="Application executables, DLLs, and internal assets (Always removed)",
        )
    )

    # 2. Local User Configuration
    cfg_path = app_data / "config"
    items.append(
        ComponentInventoryItem(
            id="config",
            label="Preferences & Settings",
            category=ComponentOwnership.CONFIGURATION,
            path=cfg_path,
            size_bytes=compute_path_size(cfg_path),
            is_external=False,
            removable=True,
            selected_default=False,
            status_note="Workstation settings, autostart, and discovery markers",
        )
    )

    # 3. Task History & Ledger
    task_db = app_data / "data" / "tasks.db"
    ledger_db = app_data / "data" / "task_ledger.db"
    checkpoints_dir = app_data / "data" / "checkpoints"
    history_size = compute_path_size(task_db) + compute_path_size(ledger_db) + compute_path_size(checkpoints_dir)
    items.append(
        ComponentInventoryItem(
            id="task_history",
            label="Task History & Checkpoints",
            category=ComponentOwnership.TASK_HISTORY,
            path=app_data / "data",
            size_bytes=history_size,
            is_external=False,
            removable=True,
            selected_default=False,
            status_note="History of executed commands, durability checkpoints, and ledger",
        )
    )

    # 4. Semantic Memory & Retrieval Database
    mem_db = app_data / "data" / "memory.db"
    rag_dir = app_data / "data" / "rag"
    learning_db = app_data / "data" / "learning.db"
    mem_size = compute_path_size(mem_db) + compute_path_size(rag_dir) + compute_path_size(learning_db)
    items.append(
        ComponentInventoryItem(
            id="memory",
            label="Memory & Retrieval Index",
            category=ComponentOwnership.MEMORY_DATABASE,
            path=app_data / "data",
            size_bytes=mem_size,
            is_external=False,
            removable=True,
            selected_default=False,
            status_note="Learned user habits, context memory, and document embeddings",
        )
    )

    # 5. Learned Skills
    skills_dir = app_data / "skills"
    items.append(
        ComponentInventoryItem(
            id="skills",
            label="Learned Skills & Dynamic Tools",
            category=ComponentOwnership.SKILLS,
            path=skills_dir,
            size_bytes=compute_path_size(skills_dir),
            is_external=False,
            removable=True,
            selected_default=False,
            status_note="Synthesized Python tools and promoted procedural skills",
        )
    )

    # 6. Logs & Diagnostic Traces
    logs_dir = app_data / "logs"
    items.append(
        ComponentInventoryItem(
            id="logs",
            label="Logs & Crash Diagnostics",
            category=ComponentOwnership.LOGS,
            path=logs_dir,
            size_bytes=compute_path_size(logs_dir),
            is_external=False,
            removable=True,
            selected_default=False,
            status_note="Application session logs, last-gasp files, and error traces",
        )
    )

    # 7. Temporary Cache
    cache_dir = app_data / "cache"
    items.append(
        ComponentInventoryItem(
            id="cache",
            label="Temporary Application Cache",
            category=ComponentOwnership.CACHE,
            path=cache_dir,
            size_bytes=compute_path_size(cache_dir),
            is_external=False,
            removable=True,
            selected_default=True,
            status_note="Cached icons, transient indices, and query buffers",
        )
    )

    # 8. Astra-Managed Models (%LOCALAPPDATA%\AstraRun\models)
    models_dir = app_data / "models"
    items.append(
        ComponentInventoryItem(
            id="managed_models",
            label="Astra-Managed Model Weights",
            category=ComponentOwnership.ASTRA_MANAGED_MODELS,
            path=models_dir,
            size_bytes=compute_path_size(models_dir),
            is_external=False,
            removable=True,
            selected_default=False,
            status_note="Local model weights downloaded directly by Astra to app storage",
        )
    )

    # 9. Astra-Managed Runtimes (%LOCALAPPDATA%\AstraRun\runtimes)
    runtimes_dir = app_data / "runtimes"
    items.append(
        ComponentInventoryItem(
            id="managed_runtimes",
            label="Astra-Managed Isolated Runtimes",
            category=ComponentOwnership.ASTRA_MANAGED_RUNTIMES,
            path=runtimes_dir,
            size_bytes=compute_path_size(runtimes_dir),
            is_external=False,
            removable=True,
            selected_default=False,
            status_note="Sandboxed execution runtimes managed by Astra",
        )
    )

    # 10. External User-Owned Models (DISCOVERED ON WORKSTATION — NEVER REMOVABLE)
    from astrarun.discovery import ExistingCapabilityResolver, CompatibilityStatus
    try:
        resolver = ExistingCapabilityResolver()
        disc_models = resolver.discover_models()
        for key, m in disc_models.items():
            if m.status in (CompatibilityStatus.EXACT_MATCH, CompatibilityStatus.COMPATIBLE_VERSION) and m.path:
                m_path = Path(m.path)
                # Verify it is OUTSIDE app_data
                try:
                    m_path.relative_to(app_data)
                    continue  # Inside app_data, handled as managed
                except ValueError:
                    pass

                items.append(
                    ComponentInventoryItem(
                        id=f"ext_model_{key}",
                        label=f"{m.name} ({m_path.name})",
                        category=ComponentOwnership.EXTERNAL_EXISTING_MODELS,
                        path=m_path,
                        size_bytes=compute_path_size(m_path),
                        is_external=True,
                        removable=False,
                        selected_default=False,
                        status_note="Preserved — not installed by Astra (User-owned model)",
                    )
                )
    except Exception as err:
        logger.debug("External model discovery skipped: %s", err)

    # 11. External Tools & Runtimes (Git, Python, Vivaldi, CUDA — NEVER REMOVABLE)
    items.append(
        ComponentInventoryItem(
            id="ext_system_tools",
            label="Workstation Tools (Git, Python, Browsers, CUDA)",
            category=ComponentOwnership.EXTERNAL_EXISTING_RUNTIMES,
            path=Path("C:/"),
            size_bytes=0,
            is_external=True,
            removable=False,
            selected_default=False,
            status_note="Preserved — existing host workstation tools",
        )
    )

    return items


def check_active_tasks_and_resident() -> Dict[str, Any]:
    """
    Check if a resident AstraRun process is active and whether tasks are currently executing.
    """
    res = {
        "is_running": False,
        "pid": None,
        "active_task_count": 0,
        "tasks": [],
    }

    try:
        state_file = get_data_dir() / "astrarun_state.json"
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
            pid = data.get("pid")
            if pid:
                import psutil
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    if "AstraRun" in proc.name() or "python" in proc.name().lower():
                        res["is_running"] = True
                        res["pid"] = pid

        # Check task ledger for non-terminal tasks
        ledger_db = get_data_dir() / "task_ledger.db"
        if ledger_db.exists():
            import sqlite3
            conn = sqlite3.connect(str(ledger_db))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, status FROM tasks WHERE status IN ('PENDING', 'RUNNING', 'WAITING_CONFIRMATION')"
            )
            rows = cursor.fetchall()
            conn.close()
            res["active_task_count"] = len(rows)
            res["tasks"] = [{"id": r[0], "title": r[1], "status": r[2]} for r in rows]
    except Exception as err:
        logger.debug("Error checking active tasks: %s", err)

    return res


def request_graceful_shutdown(timeout_sec: float = 3.0) -> bool:
    """
    Request resident AstraRun instance to shut down cleanly via IPC before uninstalling binaries.
    """
    try:
        import win32file
        import win32pipe
        import pywintypes

        pipe_name = r"\\.\pipe\astrarun_ipc"
        handle = win32file.CreateFile(
            pipe_name,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0,
            None,
            win32file.OPEN_EXISTING,
            0,
            None,
        )
        msg = json.dumps({"command": "QUIT", "args": {}}) + "\n"
        win32file.WriteFile(handle, msg.encode("utf-8"))
        win32file.CloseHandle(handle)
        logger.info("Sent graceful QUIT command to resident AstraRun via IPC.")
    except Exception as ipc_err:
        logger.debug("IPC quit signal not delivered (may not be resident): %s", ipc_err)

    # Wait for process exit if PID known
    try:
        state_file = get_data_dir() / "astrarun_state.json"
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
            pid = data.get("pid")
            if pid:
                import psutil
                if psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    p.wait(timeout=timeout_sec)
                    return True
    except Exception:
        pass
    return False


def create_uninstall_plan(
    selected_item_ids: Set[str],
    inventory: List[ComponentInventoryItem],
    app_data_root: Optional[Path] = None,
    install_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Generate a validated, secure uninstallation removal plan.
    
    Guarantees:
    - Never includes any non-removable or external item in the removal list.
    - Explicitly verifies that all targeted removal directories are within Astra's application scope.
    """
    app_data = app_data_root or get_app_data_dir()
    inst_root = install_root or get_install_root()

    paths_to_remove: List[str] = []
    paths_to_preserve: List[str] = []
    removed_items_meta: List[Dict[str, Any]] = []

    for item in inventory:
        # ABSOLUTE SAFETY INVARIANT: External assets are ALWAYS preserved
        if item.is_external or not item.removable:
            paths_to_preserve.append(str(item.path))
            continue

        if item.id in selected_item_ids:
            p_str = str(item.path.resolve())
            # Boundary check: Target path must be within app_data or install_root
            try:
                item.path.resolve().relative_to(app_data.resolve())
                paths_to_remove.append(p_str)
                removed_items_meta.append(item.to_dict())
            except ValueError:
                try:
                    item.path.resolve().relative_to(inst_root.resolve())
                    paths_to_remove.append(p_str)
                    removed_items_meta.append(item.to_dict())
                except ValueError:
                    logger.critical("[SECURITY_GATE] Refusing to remove out-of-scope path: %s", p_str)
                    paths_to_preserve.append(p_str)
        else:
            paths_to_preserve.append(str(item.path))

    return {
        "timestamp": time.time(),
        "selected_ids": list(selected_item_ids),
        "paths_to_remove": sorted(list(set(paths_to_remove))),
        "paths_to_preserve": sorted(list(set(paths_to_preserve))),
        "removed_items": removed_items_meta,
    }


def execute_uninstall_plan(
    plan: Dict[str, Any],
    app_data_root: Optional[Path] = None,
    install_root: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute removal of validated paths according to the plan.
    
    Protects user safety: Refuses deletion of any path outside Astra's known scope.
    """
    app_data = (app_data_root or get_app_data_dir()).resolve()
    inst_root = (install_root or get_install_root()).resolve()

    deleted: List[str] = []
    skipped: List[str] = []
    errors: List[Dict[str, str]] = []

    for p_str in plan.get("paths_to_remove", []):
        p = Path(p_str).resolve()
        if not p.exists():
            continue

        # Strict containment verification
        is_safe = False
        try:
            p.relative_to(app_data)
            is_safe = True
        except ValueError:
            try:
                p.relative_to(inst_root)
                is_safe = True
            except ValueError:
                is_safe = False

        if not is_safe:
            logger.critical("[SECURITY_GATE] Blocked unauthorized removal of external path: %s", p)
            skipped.append(str(p))
            continue

        if dry_run:
            deleted.append(str(p))
            continue

        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            deleted.append(str(p))
        except Exception as err:
            logger.error("Failed to delete %s: %s", p, err)
            errors.append({"path": str(p), "error": str(err)})

    # Also clean autostart registry entry
    if not dry_run and sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, "AstraRun")
                logger.info("Cleaned AstraRun from HKCU\\...\\Run")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception as err:
            logger.debug("Registry cleanup notice: %s", err)

    return {
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
    }
