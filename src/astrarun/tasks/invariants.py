"""Task Invariant Objects and Scoped WatchSets for AstraRun 1.0 Adaptive Runtime.

Provides cost-aware continuous verification:
- Event-driven monitoring first (Win32, filesystem, process, network)
- Explicit invariants with typed targets, expected states, and recovery policies
- TaskWatchSet scoping to observe only what matters to the active task
"""

from __future__ import annotations

import hashlib
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import psutil

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tasks.invariants")


class InvariantType(str, Enum):
    WINDOW_EXISTS = "WINDOW_EXISTS"
    PROCESS_RUNNING = "PROCESS_RUNNING"
    FILE_EXISTS = "FILE_EXISTS"
    FILE_HASH_MATCHES = "FILE_HASH_MATCHES"
    FILE_CONTAINS_CHANGE = "FILE_CONTAINS_CHANGE"
    DOWNLOAD_PROGRESSING = "DOWNLOAD_PROGRESSING"
    URL_MATCHES = "URL_MATCHES"
    DOM_STATE_MATCHES = "DOM_STATE_MATCHES"
    WORKSPACE_AVAILABLE = "WORKSPACE_AVAILABLE"
    MODEL_AVAILABLE = "MODEL_AVAILABLE"
    NETWORK_AVAILABLE = "NETWORK_AVAILABLE"
    CAPABILITY_AVAILABLE = "CAPABILITY_AVAILABLE"


