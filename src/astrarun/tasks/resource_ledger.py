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
        hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)

        h_desk = user32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId())
        if h_desk:
            buf_desk = ctypes.create_unicode_buffer(256)
            if user32.GetUserObjectInformationW(h_desk, 2, buf_desk, 256, None) and buf_desk.value.lower() == "default":
                return

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
    SANDBOX_DIR = "SANDBOX_DIR"
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
    NOT_MATERIALIZED = "NOT_MATERIALIZED"
    INVALID_IDENTITY = "INVALID_IDENTITY"


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
    parent_pid: Optional[int] = None
    creator_action: Optional[str] = None
    ownership_class: str = "ASTRA_CREATED"
    executable_path: Optional[str] = None
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

    @property
    def create_time(self) -> Optional[float]:
        return self.process_creation_time if self.process_creation_time is not None else self.created_at

    @create_time.setter
    def create_time(self, val: Optional[float]) -> None:
        self.process_creation_time = val

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "task_id": self.task_id,
            "resource_type": self.resource_type.value if isinstance(self.resource_type, ResourceType) else str(self.resource_type),
            "launching_capability": self.launching_capability,
            "pid": self.pid,
            "hwnd": self.hwnd,
            "process_creation_time": self.process_creation_time,
            "create_time": self.create_time,
            "parent_pid": self.parent_pid,
            "creator_action": self.creator_action,
            "ownership_class": self.ownership_class,
            "executable_path": self.executable_path,
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
            process_creation_time=d.get("process_creation_time", d.get("create_time")),
            parent_pid=d.get("parent_pid"),
            creator_action=d.get("creator_action"),
            ownership_class=d.get("ownership_class", "ASTRA_CREATED"),
            executable_path=d.get("executable_path"),
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

                candidates_for_pid = []
                for h, (w_pid, w_title, w_cls) in current_hwnds.items():
                    if h not in pre_snapshot.hwnds:
                        title_lower = w_title.lower()
                        cls_lower = w_cls.lower()
                        # Exclude system overlays / tooltips / message helpers
                        if any(x in cls_lower for x in ("uac_inputindicator", "touch tooltip", "tooltips_class32", "cicloaderwndclass")):
                            continue
                        owner = user32.GetWindow(h, 4) if sys.platform == "win32" else 0
                        if new_pid and w_pid == new_pid:
                            candidates_for_pid.append((h, w_pid, w_title, w_cls, owner))
                        elif aliases and any(a in title_lower or a in cls_lower for a in aliases):
                            candidates_for_pid.append((h, w_pid, w_title, w_cls, owner))

                if candidates_for_pid:
                    # Score and rank candidates: prioritize unowned top-level windows with non-empty titles
                    def _rank(cand):
                        c_h, c_pid, c_t, c_cls, c_owner = cand
                        score = 0
                        if c_t.strip():
                            score += 15
                        if c_owner == 0:
                            score += 10
                        if aliases and any(a in c_t.lower() or a in c_cls.lower() for a in aliases):
                            score += 25
                        if new_pid and c_pid == new_pid:
                            score += 20
                        return score

                    candidates_for_pid.sort(key=_rank, reverse=True)
                    best_h, best_pid, _, _, _ = candidates_for_pid[0]
                    new_hwnd = best_h
                    if not new_pid:
                        new_pid = best_pid
                        try:
                            proc_create_time = psutil.Process(best_pid).create_time()
                        except Exception:
                            pass

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
        if not new_hwnd and sys.platform == "win32" and current_hwnds:
            fallback_cands = []
            for h, (w_pid, w_title, w_cls) in current_hwnds.items():
                if h not in pre_snapshot.hwnds:
                    cls_low = w_cls.lower()
                    if any(x in cls_low for x in ("uac_inputindicator", "touch tooltip", "tooltips_class32", "cicloaderwndclass")):
                        continue
                    owner = user32.GetWindow(h, 4)
                    fallback_cands.append((h, w_pid, w_title, w_cls, owner))
            if fallback_cands:
                fallback_cands.sort(key=lambda c: (bool(c[2].strip()), c[4] == 0), reverse=True)
                new_hwnd = fallback_cands[0][0]
                if not new_pid:
                    new_pid = fallback_cands[0][1]

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

        # If new_pid is missing or already dead (e.g. calc.exe launched CalculatorApp.exe), resolve newly spawned matching process
        if (not new_pid or not psutil.pid_exists(new_pid)) and aliases:
            for p in psutil.process_iter(["name", "create_time"]):
                try:
                    c_time = p.info["create_time"] or 0.0
                    p_name = (p.info["name"] or "").lower()
                    is_new = (p.pid not in pre_snapshot.pids) or (c_time >= pre_snapshot.timestamp - 0.25)
                    if is_new and any(a in p_name for a in aliases):
                        new_pid = p.pid
                        proc_create_time = c_time
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # If a new process or window was identified, create registered OwnedResource
        astra_created = bool(new_pid or new_hwnd)
        meta = dict(metadata or {})
        if expected_name_or_class and "app" not in meta:
            meta["app"] = expected_name_or_class
        pid_in_pre = bool(new_pid and (new_pid in pre_snapshot.pids))
        existed_before = pid_in_pre or (not astra_created)
        resource = OwnedResource(
            task_id=task_id,
            resource_type=resource_type,
            launching_capability=capability,
            pid=new_pid,
            hwnd=new_hwnd,
            process_creation_time=proc_create_time,
            document_path=document_path,
            astra_created=astra_created,
            existed_before=existed_before,
            cleanup_policy=cleanup_policy,
            content_classification=content_classification,
            lifecycle_state=ResourceLifecycleState.ACTIVE if astra_created else ResourceLifecycleState.DISCOVERED,
            metadata=meta,
        )
        self.register_resource(resource)
        logger.info(
            "[RESOURCE_REGISTERED] task_id=%s, type=%s, pid=%s, hwnd=%s, astra_created=%s, existed_before=%s, policy=%s",
            task_id, resource.resource_type.value, resource.pid, resource.hwnd, resource.astra_created, resource.existed_before, resource.cleanup_policy.value,
        )
        try:
            from astrarun.core.telemetry import CausalTelemetry, CausalEventType
            telem = CausalTelemetry.get_instance()
            telem.emit(
                event_type=CausalEventType.RESOURCE_REGISTERED.value,
                component="AstraResourceLedger",
                task_id=task_id,
                data={
                    "resource_id": resource.resource_id,
                    "resource_type": resource.resource_type.value,
                    "pid": resource.pid,
                    "hwnd": resource.hwnd,
                    "astra_created": resource.astra_created,
                    "existed_before": resource.existed_before,
                    "cleanup_policy": resource.cleanup_policy.value,
                },
            )
        except Exception:
            pass
        return resource

    # -------------------------------------------------------------------------
    # CRUD & State Updates
    # -------------------------------------------------------------------------

    def register_resource(self, resource: OwnedResource) -> None:
        """Insert or replace an OwnedResource in SQLite."""
        if resource.pid and psutil.pid_exists(resource.pid):
            try:
                proc = psutil.Process(resource.pid)
                if resource.process_creation_time is None:
                    resource.process_creation_time = proc.create_time()
                if resource.parent_pid is None:
                    try:
                        resource.parent_pid = proc.ppid()
                    except Exception:
                        pass
                if resource.executable_path is None:
                    try:
                        resource.executable_path = proc.exe()
                    except Exception:
                        pass
            except Exception:
                pass

        resource.metadata["parent_pid"] = resource.parent_pid
        resource.metadata["creator_action"] = resource.creator_action
        resource.metadata["ownership_class"] = resource.ownership_class
        resource.metadata["executable_path"] = resource.executable_path
        resource.metadata["create_time"] = resource.create_time

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

        try:
            from astrarun.core.telemetry import CausalTelemetry, CausalEventType
            telem = CausalTelemetry.get_instance()
            telem.emit(
                event_type=CausalEventType.RESOURCE_REGISTERED.value,
                component="AstraResourceLedger",
                task_id=resource.task_id,
                data={
                    "resource_id": resource.resource_id,
                    "resource_type": resource.resource_type.value if isinstance(resource.resource_type, ResourceType) else str(resource.resource_type),
                    "pid": resource.pid,
                    "hwnd": resource.hwnd,
                    "document_path": resource.document_path,
                },
            )
        except Exception:
            pass

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

        # Concrete Identity Check: Empty, None, or whitespace-only paths/identities cannot pass vacuously
        has_identity = bool(resource.pid or resource.hwnd or (resource.document_path and str(resource.document_path).strip()))
        if not has_identity:
            logger.warning("[RESOURCE_NOT_MATERIALIZED] Resource %s has no concrete PID, HWND, or path.", resource.resource_id)
            self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.NOT_MATERIALIZED)
            return False

        if resource.resource_type in (ResourceType.SANDBOX_DIR, ResourceType.DOCUMENT):
            if not resource.document_path or not str(resource.document_path).strip():
                logger.warning("[RESOURCE_NOT_MATERIALIZED] Empty or None path for resource %s", resource.resource_id)
                self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.NOT_MATERIALIZED)
                return False
            try:
                sb_path = Path(resource.document_path)
            except Exception:
                self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.INVALID_IDENTITY)
                return False

            if not sb_path.exists():
                logger.warning("[RESOURCE_NOT_MATERIALIZED] Path %s does not exist on disk prior to cleanup.", resource.document_path)
                self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.NOT_MATERIALIZED)
                return False

        self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.CLOSING)

        # Handle SANDBOX_DIR explicitly
        if resource.resource_type == ResourceType.SANDBOX_DIR:
            if resource.cleanup_policy == CleanupPolicy.PRESERVE_ON_FAILURE:
                logger.info("[CLEANUP_SKIPPED_PRESERVE] Sandbox directory %s preserved.", resource.document_path)
                self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.SAVED)
                return True
            sb_path = Path(resource.document_path)
            if sb_path.exists():
                try:
                    import shutil
                    shutil.rmtree(sb_path, ignore_errors=True)
                    logger.info("[SANDBOX_DIR_REMOVED] %s", resource.document_path)
                except Exception as e:
                    logger.warning("Error removing sandbox dir %s: %s", resource.document_path, e)

            # Physical post-cleanup verification: require physical absence on disk
            if sb_path.exists():
                logger.error("[RESOURCE_DISPOSAL_FAILED] Path %s still exists on disk after deletion attempt.", resource.document_path)
                self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.FAILED_CLEANUP)
                return False

            self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.CLOSED)
            try:
                from astrarun.core.telemetry import CausalTelemetry, CausalEventType
                telem = CausalTelemetry.get_instance()
                telem.emit(
                    event_type=CausalEventType.RESOURCE_DISPOSED.value,
                    component="AstraResourceLedger",
                    task_id=resource.task_id,
                    data={
                        "resource_id": resource.resource_id,
                        "resource_type": resource.resource_type.value,
                        "path": resource.document_path,
                        "state": "CLOSED",
                    },
                )
            except Exception:
                pass
            return True

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

                    proc_name = (proc.name() or "").lower()
                    proc_created_by_astra = resource.astra_created and (not resource.existed_before)

                    if proc_created_by_astra and proc_name not in ("explorer.exe", "applicationframehost.exe"):
                        # Grace period: check if process exited cleanly after window close
                        try:
                            proc.wait(timeout=0.6)
                        except (psutil.TimeoutExpired, psutil.NoSuchProcess):
                            pass

                        # If still alive, terminate the task-created process and its children
                        if psutil.pid_exists(resource.pid):
                            logger.info("[TERMINATING_OWNED_PROCESS] PID %d (%s)", resource.pid, proc_name)
                            children = []
                            try:
                                children = proc.children(recursive=True)
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass

                            for child in children:
                                try:
                                    child.terminate()
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass

                            proc.terminate()
                            procs_to_wait = children + [proc]
                            gone, alive = psutil.wait_procs(procs_to_wait, timeout=force_timeout)
                            for p in alive:
                                try:
                                    p.kill()
                                    p.wait(timeout=1.0)
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass
                    else:
                        logger.info(
                            "[PRESERVING_PROCESS] PID %d (%s) was not uniquely created by Astra or is a shell host.",
                            resource.pid, proc_name
                        )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Clean Notepad TabState files if temporary/test document to prevent modal orphans
        if resource.document_path:
            clean_notepad_tabstate_for_path(resource.document_path)

        # Post-close verification: do not claim CLOSED while process/window remains.
        # For system shells or pre-existing processes, process staying alive is expected.
        proc_expected_terminated = resource.astra_created and (not resource.existed_before)
        process_still_alive = bool(resource.pid and psutil.pid_exists(resource.pid)) if proc_expected_terminated else False
        window_still_alive = False
        if user32 and resource.hwnd:
            try:
                window_still_alive = bool(user32.IsWindow(resource.hwnd))
            except Exception:
                window_still_alive = False

        disk_resource_still_alive = False
        if resource.document_path and (resource.resource_type == ResourceType.SANDBOX_DIR or resource.content_classification == ContentClassification.TEMPORARY_TEST_CONTENT):
            try:
                if Path(resource.document_path).exists():
                    disk_resource_still_alive = True
            except Exception:
                pass

        if process_still_alive or window_still_alive or disk_resource_still_alive:
            self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.FAILED_CLEANUP)
            logger.warning(
                "[RESOURCE_CLEAN_FAILED] Resource %s still live (process_alive=%s, window_alive=%s, disk_alive=%s)",
                resource.resource_id, process_still_alive, window_still_alive, disk_resource_still_alive
            )
            return False

        self.update_lifecycle_state(resource.resource_id, ResourceLifecycleState.CLOSED)
        logger.info("[RESOURCE_CLEANED] Successfully cleaned up resource %s", resource.resource_id)
        try:
            from astrarun.core.telemetry import CausalTelemetry, CausalEventType
            telem = CausalTelemetry.get_instance()
            telem.emit(
                event_type=CausalEventType.RESOURCE_DISPOSED.value,
                component="AstraResourceLedger",
                task_id=resource.task_id,
                data={
                    "resource_id": resource.resource_id,
                    "resource_type": resource.resource_type.value,
                    "pid": resource.pid,
                    "hwnd": resource.hwnd,
                    "state": "CLOSED",
                },
            )
        except Exception:
            pass
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
                auto_id_l = (getattr(el, "automation_id", "") or "").lower()
                if el.control_type.name == "BUTTON":
                    if name_lower == "close" or auto_id_l == "close" or name_lower.startswith("close"):
                        logger.info("[DIALOG_HANDLED] Clicking UI close button '%s'.", el.name)
                        invoke_element(el)
                        return
        except Exception as err:
            logger.debug("Failed inspecting save dialog: %s", err)

    def cleanup_task_resources(
        self,
        task_id: str,
        task_status: Any = "COMPLETED",
    ) -> Dict[str, Any]:
        """
        Execute deterministic cleanup for all resources owned by task_id.
        Applies try/finally semantics across SUCCESS, FAILURE, USER_CANCEL, and TIMEOUT.

        Returns a truthful report. PASS_CLEAN is only implied when process_cleaned_up
        is True (or there was never a task-owned process) and no cleanup exception occurred.
        """
        resources = self.list_resources_for_task(task_id)
        cleaned_count = 0
        preserved_count = 0
        detached_count = 0
        failed_count = 0
        cleanup_exception: Optional[str] = None
        had_task_owned_process = any(bool(r.pid) for r in resources)
        remaining_active = 0
        process_cleaned_up = True

        status_str = getattr(task_status, "value", str(task_status)).upper()
        is_success = status_str in ("COMPLETED", "SUCCESS")

        logger.info(
            "[TASK_CLEANUP_STARTED] task_id=%s, status=%s, total_resources=%d",
            task_id, status_str, len(resources)
        )

        try:
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
                try:
                    ok = self.close_owned_resource(res)
                except Exception as close_err:
                    cleanup_exception = str(close_err)
                    failed_count += 1
                    continue
                if ok:
                    cleaned_count += 1
                else:
                    failed_count += 1
                    if res.pid and psutil.pid_exists(res.pid):
                        process_cleaned_up = False
                    if res.hwnd:
                        try:
                            if sys.platform == "win32" and ctypes.windll.user32.IsWindow(res.hwnd):
                                process_cleaned_up = False
                        except Exception:
                            process_cleaned_up = False

            for res in self.list_resources_for_task(task_id):
                if res.lifecycle_state not in (
                    ResourceLifecycleState.CLOSED,
                    ResourceLifecycleState.ORPHANED_CLEANED,
                    ResourceLifecycleState.STALE_REUSED,
                    ResourceLifecycleState.USER_TAKEOVER_DETACHED,
                ):
                    if res.user_interacted:
                        continue
                    remaining_active += 1
                    if res.pid and psutil.pid_exists(res.pid):
                        process_cleaned_up = False
        except Exception as err:
            cleanup_exception = str(err)
            process_cleaned_up = False

        # No task-owned process => process lifecycle is vacuously clean.
        if not had_task_owned_process and process_cleaned_up:
            process_cleaned_up = True

        clean_ok = (
            cleanup_exception is None
            and remaining_active == 0
            and process_cleaned_up
            and failed_count == 0
        )

        orphaned_processes = 0 if process_cleaned_up else 1
        orphaned_windows = 0 if remaining_active == 0 else remaining_active

        logger.info(
            "[TASK_CLEANUP_COMPLETED] task_id=%s: cleaned=%d, preserved=%d, detached=%d, "
            "failed=%d, remaining_active=%d, process_cleaned_up=%s, exception=%s",
            task_id, cleaned_count, preserved_count, detached_count,
            failed_count, remaining_active, process_cleaned_up, cleanup_exception
        )
        try:
            if clean_ok:
                from astrarun.core.telemetry import CausalTelemetry, CausalEventType
                telem = CausalTelemetry.get_instance()
                telem.emit(
                    event_type=CausalEventType.RESOURCE_RESTORATION_VERIFIED.value,
                    component="AstraResourceLedger",
                    task_id=task_id,
                    data={
                        "cleaned_count": cleaned_count,
                        "preserved_count": preserved_count,
                        "detached_count": detached_count,
                        "failed_count": failed_count,
                        "clean_ok": True,
                        "process_cleaned_up": process_cleaned_up,
                        "remaining_active": remaining_active,
                    },
                )
            else:
                logger.warning(
                    "[RESOURCE_RESTORATION_UNVERIFIED] task_id=%s restoration could not be verified (clean_ok=False)",
                    task_id
                )
        except Exception:
            pass
        return {
            "task_id": task_id,
            "cleaned_count": cleaned_count,
            "preserved_count": preserved_count,
            "detached_count": detached_count,
            "failed_count": failed_count,
            "remaining_active_resources": remaining_active,
            # Affirmative ownership/lifecycle measurements for fail-closed oracle use.
            "resources_owned": bool(resources),
            "process_cleanup_required": had_task_owned_process,
            "process_residue_measured": True,
            "window_residue_measured": True,
            "ledger_residue_measured": True,
            "process_cleaned_up": process_cleaned_up,
            "cleanup_executed": True,
            "cleanup_exception": cleanup_exception,
            "orphaned_processes": orphaned_processes,
            "orphaned_windows": orphaned_windows,
            "active_ledger_resources": remaining_active,
            "clean": clean_ok,
            "verdict": "PASS_CLEAN" if clean_ok else "FAIL",
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
                should_cleanup = (
                    res.content_classification == ContentClassification.TEMPORARY_TEST_CONTENT
                    or res.cleanup_policy == CleanupPolicy.AUTO_CLOSE_ON_COMPLETION
                )
                if should_cleanup:
                    self.close_owned_resource(res)
                    self.update_lifecycle_state(res.resource_id, ResourceLifecycleState.ORPHANED_CLEANED)
                    recovery_results.append({"resource_id": res.resource_id, "action": "ORPHANED_CLEANED"})
                else:
                    logger.info("[ORPHAN_RETAINED] Retaining resource %s (content=%s, policy=%s)", res.resource_id, res.content_classification.value, res.cleanup_policy.value)
                    recovery_results.append({"resource_id": res.resource_id, "action": "RETAINED"})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.update_lifecycle_state(res.resource_id, ResourceLifecycleState.CLOSED)
                recovery_results.append({"resource_id": res.resource_id, "action": "CLOSED_VANISHED"})

        logger.info("[ORPHAN_RECOVERY_COMPLETED] Processed %d resources.", len(recovery_results))
        return recovery_results
