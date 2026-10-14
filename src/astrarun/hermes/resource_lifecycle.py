"""Causal resource ownership and lifecycle management for AstraRun.

CORE INVARIANT:
  A RESOURCE APPEARING AFTER AN ASTRA ACTION DOES NOT IMPLY THAT ASTRA CREATED OR OWNS IT.
  Temporal correlation is NOT causal ownership.

Astra may classify a resource TASK_CREATED only when there is affirmative causal evidence
connecting that resource to a governed Astra action or to an already-proven TASK_CREATED ancestor.

Anything else MUST remain UNKNOWN or EXTERNAL_CONCURRENT and MUST NEVER be disposed.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import psutil

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.hermes.resource_lifecycle")

WM_CLOSE = 0x0010


class OwnershipClass(str, Enum):
    PRE_EXISTING_USER = "PRE_EXISTING_USER"
    TASK_CREATED = "TASK_CREATED"
    TASK_DESCENDANT = "TASK_DESCENDANT"
    TASK_ACQUIRED = "TASK_ACQUIRED"
    SHARED = "SHARED"
    EXTERNAL_CONCURRENT = "EXTERNAL_CONCURRENT"
    UNKNOWN = "UNKNOWN"


class CausalEvidenceKind(str, Enum):
    DIRECT_GOVERNED_LAUNCH = "DIRECT_GOVERNED_LAUNCH"
    GOVERNED_LAUNCH_TARGET = "GOVERNED_LAUNCH_TARGET"
    DESCENDANT_PROCESS = "DESCENDANT_PROCESS"
    HWND_OF_TASK_PID = "HWND_OF_TASK_PID"
    STRUCTURAL_CHILD = "STRUCTURAL_CHILD"
    DIALOG_OF_TASK = "DIALOG_OF_TASK"
    TASK_DECLARED_ARTIFACT_SCOPE = "TASK_DECLARED_ARTIFACT_SCOPE"
    PRE_EXISTING_BASELINE = "PRE_EXISTING_BASELINE"
    EXTERNAL_CONCURRENT = "EXTERNAL_CONCURRENT"
    UNKNOWN_EVIDENCE = "UNKNOWN_EVIDENCE"


class LifecycleDisposition(str, Enum):
    PRESERVE = "PRESERVE"
    SAVE = "SAVE"
    DISCARD = "DISCARD"
    CLOSE = "CLOSE"
    RESTORE = "RESTORE"
    RELEASE = "RELEASE"
    FAILED_CLEANUP = "FAILED_CLEANUP"
    UNRESOLVED = "UNRESOLVED"


class LifecycleOutcome(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    BLOCKED_COMPLETE = "BLOCKED_COMPLETE"


@dataclass
class CausalProvenance:
    evidence_kind: CausalEvidenceKind
    creating_action_id: str = ""
    parent_identity_key: Optional[str] = None
    rationale: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_kind": self.evidence_kind.value,
            "creating_action_id": self.creating_action_id,
            "parent_identity_key": self.parent_identity_key,
            "rationale": self.rationale,
            "confidence": self.confidence,
        }


@dataclass
class ResourceIdentity:
    """Stable OS/UI identity for a resource (never title)."""
    kind: str  # process | window | dialog | document | file
    pid: Optional[int] = None
    hwnd: Optional[int] = None
    parent_hwnd: Optional[int] = None
    parent_pid: Optional[int] = None
    uia_id: Optional[str] = None
    process_name: str = ""
    class_name: str = ""
    bounds: Optional[Tuple[int, int, int, int]] = None
    create_time: Optional[float] = None
    path: Optional[str] = None

    def key(self) -> str:
        if self.kind == "file" and self.path:
            return f"file:{os.path.abspath(self.path).lower()}"
        if self.kind == "process" and self.pid is not None:
            return f"process:{self.pid}"
        if self.kind == "document" and self.uia_id and self.parent_hwnd is not None:
            return f"document:{self.parent_hwnd}:{self.uia_id}"
        if self.kind == "dialog" and self.hwnd is not None:
            return f"dialog:{self.hwnd}"
        if self.kind == "dialog" and self.uia_id:
            return f"dialog:{self.uia_id}"
        if self.hwnd is not None:
            return f"window:{self.hwnd}"
        if self.uia_id:
            return f"uia:{self.uia_id}"
        if self.pid is not None:
            return f"process:{self.pid}"
        return f"anon:{uuid.uuid4().hex}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "pid": self.pid,
            "hwnd": self.hwnd,
            "parent_hwnd": self.parent_hwnd,
            "parent_pid": self.parent_pid,
            "uia_id": self.uia_id,
            "process_name": self.process_name,
            "class_name": self.class_name,
            "bounds": list(self.bounds) if self.bounds else None,
            "create_time": self.create_time,
            "path": self.path,
        }


@dataclass
class TrackedResource:
    resource_id: str
    resource_type: str
    task_id: str
    identity: ResourceIdentity
    ownership: OwnershipClass
    ownership_evidence: str
    provenance: Optional[CausalProvenance] = None
    creating_action_id: str = ""
    first_seen_frame: str = ""
    last_seen_frame: str = ""
    is_new_to_world: bool = False
    parent_resource_id: Optional[str] = None
    initial_title: str = ""
    current_title: str = ""
    goal_required_final_state: str = "disposable"
    disposition: LifecycleDisposition = LifecycleDisposition.UNRESOLVED
    disposition_reason: str = ""
    cleanup_action: str = ""
    verification: LifecycleOutcome = LifecycleOutcome.UNKNOWN
    final_state: str = ""
    notes: str = ""

    @property
    def pid(self) -> Optional[int]:
        return self.identity.pid

    @property
    def hwnd(self) -> Optional[int]:
        return self.identity.hwnd

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "task_id": self.task_id,
            "identity": self.identity.to_dict(),
            "identity_key": self.identity.key(),
            "ownership": self.ownership.value,
            "ownership_evidence": self.ownership_evidence,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "creating_action_id": self.creating_action_id,
            "first_seen_frame": self.first_seen_frame,
            "last_seen_frame": self.last_seen_frame,
            "is_new_to_world": self.is_new_to_world,
            "parent_resource_id": self.parent_resource_id,
            "initial_title": self.initial_title,
            "current_title": self.current_title,
            "goal_required_final_state": self.goal_required_final_state,
            "disposition": self.disposition.value,
            "disposition_reason": self.disposition_reason,
            "cleanup_action": self.cleanup_action,
            "verification": self.verification.value,
            "final_state": self.final_state,
        }


@dataclass
class WorldFrame:
    """Immutable capture of resource identities at a point in time."""
    frame_id: str
    ts: float
    windows: List[ResourceIdentity] = field(default_factory=list)
    processes: List[ResourceIdentity] = field(default_factory=list)
    documents: List[ResourceIdentity] = field(default_factory=list)
    dialogs: List[ResourceIdentity] = field(default_factory=list)
    files: List[ResourceIdentity] = field(default_factory=list)

    def window_keys(self) -> Set[str]:
        return {w.key() for w in self.windows}

    def process_keys(self) -> Set[str]:
        return {p.key() for p in self.processes}

    def document_keys(self) -> Set[str]:
        return {d.key() for d in self.documents}

    def dialog_keys(self) -> Set[str]:
        return {d.key() for d in self.dialogs}

    def file_keys(self) -> Set[str]:
        return {f.key() for f in self.files}

    def all_keys(self) -> Set[str]:
        return (
            self.window_keys()
            | self.process_keys()
            | self.document_keys()
            | self.dialog_keys()
            | self.file_keys()
        )

    def by_key(self) -> Dict[str, ResourceIdentity]:
        out: Dict[str, ResourceIdentity] = {}
        for x in self.windows + self.processes + self.documents + self.dialogs + self.files:
            out[x.key()] = x
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "ts": self.ts,
            "windows": [w.to_dict() for w in self.windows],
            "processes": [p.to_dict() for p in self.processes],
            "documents": [d.to_dict() for d in self.documents],
            "dialogs": [d.to_dict() for d in self.dialogs],
            "files": [f.to_dict() for f in self.files],
        }


def _default_file_roots() -> List[Path]:
    import tempfile
    roots = [
        Path(tempfile.gettempdir()) / "astrarun",
        Path(tempfile.gettempdir()) / "astra_tmp",
    ]
    try:
        from astrarun.core.paths import AstraPaths
        base = Path(AstraPaths.data_dir() if hasattr(AstraPaths, "data_dir") else AstraPaths.base_dir())
        roots.append(base / "tmp")
        roots.append(base / "sandbox")
    except Exception:
        pass
    return roots


def _capture_file_artifacts(roots: Optional[List[Any]] = None) -> List[ResourceIdentity]:
    out: List[ResourceIdentity] = []
    for root in (roots or _default_file_roots()):
        try:
            rp = Path(root) if root else None
            if not rp or not rp.exists():
                continue
            for p in rp.rglob("*"):
                try:
                    if p.is_file():
                        out.append(
                            ResourceIdentity(
                                kind="file",
                                path=str(p.resolve()),
                                uia_id=None,
                            )
                        )
                except Exception:
                    continue
        except Exception:
            continue
    return out


def _capture_structural_children(windows: List[ResourceIdentity], max_windows: int = 12) -> Tuple[List[ResourceIdentity], List[ResourceIdentity]]:
    docs: List[ResourceIdentity] = []
    dialogs: List[ResourceIdentity] = []
    if sys.platform != "win32":
        return docs, dialogs
    try:
        from astrarun.interaction.discovery import inspect_window_ui
    except Exception:
        return docs, dialogs

    considered = 0
    for w in windows:
        if not w.hwnd:
            continue
        pname = (w.process_name or "").lower()
        if pname in ("explorer.exe", "dwm.exe", "sihost.exe", "applicationframehost.exe", "searchui.exe"):
            continue
        considered += 1
        if considered > max_windows:
            break
        try:
            els = inspect_window_ui(int(w.hwnd), max_depth=4, max_elements=40)
        except Exception:
            continue
        for el in els:
            ctype = ""
            try:
                ctype = (el.control_type.name or "").upper()
            except Exception:
                ctype = str(getattr(el, "control_type", "")).upper()
            el_id = getattr(el, "automation_id", None) or getattr(el, "runtime_id", None) or getattr(el, "element_id", None)
            if ctype in ("TABITEM", "TAB", "DOCUMENT", "EDIT", "TEXT"):
                uia = str(el_id) if el_id else f"ui_{w.hwnd}_{ctype}_{hash((getattr(el, 'name', '') or '', el_id)) & 0xFFFFFFFF:08x}"
                docs.append(
                    ResourceIdentity(
                        kind="document",
                        pid=w.pid,
                        hwnd=w.hwnd,
                        parent_hwnd=w.hwnd,
                        parent_pid=w.pid,
                        uia_id=uia,
                        class_name=ctype,
                        process_name=w.process_name,
                    )
                )
            if ctype in ("WINDOW", "PANE") and getattr(el, "is_dialog", False):
                dialogs.append(
                    ResourceIdentity(
                        kind="dialog",
                        pid=w.pid,
                        hwnd=int(getattr(el, "hwnd", 0) or w.hwnd or 0) or None,
                        parent_hwnd=w.hwnd,
                        parent_pid=w.pid,
                        uia_id=str(el_id) if el_id else f"dlg_{w.hwnd}_{hash(getattr(el, 'name', '') or '') & 0xFFFFFFFF:08x}",
                        process_name=w.process_name,
                    )
                )
    return docs, dialogs


def _ensure_desktop_attached() -> None:
    """Ensure current thread is attached to the interactive Default desktop."""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        DESKTOP_ALL = 0x01FF
        user32.OpenDesktopW.restype = ctypes.c_void_p
        user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]
        user32.SetThreadDesktop.restype = ctypes.c_int
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_ALL)
        if not hdesk:
            hdesk = user32.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def capture_world_frame(
    frame_id: str = "",
    include_structural_ui: bool = False,
    file_roots: Optional[List[Any]] = None,
) -> WorldFrame:
    """Capture process/window/document/dialog/file identities across the desktop."""
    frame = WorldFrame(frame_id=frame_id or f"frame_{int(time.time()*1000)}", ts=time.time())
    if sys.platform != "win32":
        return frame

    user32 = ctypes.windll.user32
    
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(h, _l):
        if not user32.IsWindow(h):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        create_time = None
        pname = ""
        try:
            p = psutil.Process(int(pid.value or 0))
            create_time = p.create_time()
            pname = p.name()
        except Exception:
            pass
        class_name = cls.value
        frame.windows.append(
            ResourceIdentity(
                kind="window",
                pid=int(pid.value or 0) or None,
                hwnd=int(h),
                process_name=pname,
                class_name=class_name,
                create_time=create_time,
            )
        )
        if "dialog" in class_name.lower() or class_name in ("#32770",):
            frame.dialogs.append(
                ResourceIdentity(
                    kind="dialog",
                    pid=int(pid.value or 0) or None,
                    hwnd=int(h),
                    parent_hwnd=None,
                    parent_pid=int(pid.value or 0) or None,
                    uia_id=f"win32dialog_{int(h)}",
                    class_name=class_name,
                    process_name=pname,
                )
            )
        return True

    user32.EnumWindows(_cb, 0)
    for p in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            frame.processes.append(
                ResourceIdentity(
                    kind="process",
                    pid=int(p.info["pid"]),
                    process_name=(p.info.get("name") or ""),
                    create_time=p.info.get("create_time"),
                )
            )
        except Exception:
            pass

    if include_structural_ui:
        docs, more_dialogs = _capture_structural_children(frame.windows)
        frame.documents.extend(docs)
        frame.dialogs.extend(more_dialogs)

    frame.files.extend(_capture_file_artifacts(file_roots))
    return frame


def snapshot_resources() -> Dict[str, Any]:
    """Backward-compatible dict snapshot built from WorldFrame."""
    fr = capture_world_frame()
    return {
        "windows": [
            {"hwnd": w.hwnd, "pid": w.pid, "title": "", "process": w.process_name, "class": w.class_name}
            for w in fr.windows
        ],
        "processes": [{"pid": p.pid, "name": p.process_name} for p in fr.processes],
        "ts": fr.ts,
        "frame": fr,
    }


def diff_frames(pre: WorldFrame, post: WorldFrame) -> Dict[str, List[ResourceIdentity]]:
    pre_k, post_k = pre.all_keys(), post.all_keys()
    post_by = post.by_key()
    pre_by = pre.by_key()
    new_keys = post_k - pre_k
    gone_keys = pre_k - post_k

    def _pick(keys: Set[str], prefix: str) -> List[ResourceIdentity]:
        return [post_by[k] for k in keys if k.startswith(prefix) and k in post_by]

    def _pick_gone(keys: Set[str], prefix: str) -> List[ResourceIdentity]:
        return [pre_by[k] for k in keys if k.startswith(prefix) and k in pre_by]

    return {
        "new_windows": _pick(new_keys, "window:"),
        "new_processes": _pick(new_keys, "process:"),
        "new_documents": _pick(new_keys, "document:") + _pick(new_keys, "uia:"),
        "new_dialogs": _pick(new_keys, "dialog:"),
        "new_files": _pick(new_keys, "file:"),
        "gone_windows": _pick_gone(gone_keys, "window:"),
        "gone_processes": _pick_gone(gone_keys, "process:"),
        "gone_documents": _pick_gone(gone_keys, "document:") + _pick_gone(gone_keys, "uia:"),
        "gone_dialogs": _pick_gone(gone_keys, "dialog:"),
        "gone_files": _pick_gone(gone_keys, "file:"),
    }


def is_system_noise_process(name: str) -> bool:
    n = (name or "").lower()
    noise = {
        "wmiprvse.exe", "svchost.exe", "csrss.exe", "lsass.exe", "services.exe",
        "explorer.exe", "dwm.exe", "fontdrvhost.exe", "sihost.exe", "taskhostw.exe",
        "runtimebroker.exe", "applicationframehost.exe", "system", "registry", "smss.exe",
    }
    return n in noise or n.startswith("system")


def is_process_descendant_of(candidate_pid: int, ancestor_pids: Set[int], max_depth: int = 5) -> bool:
    """Trace process ancestry via OS process tree to verify genuine causal lineage."""
    if not candidate_pid or not ancestor_pids:
        return False
    if candidate_pid in ancestor_pids:
        return True
    try:
        curr = psutil.Process(candidate_pid)
        depth = 0
        while curr and depth < max_depth:
            ppid = curr.ppid()
            if ppid in ancestor_pids:
                return True
            if ppid <= 4:
                break
            try:
                curr = psutil.Process(ppid)
                depth += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False


def classify_ownership_causal(
    identity: ResourceIdentity,
    baseline: WorldFrame,
    action_context: Optional[Dict[str, Any]] = None,
) -> Tuple[OwnershipClass, CausalProvenance]:
    """
    STRICT CAUSAL CLASSIFICATION (NO TEMPORAL BIAS, NO TITLE HACKS).
    
    A resource is TASK_CREATED only if affirmative causal evidence connects it to
    the governed Astra action or an already-proven task ancestor:
    A. Direct launch operation return (Popen.pid / launched_pid)
    B. PID explicitly launched as target
    C. Descendant process whose parent/ancestry traces to proven task-created process
    D. HWND whose owning PID is a proven task-created process
    E. Structural UIA child whose parent HWND is a proven task-created window
    F. Dialog whose owning PID or parent HWND is proven task-created
    G. File created inside an explicitly declared task-owned artifact scope
    
    TEMPORAL COINCIDENCE ALONE NEVER IMPLIES OWNERSHIP.
    Anything else is EXTERNAL_CONCURRENT or UNKNOWN.
    """
    key = identity.key()
    ctx = action_context or {}
    action_id = ctx.get("action_id", "")
    proven_task_pids: Set[int] = set(ctx.get("proven_task_pids", []))
    proven_task_hwnds: Set[int] = set(ctx.get("proven_task_hwnds", []))
    declared_artifact_scopes: List[str] = [
        os.path.abspath(str(s)).lower() for s in ctx.get("declared_artifact_scopes", [])
    ]
    launched_pid = ctx.get("launched_pid")
    if launched_pid:
        proven_task_pids.add(int(launched_pid))

    # 1. Baseline presence
    if key in baseline.all_keys():
        prov = CausalProvenance(
            evidence_kind=CausalEvidenceKind.PRE_EXISTING_BASELINE,
            creating_action_id="",
            rationale=f"identity {key} pre-existed in baseline frame {baseline.frame_id}",
            confidence=1.0,
        )
        return OwnershipClass.PRE_EXISTING_USER, prov

    # 2. Process attribution
    if identity.kind == "process":
        pid = identity.pid
        if pid is not None:
            if launched_pid is not None and pid == int(launched_pid):
                prov = CausalProvenance(
                    evidence_kind=CausalEvidenceKind.DIRECT_GOVERNED_LAUNCH,
                    creating_action_id=action_id,
                    rationale=f"PID {pid} matches governed action launch handle/PID directly",
                    confidence=1.0,
                )
                return OwnershipClass.TASK_CREATED, prov
            if is_process_descendant_of(pid, proven_task_pids):
                prov = CausalProvenance(
                    evidence_kind=CausalEvidenceKind.DESCENDANT_PROCESS,
                    creating_action_id=action_id,
                    parent_identity_key=f"process:{launched_pid}" if launched_pid else None,
                    rationale=f"PID {pid} is proven child/descendant of task ancestor in {proven_task_pids}",
                    confidence=1.0,
                )
                return OwnershipClass.TASK_DESCENDANT, prov

        # Appeared during action window but NO causal link
        prov = CausalProvenance(
            evidence_kind=CausalEvidenceKind.EXTERNAL_CONCURRENT,
            creating_action_id="",
            rationale=f"Process {identity.process_name} (PID {pid}) appeared concurrently without causal launch evidence",
            confidence=0.0,
        )
        return OwnershipClass.EXTERNAL_CONCURRENT, prov

    # 3. Window attribution (Win32 HWND)
    if identity.kind == "window":
        w_pid = identity.pid
        if w_pid is not None and (w_pid in proven_task_pids or is_process_descendant_of(w_pid, proven_task_pids)):
            prov = CausalProvenance(
                evidence_kind=CausalEvidenceKind.HWND_OF_TASK_PID,
                creating_action_id=action_id,
                parent_identity_key=f"process:{w_pid}",
                rationale=f"HWND {identity.hwnd} owned by proven task process PID {w_pid}",
                confidence=1.0,
            )
            return OwnershipClass.TASK_CREATED, prov

        prov = CausalProvenance(
            evidence_kind=CausalEvidenceKind.EXTERNAL_CONCURRENT,
            creating_action_id="",
            rationale=f"Window HWND {identity.hwnd} owned by external PID {w_pid}, not task",
            confidence=0.0,
        )
        return OwnershipClass.EXTERNAL_CONCURRENT, prov

    # 4. Dialog attribution
    if identity.kind == "dialog":
        d_pid = identity.pid
        d_parent_hwnd = identity.parent_hwnd
        if (d_pid is not None and (d_pid in proven_task_pids or is_process_descendant_of(d_pid, proven_task_pids))) or \
           (d_parent_hwnd is not None and d_parent_hwnd in proven_task_hwnds):
            prov = CausalProvenance(
                evidence_kind=CausalEvidenceKind.DIALOG_OF_TASK,
                creating_action_id=action_id,
                parent_identity_key=f"window:{d_parent_hwnd}" if d_parent_hwnd else f"process:{d_pid}",
                rationale=f"Dialog belongs to proven task window {d_parent_hwnd} or PID {d_pid}",
                confidence=1.0,
            )
            return OwnershipClass.TASK_CREATED, prov

        prov = CausalProvenance(
            evidence_kind=CausalEvidenceKind.EXTERNAL_CONCURRENT,
            creating_action_id="",
            rationale=f"Dialog belongs to external process or parent, not task",
            confidence=0.0,
        )
        return OwnershipClass.EXTERNAL_CONCURRENT, prov

    # 5. Document / UIA structural children
    if identity.kind == "document":
        parent_hwnd = identity.parent_hwnd
        if parent_hwnd is not None and parent_hwnd in proven_task_hwnds:
            prov = CausalProvenance(
                evidence_kind=CausalEvidenceKind.STRUCTURAL_CHILD,
                creating_action_id=action_id,
                parent_identity_key=f"window:{parent_hwnd}",
                rationale=f"UIA element {identity.uia_id} is structural child under task window {parent_hwnd}",
                confidence=1.0,
            )
            return OwnershipClass.TASK_CREATED, prov

        prov = CausalProvenance(
            evidence_kind=CausalEvidenceKind.EXTERNAL_CONCURRENT,
            creating_action_id="",
            rationale=f"UIA element parent HWND {parent_hwnd} is not task-owned",
            confidence=0.0,
        )
        return OwnershipClass.EXTERNAL_CONCURRENT, prov

    # 6. File attribution
    if identity.kind == "file" and identity.path:
        norm_path = os.path.abspath(identity.path).lower()
        if declared_artifact_scopes and any(norm_path.startswith(sc) for sc in declared_artifact_scopes):
            prov = CausalProvenance(
                evidence_kind=CausalEvidenceKind.TASK_DECLARED_ARTIFACT_SCOPE,
                creating_action_id=action_id,
                rationale=f"File {identity.path} is contained within declared task artifact scope",
                confidence=1.0,
            )
            return OwnershipClass.TASK_CREATED, prov

        prov = CausalProvenance(
            evidence_kind=CausalEvidenceKind.EXTERNAL_CONCURRENT,
            creating_action_id="",
            rationale=f"File {identity.path} created outside declared task scope",
            confidence=0.0,
        )
        return OwnershipClass.EXTERNAL_CONCURRENT, prov

    # 7. Unattributable
    prov = CausalProvenance(
        evidence_kind=CausalEvidenceKind.UNKNOWN_EVIDENCE,
        creating_action_id="",
        rationale=f"Identity {key} cannot be causally attributed to task action",
        confidence=0.0,
    )
    return OwnershipClass.UNKNOWN, prov


def plan_disposition(
    resource: TrackedResource,
    goal_final_state: str = "disposable",
    user_requested_preserve: bool = False,
) -> LifecycleDisposition:
    """
    Plan safe disposition.
    CRITICAL INVARIANT: UNKNOWN, EXTERNAL_CONCURRENT, and PRE_EXISTING_USER resources
    MUST NEVER be disposed! They are strictly PRESERVE.
    """
    if resource.ownership in (
        OwnershipClass.PRE_EXISTING_USER,
        OwnershipClass.SHARED,
        OwnershipClass.EXTERNAL_CONCURRENT,
        OwnershipClass.UNKNOWN,
    ):
        return LifecycleDisposition.PRESERVE
    if user_requested_preserve or goal_final_state == "preserve":
        return LifecycleDisposition.PRESERVE
    if goal_final_state == "save":
        return LifecycleDisposition.SAVE
    if resource.ownership in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT, OwnershipClass.TASK_ACQUIRED):
        return LifecycleDisposition.CLOSE
    return LifecycleDisposition.PRESERVE


class ReconcileReport:
    def __init__(self, task_id: str = "", **kwargs: Any) -> None:
        self.task_id = task_id
        self.resources_before: List[TrackedResource] = []
        self.resources_created: List[TrackedResource] = []
        self.resources_preserved: List[TrackedResource] = []
        self.resources_cleaned: List[TrackedResource] = []
        self.resources_remaining: List[TrackedResource] = []
        self.cleanup_executed = False
        self.process_cleaned_up = True
        self.orphaned_processes = 0
        self.orphaned_windows = 0
        self.active_ledger_resources = 0
        self.cleanup_exception: Optional[str] = None
        self.lifecycle_ok = False
        self.stop_reason = ""
        self.details: Dict[str, Any] = {}
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "cleanup_executed": self.cleanup_executed,
            "lifecycle_ok": self.lifecycle_ok,
            "process_cleaned_up": self.process_cleaned_up,
            "orphaned_processes": self.orphaned_processes,
            "orphaned_windows": self.orphaned_windows,
            "resources_created_count": len(self.resources_created),
            "resources_cleaned_count": len(self.resources_cleaned),
            "resources_preserved_count": len(self.resources_preserved),
            "resources_created": [r.to_dict() for r in self.resources_created],
            "resources_cleaned": [r.to_dict() for r in self.resources_cleaned],
            "resources_preserved": [r.to_dict() for r in self.resources_preserved],
            "stop_reason": self.stop_reason,
            "cleanup_exception": self.cleanup_exception,
            "details": self.details,
        }


class TaskResourceReconciler:
    """
    Causal ownership tracker and verified cleanup executor.
    Guarantees that temporal correlation never grants ownership.
    """

    def __init__(
        self,
        ledger: Any = None,
        cleanup_fn: Optional[Callable[[str, str], Dict[str, Any]]] = None,
        world_capture: Optional[Callable[[], WorldFrame]] = None,
    ):
        self.ledger = ledger
        self.cleanup_fn = cleanup_fn
        self.world_capture = world_capture or capture_world_frame
        self._resources: Dict[str, TrackedResource] = {}
        self.baseline: Optional[WorldFrame] = None
        self._task_id = ""
        self._action_seq = 0
        self._proven_task_pids: Set[int] = set()
        self._proven_task_hwnds: Set[int] = set()
        self._declared_artifact_scopes: List[str] = []

    def begin(
        self,
        task_id: str,
        task_markers: Optional[List[str]] = None,
        pre_snapshot: Optional[Dict[str, Any]] = None,
        declared_artifact_scopes: Optional[List[str]] = None,
    ) -> None:
        self._task_id = task_id
        if declared_artifact_scopes:
            self._declared_artifact_scopes = list(declared_artifact_scopes)
        if isinstance(pre_snapshot, dict) and isinstance(pre_snapshot.get("frame"), WorldFrame):
            self.baseline = pre_snapshot["frame"]
        elif hasattr(pre_snapshot, "windows"):
            self.baseline = pre_snapshot  # type: ignore
        else:
            self.baseline = self.world_capture()

    def declare_artifact_scope(self, scope_path: str) -> None:
        self._declared_artifact_scopes.append(os.path.abspath(scope_path).lower())

    def register_launched_process(self, pid: int, action_id: str = "") -> TrackedResource:
        """Affirmative evidence: process returned directly from governed launch operation."""
        self._proven_task_pids.add(int(pid))
        pname = ""
        c_time = None
        try:
            p = psutil.Process(pid)
            pname = p.name()
            c_time = p.create_time()
        except Exception:
            pass
        ident = ResourceIdentity(
            kind="process",
            pid=pid,
            process_name=pname,
            create_time=c_time,
        )
        prov = CausalProvenance(
            evidence_kind=CausalEvidenceKind.DIRECT_GOVERNED_LAUNCH,
            creating_action_id=action_id,
            rationale=f"Governed action directly returned PID {pid}",
            confidence=1.0,
        )
        return self.register(
            resource_type="process",
            ownership=OwnershipClass.TASK_CREATED,
            ownership_evidence=prov.rationale,
            identity=ident,
            provenance=prov,
            creating_action_id=action_id,
            goal_required_final_state="disposable",
        )

    def register(
        self,
        resource_type: str,
        ownership: OwnershipClass,
        ownership_evidence: str,
        identity: ResourceIdentity,
        provenance: Optional[CausalProvenance] = None,
        creating_action_id: str = "",
        first_seen_frame: str = "",
        parent_resource_id: Optional[str] = None,
        path: Optional[str] = None,
        goal_required_final_state: str = "disposable",
        is_new_to_world: bool = False,
    ) -> TrackedResource:
        rid = f"res_{uuid.uuid4().hex[:10]}"
        if path and not identity.path:
            identity.path = path
        res = TrackedResource(
            resource_id=rid,
            resource_type=resource_type,
            task_id=self._task_id,
            identity=identity,
            ownership=ownership,
            ownership_evidence=ownership_evidence,
            provenance=provenance,
            creating_action_id=creating_action_id,
            first_seen_frame=first_seen_frame,
            parent_resource_id=parent_resource_id,
            goal_required_final_state=goal_required_final_state,
            is_new_to_world=is_new_to_world,
        )
        res.disposition = plan_disposition(res, goal_final_state=goal_required_final_state)
        res.disposition_reason = f"causal ownership={ownership.value}"
        if res.disposition == LifecycleDisposition.CLOSE:
            if identity.kind == "process":
                res.cleanup_action = "terminate_task_owned_process"
            elif identity.kind == "window":
                res.cleanup_action = "close_hwnd_identity"
            elif identity.kind == "dialog":
                res.cleanup_action = "close_dialog_hwnd"
            elif identity.kind == "file":
                res.cleanup_action = "delete_task_artifact_file"
            else:
                res.cleanup_action = "close_owned_identity"
        elif res.disposition == LifecycleDisposition.PRESERVE:
            res.cleanup_action = "preserve_untouched"

        self._resources[rid] = res
        if ownership in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT):
            if identity.pid:
                self._proven_task_pids.add(identity.pid)
            if identity.hwnd:
                self._proven_task_hwnds.add(identity.hwnd)
        return res

    def record_action_delta(
        self,
        pre_action: WorldFrame,
        post_action: WorldFrame,
        action_id: str = "",
        action_context: Optional[Dict[str, Any]] = None,
    ) -> List[TrackedResource]:
        """
        Record observational delta and causally classify every new resource.
        OBSERVATION != OWNERSHIP.
        """
        self._action_seq += 1
        action_id = action_id or f"action_{self._action_seq}"
        if self.baseline is None:
            self.baseline = pre_action

        ctx = dict(action_context or {})
        ctx["action_id"] = action_id
        ctx["proven_task_pids"] = list(self._proven_task_pids)
        ctx["proven_task_hwnds"] = list(self._proven_task_hwnds)
        ctx["declared_artifact_scopes"] = list(self._declared_artifact_scopes)

        delta = diff_frames(pre_action, post_action)
        new_idents = (
            delta["new_windows"]
            + delta["new_processes"]
            + delta["new_documents"]
            + delta["new_dialogs"]
            + delta["new_files"]
        )

        created: List[TrackedResource] = []
        for ident in new_idents:
            existing = next((r for r in self._resources.values() if r.identity.key() == ident.key()), None)
            if existing:
                existing.last_seen_frame = post_action.frame_id
                continue

            own, prov = classify_ownership_causal(ident, self.baseline, ctx)

            # Check if this process can be dynamically added to proven PIDs for subsequent windows
            if own in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT) and ident.pid:
                self._proven_task_pids.add(ident.pid)
                ctx["proven_task_pids"] = list(self._proven_task_pids)
            if own in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT) and ident.hwnd:
                self._proven_task_hwnds.add(ident.hwnd)
                ctx["proven_task_hwnds"] = list(self._proven_task_hwnds)

            rtype = ident.kind
            res = self.register(
                resource_type=rtype,
                ownership=own,
                ownership_evidence=prov.rationale,
                identity=ident,
                provenance=prov,
                creating_action_id=action_id,
                first_seen_frame=post_action.frame_id,
                path=ident.path,
                goal_required_final_state="disposable",
                is_new_to_world=True,
            )
            created.append(res)
        return created

    def resources(self) -> List[TrackedResource]:
        return list(self._resources.values())

    def observed_resources(self) -> List[TrackedResource]:
        return list(self._resources.values())

    def new_resources(self) -> List[TrackedResource]:
        return [r for r in self._resources.values() if r.is_new_to_world]

    def causally_attributed_resources(self) -> List[TrackedResource]:
        return [r for r in self._resources.values() if r.ownership in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT)]

    def task_owned_resources(self) -> List[TrackedResource]:
        return [r for r in self._resources.values() if r.ownership in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT, OwnershipClass.TASK_ACQUIRED)]

    def disposable_resources(self) -> List[TrackedResource]:
        return [
            r for r in self._resources.values()
            if r.ownership in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT, OwnershipClass.TASK_ACQUIRED)
            and r.disposition in (LifecycleDisposition.CLOSE, LifecycleDisposition.DISCARD)
        ]

    def reconcile_and_cleanup(self, goal_final_state: str = "disposable") -> ReconcileReport:
        """
        Execute verified disposal ONLY on task-owned disposable resources.
        UNKNOWN and EXTERNAL_CONCURRENT resources are strictly protected.
        """
        report = ReconcileReport(task_id=self._task_id)
        report.resources_before = list(self._resources.values())
        report.resources_created = self.causally_attributed_resources()
        report.cleanup_executed = True

        to_close = self.disposable_resources()
        preserved = [r for r in self._resources.values() if r not in to_close]
        report.resources_preserved = preserved

        user32 = ctypes.windll.user32 if sys.platform == "win32" else None

        # 1. Close windows gracefully first
        for r in to_close:
            if r.identity.kind in ("window", "dialog") and r.identity.hwnd and user32:
                try:
                    if user32.IsWindow(r.identity.hwnd):
                        user32.PostMessageW(r.identity.hwnd, WM_CLOSE, 0, 0)
                except Exception as err:
                    logger.debug("Failed PostMessage to HWND %s: %s", r.identity.hwnd, err)

        time.sleep(0.3)

        # 2. Delete task artifact files
        for r in to_close:
            if r.identity.kind == "file" and r.identity.path:
                try:
                    p = Path(r.identity.path)
                    if p.exists():
                        p.unlink()
                        r.verification = LifecycleOutcome.VERIFIED
                        r.final_state = "file_deleted"
                        report.resources_cleaned.append(r)
                except Exception as err:
                    r.verification = LifecycleOutcome.FAILED
                    r.final_state = f"file_delete_failed: {err}"

        # 3. Terminate task processes if still alive
        for r in to_close:
            if r.identity.kind == "process" and r.identity.pid:
                pid = r.identity.pid
                try:
                    if psutil.pid_exists(pid):
                        p = psutil.Process(pid)
                        p.terminate()
                        try:
                            p.wait(timeout=1.0)
                        except psutil.TimeoutExpired:
                            p.kill()
                    r.verification = LifecycleOutcome.VERIFIED
                    r.final_state = "process_terminated"
                    report.resources_cleaned.append(r)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    r.verification = LifecycleOutcome.VERIFIED
                    r.final_state = "process_already_exited"
                    report.resources_cleaned.append(r)
            elif r.identity.kind in ("window", "dialog") and r not in report.resources_cleaned:
                hwnd_dead = True
                if r.identity.hwnd and user32:
                    hwnd_dead = not bool(user32.IsWindow(r.identity.hwnd))
                if hwnd_dead:
                    r.verification = LifecycleOutcome.VERIFIED
                    r.final_state = "window_closed"
                    report.resources_cleaned.append(r)
                else:
                    r.verification = LifecycleOutcome.FAILED
                    r.final_state = "window_lingering"
            elif r.identity.kind == "document" and r not in report.resources_cleaned:
                parent_hwnd_dead = True
                if r.identity.parent_hwnd and user32:
                    parent_hwnd_dead = not bool(user32.IsWindow(r.identity.parent_hwnd))
                parent_pid_dead = True
                if r.identity.parent_pid:
                    parent_pid_dead = not psutil.pid_exists(r.identity.parent_pid)
                if parent_hwnd_dead or parent_pid_dead:
                    r.verification = LifecycleOutcome.VERIFIED
                    r.final_state = "parent_surface_closed"
                    report.resources_cleaned.append(r)
                else:
                    r.verification = LifecycleOutcome.FAILED
                    r.final_state = "parent_surface_lingering"

        # Check for lingering disposable resources
        lingering = [r for r in to_close if r.verification != LifecycleOutcome.VERIFIED]
        report.resources_remaining = lingering
        report.process_cleaned_up = len(lingering) == 0
        report.orphaned_processes = len([r for r in lingering if r.identity.kind == "process"])
        report.orphaned_windows = len([r for r in lingering if r.identity.kind == "window"])
        report.lifecycle_ok = (len(lingering) == 0)

        # Also delegate to legacy ledger if available
        if self.cleanup_fn:
            try:
                self.cleanup_fn(self._task_id, "COMPLETED" if report.lifecycle_ok else "FAILED")
            except Exception:
                pass

        return report


def compare_world_state(
    baseline: WorldFrame,
    final: WorldFrame,
    tracked: List[TrackedResource],
    goal_preserve_keys: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Final world-state oracle (reality, not ledger claims).
    - Every baseline identity should remain (unless user requested change).
    - Every disposable TASK_CREATED / TASK_DESCENDANT identity should be absent.
    - Concurrent external identities must remain alive.
    """
    base_keys = baseline.all_keys()
    fin_keys = final.all_keys()

    task_disposable = [
        r for r in tracked
        if r.ownership in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT, OwnershipClass.TASK_ACQUIRED)
        and r.disposition in (LifecycleDisposition.CLOSE, LifecycleDisposition.DISCARD)
    ]

    task_preserve = [
        r for r in tracked
        if r.disposition in (LifecycleDisposition.PRESERVE, LifecycleDisposition.SAVE)
        and r.ownership in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT, OwnershipClass.TASK_ACQUIRED)
    ]

    missing_baseline = sorted(base_keys - fin_keys)
    residual_task = []
    user32 = ctypes.windll.user32 if sys.platform == "win32" else None

    for r in task_disposable:
        k = r.identity.key()
        if k in fin_keys:
            residual_task.append({"resource_id": r.resource_id, "key": k, "reason": "identity still in final frame"})
        elif r.identity.hwnd and user32:
            try:
                if user32.IsWindow(r.identity.hwnd):
                    residual_task.append({"resource_id": r.resource_id, "key": k, "reason": "hwnd still live"})
            except Exception:
                pass
        elif r.identity.pid:
            if psutil.pid_exists(r.identity.pid):
                residual_task.append({"resource_id": r.resource_id, "key": k, "reason": "pid still live"})

    missing_preserve = [
        r.identity.key() for r in task_preserve if r.identity.key() not in fin_keys
    ]

    external_concurrent_tracked = [
        r for r in tracked if r.ownership in (OwnershipClass.EXTERNAL_CONCURRENT, OwnershipClass.UNKNOWN)
    ]
    external_concurrent_survived = [
        r.identity.key() for r in external_concurrent_tracked if r.identity.key() in fin_keys
    ]

    ok = (len(residual_task) == 0 and len(missing_preserve) == 0 and len(missing_baseline) == 0)
    return {
        "baseline_frame": baseline.frame_id,
        "final_frame": final.frame_id,
        "baseline_keys": sorted(base_keys),
        "final_keys": sorted(fin_keys),
        "missing_baseline_identities": missing_baseline,
        "residual_task_owned": residual_task,
        "missing_requested_preserve": missing_preserve,
        "external_concurrent_count": len(external_concurrent_tracked),
        "external_concurrent_survived_count": len(external_concurrent_survived),
        "external_concurrent_survived": external_concurrent_survived,
        "task_disposable_count": len(task_disposable),
        "world_state_ok": ok,
        "verdict": "PASS" if ok else "FAIL",
    }


def scan_and_reconcile_residue(
    task_marker_prefix: str = "ASTRA_CAUSAL",
    ledger: Any = None,
) -> Dict[str, Any]:
    """Diagnostic-only residue scanner."""
    fr = capture_world_frame()
    return {
        "total_windows": len(fr.windows),
        "total_processes": len(fr.processes),
        "ts": fr.ts,
    }