class InvariantImportance(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    TRANSIENT = "TRANSIENT"


@dataclass
class TaskInvariant:
    """Strongly typed assertion about workstation or environmental state."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: InvariantType = InvariantType.PROCESS_RUNNING
    target: str = ""  # process_name, hwnd, file_path, url, etc.
    expected_state: Any = True
    importance: InvariantImportance = InvariantImportance.REQUIRED
    verification_provider: str = "auto"
    poll_policy: str = "step_boundary"  # event_driven, periodic, step_boundary
    recovery_policy: str = "reopen_app"  # reopen_app, resume_download, reconcile_file, wait_network, ask_user
    metadata: Dict[str, Any] = field(default_factory=dict)

    def check(self, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any, str]:
        """Verify invariant against actual world state.
        
        Returns:
            (is_valid, observed_state, message)
        """
        try:
            if self.type == InvariantType.PROCESS_RUNNING:
                proc_name = self.target.lower()
                matching_pids = []
                for p in psutil.process_iter(['name', 'pid']):
                    try:
                        if p.info['name'] and p.info['name'].lower() == proc_name:
                            matching_pids.append(p.info['pid'])
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                is_running = len(matching_pids) > 0
                return (
                    is_running == bool(self.expected_state),
                    matching_pids,
                    f"Process '{self.target}' running: {is_running} (PIDs: {matching_pids})",
                )

            elif self.type == InvariantType.FILE_EXISTS:
                p = Path(self.target)
                exists = p.exists()
                return (
                    exists == bool(self.expected_state),
                    exists,
                    f"File '{self.target}' exists: {exists}",
                )

            elif self.type == InvariantType.FILE_HASH_MATCHES:
                p = Path(self.target)
                if not p.exists():
                    return (False, None, f"File '{self.target}' does not exist for hash check")
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    while chunk := f.read(1024 * 1024):
                        h.update(chunk)
                actual_hash = h.hexdigest().lower()
                expected = str(self.expected_state).lower()
                matches = actual_hash == expected
                return (
                    matches,
                    actual_hash,
                    f"File hash for '{self.target}' matches: {matches} (actual={actual_hash[:12]}..., expected={expected[:12]}...)",
                )

            elif self.type == InvariantType.FILE_CONTAINS_CHANGE:
                p = Path(self.target)
                if not p.exists():
                    return (False, "", f"File '{self.target}' does not exist")
                content = p.read_text(encoding="utf-8", errors="replace")
                expected_needle = str(self.expected_state)
                contains = expected_needle in content
                return (
                    contains,
                    len(content),
                    f"File '{self.target}' contains expected change: {contains}",
                )

            elif self.type == InvariantType.NETWORK_AVAILABLE:
                # Fast socket check to default gateway / dns without heavy traffic
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(0.5)
                    # Check connection to reliable address
                    sock.connect(("8.8.8.8", 53))
                    sock.close()
                    online = True
                except Exception:
                    online = False
                return (
                    online == bool(self.expected_state),
                    online,
                    f"Network connectivity: {online}",
                )

            elif self.type == InvariantType.DOWNLOAD_PROGRESSING:
                dest = Path(self.target)
                part_file = dest.with_suffix(dest.suffix + ".part")
                exists = dest.exists() or part_file.exists()
                size = 0
                if dest.exists():
                    size = dest.stat().st_size
                elif part_file.exists():
                    size = part_file.stat().st_size
                last_size = self.metadata.get("last_size", 0)
                self.metadata["last_size"] = size
                progressing = size >= last_size and exists
                return (
                    progressing,
                    size,
                    f"Download '{self.target}' progressing: {size} bytes",
                )

            elif self.type == InvariantType.WINDOW_EXISTS:
                # Target can be window title substring or hwnd integer
                from astrarun.capabilities.window_manager import find_windows_by_title
                windows = find_windows_by_title(self.target)
                exists = len(windows) > 0
                return (
                    exists == bool(self.expected_state),
                    [w.hwnd for w in windows],
                    f"Window '{self.target}' found: {exists} (Count: {len(windows)})",
                )

            elif self.type == InvariantType.WORKSPACE_AVAILABLE:
                p = Path(self.target)
                accessible = p.exists() and p.is_dir()
                return (
                    accessible,
                    accessible,
                    f"Workspace '{self.target}' accessible: {accessible}",
                )

            else:
                # Generic fallback using context evaluation
                if context and self.target in context:
                    val = context[self.target]
                    matches = val == self.expected_state
                    return (matches, val, f"Context key '{self.target}'={val} (expected {self.expected_state})")
                return (True, None, f"Untracked invariant type {self.type.value} passed by default")

        except Exception as err:
            logger.error("Error evaluating invariant %s (%s): %s", self.id, self.type.value, err)
            return (False, None, f"Evaluation error: {err}")


@dataclass
class TaskWatchSet:
    """Scoped dependency watcher monitoring only resources relevant to an active task."""
    task_id: str
    invariants: Dict[str, TaskInvariant] = field(default_factory=dict)
    watched_processes: Set[str] = field(default_factory=set)
    watched_windows: Set[str] = field(default_factory=set)
    watched_files: Set[Path] = field(default_factory=set)
    watched_downloads: Set[str] = field(default_factory=set)
    last_check_timestamp: float = 0.0

    def add_invariant(self, invariant: TaskInvariant) -> None:
        """Register a new invariant into the task watch set."""
        self.invariants[invariant.id] = invariant
        if invariant.type == InvariantType.PROCESS_RUNNING:
            self.watched_processes.add(invariant.target.lower())
        elif invariant.type == InvariantType.WINDOW_EXISTS:
            self.watched_windows.add(invariant.target.lower())
        elif invariant.type in (InvariantType.FILE_EXISTS, InvariantType.FILE_HASH_MATCHES, InvariantType.FILE_CONTAINS_CHANGE):
            self.watched_files.add(Path(invariant.target))
        elif invariant.type == InvariantType.DOWNLOAD_PROGRESSING:
            self.watched_downloads.add(invariant.target)

    def check_all(self, context: Optional[Dict[str, Any]] = None) -> List[Tuple[TaskInvariant, bool, Any, str]]:
        """Evaluate all active invariants for this task."""
        self.last_check_timestamp = time.time()
        results = []
        for inv in self.invariants.values():
            valid, observed, msg = inv.check(context)
            results.append((inv, valid, observed, msg))
        return results

    def get_broken_invariants(self, context: Optional[Dict[str, Any]] = None) -> List[Tuple[TaskInvariant, Any, str]]:
        """Return list of required invariants that are currently broken."""
        broken = []
        for inv, valid, observed, msg in self.check_all(context):
            if not valid and inv.importance == InvariantImportance.REQUIRED:
                broken.append((inv, observed, msg))
        return broken
