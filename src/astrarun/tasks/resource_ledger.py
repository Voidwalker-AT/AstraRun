"""Astra-Owned Resource Lifecycle Ledger and Window Cleanup Subsystem.

Enforces the core invariant:
  TASK-SCOPED RESOURCE OWNERSHIP + VERIFIED CLEANUP
  - Astra may close ONLY resources that Astra itself created for the task.
  - Pre-launch snapshotting disambiguates new instances from existing user windows.
  - Safe-before-close verification ensures artifacts exist on disk before termination.
  - Physical user interaction detaches resources ('Do Not Fight The User').
  - Crash/restart recovery validates PID creation times to eliminate PID reuse hazards.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil

from astrarun.core.logging import get_logger
from astrarun.core.paths import AstraPaths

logger = get_logger("astrarun.tasks.resource_ledger")

# Win32 Constants
WM_CLOSE = 0x0010
BM_CLICK = 0x00F5
WM_SYSCOMMAND = 0x0112
SC_CLOSE = 0xF060


def _ensure_desktop_attached() -> None:
    """Ensure current thread is attached to the interactive input desktop."""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.OpenDesktopW.restype = ctypes.c_void_p
        user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]
        user32.SetThreadDesktop.restype = ctypes.c_int
        DESKTOP_ALL = 0x01FF
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_ALL)
        if not hdesk:
            hdesk = user32.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def clean_notepad_tabstate_for_path(document_path: str) -> None:
    """Clean Windows 11 Notepad TabState session file for a temporary or test document path."""
    if not document_path:
        return
    try:
        import glob
        localappdata = os.environ.get("LOCALAPPDATA", "")
        tabstate_dir = os.path.join(localappdata, "Packages", "Microsoft.WindowsNotepad_8wekyb3d8bbwe", "LocalState", "TabState")
        if not os.path.exists(tabstate_dir):
            return
        target_stem = os.path.basename(document_path).lower()
        target_path_lower = os.path.abspath(document_path).lower()
        for f in glob.glob(os.path.join(tabstate_dir, "*.bin")):
            try:
                with open(f, "rb") as fp:
                    raw = fp.read()
                raw_u16 = raw.decode("utf-16le", errors="ignore").lower()
                if target_stem in raw_u16 or target_path_lower in raw_u16:
                    base = os.path.basename(f).split(".")[0]
                    for sibling in glob.glob(os.path.join(tabstate_dir, f"{base}*")):
                        try:
                            os.remove(sibling)
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass


class ResourceType(str, Enum):

    APPLICATION = "APPLICATION"
    WINDOW = "WINDOW"
    BROWSER_INSTANCE = "BROWSER_INSTANCE"
    BROWSER_TAB = "BROWSER_TAB"
    HELPER_PROCESS = "HELPER_PROCESS"
    DOCUMENT = "DOCUMENT"
    EXPLORER_WINDOW = "EXPLORER_WINDOW"
    TEST_APP = "TEST_APP"
    OTHER = "OTHER"


class CleanupPolicy(str, Enum):
    AUTO_CLOSE_ON_COMPLETION = "AUTO_CLOSE_ON_COMPLETION"
    SAVE_BEFORE_CLOSE = "SAVE_BEFORE_CLOSE"
    DETACH_ON_USER_INTERACTION = "DETACH_ON_USER_INTERACTION"
    PRESERVE_ON_FAILURE = "PRESERVE_ON_FAILURE"
    PERSIST_ARTIFACT_THEN_CLOSE = "PERSIST_ARTIFACT_THEN_CLOSE"
    NEVER_CLOSE = "NEVER_CLOSE"


class ContentClassification(str, Enum):
    TASK_ARTIFACT = "TASK_ARTIFACT"
    TEMPORARY_TEST_CONTENT = "TEMPORARY_TEST_CONTENT"
    UNSAVED_USER_CONTENT = "UNSAVED_USER_CONTENT"
    NONE = "NONE"


class ResourceLifecycleState(str, Enum):
    DISCOVERED = "DISCOVERED"
    LAUNCHED = "LAUNCHED"
    ACTIVE = "ACTIVE"
    USER_TAKEOVER_DETACHED = "USER_TAKEOVER_DETACHED"
    SAVING = "SAVING"
    SAVED = "SAVED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    ORPHANED_CLEANED = "ORPHANED_CLEANED"
    FAILED_CLEANUP = "FAILED_CLEANUP"
    STALE_REUSED = "STALE_REUSED"


@dataclass
class OwnedResource:
    """Represents an interactive or OS resource tracked under explicit Astra ownership."""
    resource_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = "default_task"
    resource_type: ResourceType = ResourceType.APPLICATION
    launching_capability: str = "open_application"
    pid: Optional[int] = None
    hwnd: Optional[int] = None
    process_creation_time: Optional[float] = None
    document_path: Optional[str] = None
    astra_created: bool = True
    existed_before: bool = False
    cleanup_policy: CleanupPolicy = CleanupPolicy.AUTO_CLOSE_ON_COMPLETION
    content_classification: ContentClassification = ContentClassification.NONE
    lifecycle_state: ResourceLifecycleState = ResourceLifecycleState.ACTIVE
    user_interacted: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "task_id": self.task_id,
            "resource_type": self.resource_type.value if isinstance(self.resource_type, ResourceType) else str(self.resource_type),
            "launching_capability": self.launching_capability,
            "pid": self.pid,
            "hwnd": self.hwnd,
            "process_creation_time": self.process_creation_time,
            "document_path": self.document_path,
            "astra_created": self.astra_created,
            "existed_before": self.existed_before,
            "cleanup_policy": self.cleanup_policy.value if isinstance(self.cleanup_policy, CleanupPolicy) else str(self.cleanup_policy),
            "content_classification": self.content_classification.value if isinstance(self.content_classification, ContentClassification) else str(self.content_classification),
            "lifecycle_state": self.lifecycle_state.value if isinstance(self.lifecycle_state, ResourceLifecycleState) else str(self.lifecycle_state),
            "user_interacted": self.user_interacted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> OwnedResource:
        return cls(
            resource_id=d["resource_id"],
            task_id=d.get("task_id", "default_task"),
            resource_type=ResourceType(d.get("resource_type", ResourceType.APPLICATION.value)),
            launching_capability=d.get("launching_capability", "unknown"),
            pid=d.get("pid"),
            hwnd=d.get("hwnd"),
            process_creation_time=d.get("process_creation_time"),
            document_path=d.get("document_path"),
            astra_created=bool(d.get("astra_created", True)),
            existed_before=bool(d.get("existed_before", False)),
            cleanup_policy=CleanupPolicy(d.get("cleanup_policy", CleanupPolicy.AUTO_CLOSE_ON_COMPLETION.value)),
            content_classification=ContentClassification(d.get("content_classification", ContentClassification.NONE.value)),
            lifecycle_state=ResourceLifecycleState(d.get("lifecycle_state", ResourceLifecycleState.ACTIVE.value)),
            user_interacted=bool(d.get("user_interacted", False)),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            metadata=d.get("metadata", {}),
        )


@dataclass
class PreLaunchSnapshot:
    """Pre-launch environment snapshot of active processes and desktop windows."""
    timestamp: float
    pids: Dict[int, Tuple[str, float]]  # pid -> (process_name, create_time)
    hwnds: Dict[int, Tuple[int, str, str]]  # hwnd -> (pid, title, class_name)


class AstraResourceLedger:
    """
    SQLite-backed ledger for task-scoped resource ownership, persistence,
    and verified deterministic cleanup.
    """

    _instance: Optional[AstraResourceLedger] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, db_path: Optional[Path | str] = None) -> AstraResourceLedger:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(db_path=db_path)
            return cls._instance

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path is None:
            self.db_path = AstraPaths.data_dir() / "astra_history.db"
        else:
            self.db_path = Path(db_path)

        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=10.0,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA foreign_keys = ON;")
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS owned_resources (
                    resource_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    launching_capability TEXT NOT NULL,
                    pid INTEGER,
                    hwnd INTEGER,
                    process_creation_time REAL,
                    document_path TEXT,
                    astra_created INTEGER NOT NULL DEFAULT 1,
                    existed_before INTEGER NOT NULL DEFAULT 0,
                    cleanup_policy TEXT NOT NULL DEFAULT 'AUTO_CLOSE_ON_COMPLETION',
                    content_classification TEXT NOT NULL DEFAULT 'NONE',
                    lifecycle_state TEXT NOT NULL DEFAULT 'ACTIVE',
                    user_interacted INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_owned_res_task ON owned_resources(task_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_owned_res_state ON owned_resources(lifecycle_state);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_owned_res_pid ON owned_resources(pid);")
            conn.commit()

    # -------------------------------------------------------------------------
    # Snapshotting and Disambiguation
    # -------------------------------------------------------------------------

    def capture_pre_launch_snapshot(self) -> PreLaunchSnapshot:
        """Capture all currently running processes and visible top-level windows."""
        t_snap = time.time()
        pids: Dict[int, Tuple[str, float]] = {}
        for p in psutil.process_iter(["name", "create_time"]):
            try:
                pids[p.pid] = (p.info["name"] or "", p.info["create_time"] or 0.0)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        hwnds: Dict[int, Tuple[int, str, str]] = {}
        if sys.platform == "win32":
            _ensure_desktop_attached()
            user32 = ctypes.windll.user32
            from ctypes import wintypes

            def enum_cb(h: int, l: int) -> bool:
                if user32.IsWindowVisible(h):
                    pid_buf = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(pid_buf))
                    length = user32.GetWindowTextLengthW(h)
                    title = ""
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(h, buf, length + 1)
                        title = buf.value
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(h, cls_buf, 256)
                    hwnds[h] = (pid_buf.value, title, cls_buf.value)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        return PreLaunchSnapshot(timestamp=t_snap, pids=pids, hwnds=hwnds)

    def identify_and_register_launched_resource(
        self,
        task_id: str,
        capability: str,
        pre_snapshot: PreLaunchSnapshot,
        expected_name_or_class: Optional[str] = None,
        timeout_sec: float = 4.0,
        cleanup_policy: CleanupPolicy = CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
        content_classification: ContentClassification = ContentClassification.NONE,
        document_path: Optional[str] = None,
        resource_type: ResourceType = ResourceType.APPLICATION,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OwnedResource:
        """
        Poll and identify the newly spawned PID and HWND created after pre_snapshot.
        Registers the resulting resource in SQLite with astra_created=True.
        """
        deadline = time.time() + timeout_sec
        new_pid: Optional[int] = None
        new_hwnd: Optional[int] = None
        proc_create_time: Optional[float] = None
        pid_found_at: Optional[float] = None
        user32 = ctypes.windll.user32 if sys.platform == "win32" else None

        target_name_lower = (expected_name_or_class or "").lower().replace(".exe", "")
        aliases = [target_name_lower] if target_name_lower else []
        try:
            from pathlib import Path
            from astrarun.discovery.entity_resolver import SemanticEntityResolver
            resolver = SemanticEntityResolver()
            res_ent = resolver.resolve_application(target_name_lower)
            if res_ent:
                stem = Path(res_ent.target_path).stem.lower()
                aliases.extend([stem, res_ent.name.lower()])
        except Exception:
            pass
        aliases = list(set([a for a in aliases if a]))

        while time.time() < deadline:
            time.sleep(0.15)
            # 1. Scan for new processes
            if not new_pid:
                for p in psutil.process_iter(["name", "create_time"]):
                    try:
                        c_time = p.info["create_time"] or 0.0
                        p_name = (p.info["name"] or "").lower()
                        # A new process is either not in snapshot, or created at or after snapshot time
                        is_new = (p.pid not in pre_snapshot.pids) or (c_time >= pre_snapshot.timestamp - 0.25)
                        name_matches = (not aliases) or any(a in p_name for a in aliases)
                        if is_new and name_matches:
                            new_pid = p.pid
                            proc_create_time = c_time
                            pid_found_at = time.time()
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

            # 2. Scan for new windows
            if sys.platform == "win32":
                _ensure_desktop_attached()
                current_hwnds: Dict[int, Tuple[int, str, str]] = {}

                def enum_cb(h: int, l: int) -> bool:
                    if user32.IsWindowVisible(h):
                        pid_buf = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(h, ctypes.byref(pid_buf))
                        length = user32.GetWindowTextLengthW(h)
                        title = ""
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(h, buf, length + 1)
                            title = buf.value
                        cls_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(h, cls_buf, 256)
                        current_hwnds[h] = (pid_buf.value, title, cls_buf.value)
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

                for h, (w_pid, w_title, w_cls) in current_hwnds.items():
                    if h not in pre_snapshot.hwnds:
                        # Window was not in snapshot
                        title_lower = w_title.lower()
                        cls_lower = w_cls.lower()
                        if new_pid and w_pid == new_pid:
                            new_hwnd = h
                            break
                        if aliases and any(a in title_lower or a in cls_lower for a in aliases):
                            new_hwnd = h
                            if not new_pid:
                                new_pid = w_pid
                                try:
                                    proc_create_time = psutil.Process(w_pid).create_time()
                                except Exception:
                                    pass
                            break

            # If both PID and HWND are identified, we are done
            if new_pid and new_hwnd:
                break

            # If PID found but no window appeared after 4.0s, terminate polling
            if new_pid and pid_found_at and (time.time() - pid_found_at >= 4.0):
                break

            # If HWND found without PID, terminate polling
            if new_hwnd and not new_pid:
                break

        # Fallback check for new window if PID was found but HWND was still None
        if not new_hwnd and sys.platform == "win32":
            for h, (w_pid, w_title, w_cls) in current_hwnds.items():
                if h not in pre_snapshot.hwnds:
                    t_low = w_title.lower()
                    if aliases and any(a in t_low for a in aliases):
                        new_hwnd = h
                        if not new_pid:
                            new_pid = w_pid
                        break

        # If window HWND was found on Windows, ensure new_pid is the actual window process PID
        if new_hwnd and sys.platform == "win32":
            try:
                pbuf = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(new_hwnd, ctypes.byref(pbuf))
                window_pid = pbuf.value
                if window_pid and psutil.pid_exists(window_pid):
                    new_pid = window_pid
                    try:
                        proc_create_time = psutil.Process(new_pid).create_time()
                    except Exception:
                        pass
            except Exception:
                pass

        # If a new process or window was identified, create registered OwnedResource
        astra_created = bool(new_pid or new_hwnd)
        meta = dict(metadata or {})
        if expected_name_or_class and "app" not in meta:
            meta["app"] = expected_name_or_class
        resource = OwnedResource(
            task_id=task_id,
            resource_type=resource_type,
            launching_capability=capability,
            pid=new_pid,
            hwnd=new_hwnd,
            process_creation_time=proc_create_time,
            document_path=document_path,
            astra_created=astra_created,
            existed_before=not astra_created,
            cleanup_policy=cleanup_policy,
            content_classification=content_classification,
            lifecycle_state=ResourceLifecycleState.ACTIVE if astra_created else ResourceLifecycleState.DISCOVERED,
            metadata=meta,
        )
        self.register_resource(resource)
        logger.info(
            "[RESOURCE_REGISTERED] task_id=%s, type=%s, pid=%s, hwnd=%s, astra_created=%s, policy=%s",
            task_id, resource.resource_type.value, resource.pid, resource.hwnd, resource.astra_created, resource.cleanup_policy.value,
        )
        return resource

    # -------------------------------------------------------------------------
    # CRUD & State Updates
    # -------------------------------------------------------------------------

    def register_resource(self, resource: OwnedResource) -> None:
        """Insert or replace an OwnedResource in SQLite."""
        with self._lock:
            conn = self._get_connection()
            conn.execute("""
                INSERT OR REPLACE INTO owned_resources (
                    resource_id, task_id, resource_type, launching_capability,
                    pid, hwnd, process_creation_time, document_path,
                    astra_created, existed_before, cleanup_policy,
                    content_classification, lifecycle_state, user_interacted,
                    created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                resource.resource_id,
                resource.task_id,
                resource.resource_type.value if isinstance(resource.resource_type, ResourceType) else str(resource.resource_type),
                resource.launching_capability,
                resource.pid,
                resource.hwnd,
                resource.process_creation_time,
                resource.document_path,
                1 if resource.astra_created else 0,
                1 if resource.existed_before else 0,
                resource.cleanup_policy.value if isinstance(resource.cleanup_policy, CleanupPolicy) else str(resource.cleanup_policy),
                resource.content_classification.value if isinstance(resource.content_classification, ContentClassification) else str(resource.content_classification),
                resource.lifecycle_state.value if isinstance(resource.lifecycle_state, ResourceLifecycleState) else str(resource.lifecycle_state),
                1 if resource.user_interacted else 0,
                resource.created_at,
                time.time(),
                json.dumps(resource.metadata),
            ))
            conn.commit()

    def get_resource(self, resource_id: str) -> Optional[OwnedResource]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM owned_resources WHERE resource_id = ?;", (resource_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_resource(row)
            return None

    def list_resources_for_task(self, task_id: str) -> List[OwnedResource]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM owned_resources WHERE task_id = ? ORDER BY created_at ASC;", (task_id,))
            return [self._row_to_resource(r) for r in cursor.fetchall()]

    def list_active_astra_resources(self) -> List[OwnedResource]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT * FROM owned_resources
                WHERE astra_created = 1 AND lifecycle_state IN ('ACTIVE', 'LAUNCHED', 'SAVING', 'SAVED')
                ORDER BY created_at ASC;
            """)
            return [self._row_to_resource(r) for r in cursor.fetchall()]

    def get_resource_for_hwnd(self, hwnd: int) -> Optional[OwnedResource]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM owned_resources WHERE hwnd = ? AND lifecycle_state IN ('ACTIVE', 'LAUNCHED', 'SAVING', 'SAVED');", (hwnd,))
            row = cursor.fetchone()
            if row:
                return self._row_to_resource(row)
            return None

    def get_resource_for_pid(self, pid: int) -> Optional[OwnedResource]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM owned_resources WHERE pid = ? AND lifecycle_state IN ('ACTIVE', 'LAUNCHED', 'SAVING', 'SAVED');", (pid,))
            row = cursor.fetchone()
            if row:
                return self._row_to_resource(row)
            return None


    def update_lifecycle_state(
        self,
        resource_id: str,
        state: ResourceLifecycleState,
        metadata_updates: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT metadata FROM owned_resources WHERE resource_id = ?;", (resource_id,))
            row = cursor.fetchone()
            meta = {}
            if row and row["metadata"]:
                try:
                    meta = json.loads(row["metadata"])
                except Exception:
                    pass
            if metadata_updates:
                meta.update(metadata_updates)

            conn.execute("""
                UPDATE owned_resources
                SET lifecycle_state = ?, updated_at = ?, metadata = ?
                WHERE resource_id = ?;
            """, (state.value, time.time(), json.dumps(meta), resource_id))
            conn.commit()

    def _row_to_resource(self, row: sqlite3.Row) -> OwnedResource:
        meta = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except Exception:
                pass
        return OwnedResource(
            resource_id=row["resource_id"],
            task_id=row["task_id"],
            resource_type=ResourceType(row["resource_type"]),
            launching_capability=row["launching_capability"],
            pid=row["pid"],
            hwnd=row["hwnd"],
            process_creation_time=row["process_creation_time"],
            document_path=row["document_path"],
            astra_created=bool(row["astra_created"]),
            existed_before=bool(row["existed_before"]),
            cleanup_policy=CleanupPolicy(row["cleanup_policy"]),
            content_classification=ContentClassification(row["content_classification"]),
            lifecycle_state=ResourceLifecycleState(row["lifecycle_state"]),
            user_interacted=bool(row["user_interacted"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=meta,
        )

    # -------------------------------------------------------------------------
    # User Takeover & Detachment ("Do Not Fight The User")
    # -------------------------------------------------------------------------

    def mark_user_takeover_for_task(self, task_id: str) -> int:
        """Mark all active resources for a task as detached due to user intervention."""
        with self._lock:
            resources = self.list_resources_for_task(task_id)
            count = 0
            for r in resources:
                if r.lifecycle_state in (ResourceLifecycleState.ACTIVE, ResourceLifecycleState.LAUNCHED):
                    r.user_interacted = True
                    r.lifecycle_state = ResourceLifecycleState.USER_TAKEOVER_DETACHED
                    self.register_resource(r)
                    count += 1
                    logger.info(
                        "[USER_TAKEOVER_DETACHED] Resource %s (PID=%s, HWND=%s) detached from auto-cleanup.",
                        r.resource_id, r.pid, r.hwnd
                    )
            return count

    def mark_user_takeover_for_window(self, hwnd: int) -> Optional[OwnedResource]:
        """Detach a specific window when user focus or keyboard activity is detected on it."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM owned_resources WHERE hwnd = ? AND lifecycle_state IN ('ACTIVE', 'LAUNCHED');", (hwnd,))
            row = cursor.fetchone()
            if row:
                res = self._row_to_resource(row)
                res.user_interacted = True
                res.lifecycle_state = ResourceLifecycleState.USER_TAKEOVER_DETACHED
                self.register_resource(res)
                logger.info("[USER_TAKEOVER_DETACHED] Window HWND %s detached from auto-cleanup.", hwnd)
                return res
            return None

    # -------------------------------------------------------------------------
    # Targeted Cleanup Execution
    # -------------------------------------------------------------------------

    def close_owned_resource(
        self,
        resource: OwnedResource,
        force_timeout: float = 3.0,
    ) -> bool:
        """
        Target and close ONLY the specific Astra-owned resource.
        Guarantees:
        - Never closes pre-existing instances (astra_created == False).
        - Never closes windows where user intervention occurred (USER_TAKEOVER_DETACHED).
        - Verifies required artifact exists before closing if SAVE_BEFORE_CLOSE.
        - Validates process creation timestamp before termination to prevent PID reuse kills.
        """
        # 1. Critical Ownership Invariant Check
        if not resource.astra_created:
            logger.warning("[CLEANUP_SKIPPED] Resource %s was not created by Astra.", resource.resource_id)
            return False

        if resource.user_interacted or resource.lifecycle_state == ResourceLifecycleState.USER_TAKEOVER_DETACHED:
            logger.info("[CLEANUP_SKIPPED_USER_TAKEOVER] Resource %s retained (user intervened).", resource.resource_id)
            return False

        if resource.cleanup_policy == CleanupPolicy.NEVER_CLOSE:
            logger.info("[CLEANUP_SKIPPED_POLICY] Resource %s has NEVER_CLOSE policy.", resource.resource_id)
            return False

        self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.CLOSING)

        # 2. SAVE BEFORE CLOSE Verification
        if resource.cleanup_policy in (CleanupPolicy.SAVE_BEFORE_CLOSE, CleanupPolicy.PERSIST_ARTIFACT_THEN_CLOSE) or \
           resource.content_classification == ContentClassification.TASK_ARTIFACT:
            if resource.document_path:
                doc_path = Path(resource.document_path)
                if not doc_path.exists() or doc_path.stat().st_size == 0:
                    logger.warning("[SAVE_BEFORE_CLOSE_REQUIRED] Artifact '%s' is not verified on disk.", resource.document_path)
                    # Cannot safely mark closed if artifact persistence was required but missing
                    self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.ACTIVE)
                    return False
                logger.info("[ARTIFACT_PERSISTENCE_VERIFIED] '%s' verified before close.", resource.document_path)

        # 3. Graceful Window Closure via WM_CLOSE
        user32 = ctypes.windll.user32 if sys.platform == "win32" else None
        window_closed = False

        if user32:
            _ensure_desktop_attached()
            # If HWND is missing, attempt to dynamically discover it from PID
            if not resource.hwnd and resource.pid:
                from ctypes import wintypes
                def find_cb(h: int, l: int) -> bool:
                    if user32.IsWindowVisible(h):
                        pbuf = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(h, ctypes.byref(pbuf))
                        if pbuf.value == resource.pid:
                            resource.hwnd = h
                            return False
                    return True
                WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                user32.EnumWindows(WNDENUMPROC(find_cb), 0)

            if resource.hwnd:
                try:
                    if user32.IsWindow(resource.hwnd):
                        logger.info("[WM_CLOSE_SENT] Closing HWND %d (PID=%s)", resource.hwnd, resource.pid)
                        user32.PostMessageW(resource.hwnd, WM_CLOSE, 0, 0)

                        # Wait up to 2 seconds for window to disappear
                        deadline = time.time() + 2.0
                        while time.time() < deadline:
                            time.sleep(0.1)
                            if not user32.IsWindow(resource.hwnd):
                                window_closed = True
                                break

                        # Fallback: WM_SYSCOMMAND / SC_CLOSE
                        if not window_closed and user32.IsWindow(resource.hwnd):
                            user32.PostMessageW(resource.hwnd, WM_SYSCOMMAND, SC_CLOSE, 0)
                            time.sleep(0.3)
                            if not user32.IsWindow(resource.hwnd):
                                window_closed = True

                        # Handle unexpected Save/Don't Save dialog if still visible
                        if not window_closed and user32.IsWindow(resource.hwnd):
                            self._handle_unexpected_save_dialog(resource)
                            time.sleep(0.3)
                            if not user32.IsWindow(resource.hwnd):
                                window_closed = True
                            else:
                                self._handle_unexpected_save_dialog(resource)
                                time.sleep(0.3)
                                if not user32.IsWindow(resource.hwnd):
                                    window_closed = True
                except Exception as e:
                    logger.warning("Error posting WM_CLOSE to HWND %s: %s", resource.hwnd, e)

        # 4. Process Termination with PID Reuse Protection
        if resource.pid:
            try:
                if psutil.pid_exists(resource.pid):
                    proc = psutil.Process(resource.pid)
                    # Critical PID reuse guard: verify process creation time matches!
                    if resource.process_creation_time is not None:
                        curr_create_time = proc.create_time()
                        if abs(curr_create_time - resource.process_creation_time) > 2.0:
                            logger.error(
                                "[PID_REUSE_DETECTED] PID %d create_time %.2f != recorded %.2f. ABORTING TERMINATION.",
                                resource.pid, curr_create_time, resource.process_creation_time
                            )
                            self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.STALE_REUSED)
                            return False

                    # Check if process has OTHER visible windows (shared multi-window host like modern Notepad)
                    other_windows_exist = False
                    if user32:
                        _ensure_desktop_attached()
                        from ctypes import wintypes
                        def check_cb(h: int, l: int) -> bool:
                            nonlocal other_windows_exist
                            if h != resource.hwnd and user32.IsWindowVisible(h):
                                p_buf = wintypes.DWORD()
                                user32.GetWindowThreadProcessId(h, ctypes.byref(p_buf))
                                if p_buf.value == resource.pid:
                                    other_windows_exist = True
                                    return False
                            return True
                        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                        user32.EnumWindows(WNDENUMPROC(check_cb), 0)

                    if other_windows_exist:
                        logger.info(
                            "[PRESERVING_SHARED_PROCESS] PID %d has other active windows. Skipping process termination.",
                            resource.pid
                        )
                    else:
                        proc_name = (proc.name() or "").lower()
                        if proc_name not in ("explorer.exe", "applicationframehost.exe"):
                            logger.info("[TERMINATING_OWNED_PROCESS] PID %d (%s)", resource.pid, proc_name)
                            proc.terminate()
                            try:
                                proc.wait(timeout=force_timeout)
                            except psutil.TimeoutExpired:
                                proc.kill()
                                proc.wait(timeout=1.0)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Clean Notepad TabState files if temporary test document to prevent modal orphans
        if resource.document_path and resource.content_classification == ContentClassification.TEMPORARY_TEST_CONTENT:
            clean_notepad_tabstate_for_path(resource.document_path)

        self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.CLOSED)
        logger.info("[RESOURCE_CLEANED] Successfully cleaned up resource %s", resource.resource_id)
        return True


    def _handle_unexpected_save_dialog(self, resource: OwnedResource) -> None:
        """Inspect and handle any Save/Don't Save dialog presented upon WM_CLOSE."""
        if sys.platform != "win32":
            return
        try:
            _ensure_desktop_attached()
            from astrarun.interaction.discovery import inspect_window_ui
            from astrarun.interaction.controller import invoke_element
            elements = inspect_window_ui(resource.hwnd or 0, max_depth=5)
            # Phase 1: Look for modal dialog response buttons (Don't Save, Discard, OK, Cancel)
            for el in elements:
                name_lower = el.name.lower()
                if el.control_type.name == "BUTTON":
                    if any(s in name_lower for s in ("don't save", "dont save", "discard", "no")):
                        logger.info("[DIALOG_HANDLED] Clicking 'Don't Save' to dismiss prompt.")
                        invoke_element(el)
                        return
                    if resource.content_classification == ContentClassification.TASK_ARTIFACT and name_lower in ("save", "yes"):
                        logger.info("[DIALOG_HANDLED] Clicking 'Save' for task artifact.")
                        invoke_element(el)
                        return
                    if name_lower in ("ok", "cancel") and ("popup" in el.class_name.lower() or "dialog" in el.class_name.lower()):
                        logger.info("[DIALOG_HANDLED] Dismissing alert dialog via '%s'.", el.name)
                        invoke_element(el)
                        return

            # Phase 2: If no dialog button found, click UI Close button on window caption
            for el in elements:
                name_lower = el.name.lower()
                if el.control_type.name == "BUTTON":
                    if name_lower == "close" or ("close" in name_lower and ("calculator" in name_lower or "window" in name_lower or "notepad" in name_lower)):
                        logger.info("[DIALOG_HANDLED] Clicking UI close button '%s'.", el.name)
                        invoke_element(el)
                        return
        except Exception as err:
            logger.debug("Failed inspecting save dialog: %s", err)

    def cleanup_task_resources(
        self,
        task_id: str,
        task_status: Any,
    ) -> Dict[str, Any]:
        """
        Execute deterministic cleanup for all resources owned by task_id.
        Applies try/finally semantics across SUCCESS, FAILURE, USER_CANCEL, and TIMEOUT.
        """
        resources = self.list_resources_for_task(task_id)
        cleaned_count = 0
        preserved_count = 0
        detached_count = 0

        status_str = getattr(task_status, "value", str(task_status)).upper()
        is_success = status_str in ("COMPLETED", "SUCCESS")

        logger.info(
            "[TASK_CLEANUP_STARTED] task_id=%s, status=%s, total_resources=%d",
            task_id, status_str, len(resources)
        )

        for res in resources:
            if res.lifecycle_state in (ResourceLifecycleState.CLOSED, ResourceLifecycleState.ORPHANED_CLEANED):
                continue

            if res.user_interacted or res.lifecycle_state == ResourceLifecycleState.USER_TAKEOVER_DETACHED:
                detached_count += 1
                continue

            # Policy checks on failure/cancellation
            if not is_success:
                if res.cleanup_policy == CleanupPolicy.PRESERVE_ON_FAILURE:
                    logger.info("[RESOURCE_PRESERVED_ON_FAILURE] %s preserved for analysis.", res.resource_id)
                    preserved_count += 1
                    continue
                if res.content_classification == ContentClassification.TASK_ARTIFACT:
                    # Do not discard valuable partially created user work on unexpected failure
                    logger.info("[RESOURCE_PRESERVED_ARTIFACT] %s preserved due to TASK_ARTIFACT content.", res.resource_id)
                    preserved_count += 1
                    continue

            # Execute targeted closure
            ok = self.close_owned_resource(res)
            if ok:
                cleaned_count += 1
            else:
                preserved_count += 1

        logger.info(
            "[TASK_CLEANUP_COMPLETED] task_id=%s: cleaned=%d, preserved=%d, detached=%d",
            task_id, cleaned_count, preserved_count, detached_count
        )
        return {
            "task_id": task_id,
            "cleaned_count": cleaned_count,
            "preserved_count": preserved_count,
            "detached_count": detached_count,
        }

    # -------------------------------------------------------------------------
    # Crash / Restart Orphan Recovery
    # -------------------------------------------------------------------------

    def recover_orphaned_resources(self) -> List[Dict[str, Any]]:
        """
        Recover potentially orphaned Astra-created resources after a crash/restart.
        Validates PID existence and PID creation time to strictly eliminate PID reuse hazards.
        """
        active_resources = self.list_active_astra_resources()
        recovery_results = []

        logger.info("[ORPHAN_RECOVERY_STARTED] Found %d active Astra resources.", len(active_resources))

        for res in active_resources:
            # If HWND is recorded on Windows, verify whether the window is still open
            window_alive = False
            user32 = ctypes.windll.user32 if sys.platform == "win32" else None
            if user32 and res.hwnd:
                try:
                    if user32.IsWindow(res.hwnd):
                        window_alive = True
                        pbuf = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(res.hwnd, ctypes.byref(pbuf))
                        if pbuf.value and psutil.pid_exists(pbuf.value):
                            res.pid = pbuf.value
                            try:
                                res.process_creation_time = psutil.Process(res.pid).create_time()
                            except Exception:
                                pass
                except Exception:
                    pass

            # If neither window nor PID is alive, mark CLOSED
            if not window_alive and (not res.pid or not psutil.pid_exists(res.pid)):
                self.update_lifecycle_state(res.resource_id, ResourceLifecycleState.CLOSED)
                recovery_results.append({"resource_id": res.resource_id, "action": "CLOSED_NOT_FOUND"})
                continue

            try:
                proc = psutil.Process(res.pid)
                curr_create_time = proc.create_time()

                # Strict PID reuse check
                if res.process_creation_time and abs(curr_create_time - res.process_creation_time) > 2.0:
                    logger.warning(
                        "[ORPHAN_RECOVERY_PID_REUSE] PID %d has new create_time %.2f. Skipping kill.",
                        res.pid, curr_create_time
                    )
                    self.update_lifecycle_state(res.resource_id, ResourceLifecycleState.STALE_REUSED)
                    recovery_results.append({"resource_id": res.resource_id, "action": "STALE_REUSED"})
                    continue

                # Process identity is verified!
                # If resource was temporary test content, clean it up
                if res.content_classification == ContentClassification.TEMPORARY_TEST_CONTENT:
                    self.close_owned_resource(res)
                    self.update_lifecycle_state(res.resource_id, ResourceLifecycleState.ORPHANED_CLEANED)
                    recovery_results.append({"resource_id": res.resource_id, "action": "ORPHANED_CLEANED"})
                else:
                    logger.info("[ORPHAN_RETAINED] Retaining resource %s (content=%s)", res.resource_id, res.content_classification.value)
                    recovery_results.append({"resource_id": res.resource_id, "action": "RETAINED"})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.update_lifecycle_state(res.resource_id, ResourceLifecycleState.CLOSED)
                recovery_results.append({"resource_id": res.resource_id, "action": "CLOSED_VANISHED"})

        logger.info("[ORPHAN_RECOVERY_COMPLETED] Processed %d resources.", len(recovery_results))
        return recovery_results
