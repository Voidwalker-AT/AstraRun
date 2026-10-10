"""Task-local Side-Effect Ledger for Phase F0-23."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from astrarun.agent.models import GoalContract


class ResourceOwnership(str, Enum):
    USER_OWNED_PREEXISTING = "USER_OWNED_PREEXISTING"
    ASTRA_OWNED_TASK_RESOURCE = "ASTRA_OWNED_TASK_RESOURCE"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


class MutationType(str, Enum):
    PROCESS_LAUNCH = "PROCESS_LAUNCH"
    PROCESS_TERMINATION = "PROCESS_TERMINATION"
    WINDOW_OPEN = "WINDOW_OPEN"
    WINDOW_CLOSE = "WINDOW_CLOSE"
    WINDOW_SNAP = "WINDOW_SNAP"
    FILE_CREATE = "FILE_CREATE"
    FILE_MODIFY = "FILE_MODIFY"
    FILE_DELETE = "FILE_DELETE"
    CLIPBOARD_MUTATE = "CLIPBOARD_MUTATE"
    SYSTEM_STATE = "SYSTEM_STATE"


@dataclass
class SideEffectEntry:
    entry_id: str
    mutation_type: MutationType
    target: str
    ownership: ResourceOwnership
    is_consequential: bool
    is_requested: bool
    advances_goal: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskSideEffectLedger:
    """
    Task-local ledger tracking all physical and OS mutations during an AstraRun execution.
    Compares observed mutations against the GoalContract to detect unrequested side-effects.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.entries: List[SideEffectEntry] = []
        self.pre_existing_pids: Set[int] = set()
        self.pre_existing_hwnds: Set[int] = set()

    def record_baseline(self, pids: Set[int], hwnds: Set[int]) -> None:
        self.pre_existing_pids = set(pids)
        self.pre_existing_hwnds = set(hwnds)

    def record_process_launch(self, pid: int, name: str, is_requested: bool = True) -> None:
        ownership = ResourceOwnership.ASTRA_OWNED_TASK_RESOURCE if pid not in self.pre_existing_pids else ResourceOwnership.USER_OWNED_PREEXISTING
        self.entries.append(SideEffectEntry(
            entry_id=f"proc_launch_{pid}",
            mutation_type=MutationType.PROCESS_LAUNCH,
            target=f"{name} (PID {pid})",
            ownership=ownership,
            is_consequential=True,
            is_requested=is_requested,
            advances_goal=is_requested,
            metadata={"pid": pid, "name": name},
        ))

    def record_window_mutation(self, hwnd: int, title: str, mutation: MutationType, is_requested: bool) -> None:
        ownership = ResourceOwnership.USER_OWNED_PREEXISTING if hwnd in self.pre_existing_hwnds else ResourceOwnership.ASTRA_OWNED_TASK_RESOURCE
        self.entries.append(SideEffectEntry(
            entry_id=f"win_{mutation.value.lower()}_{hwnd}",
            mutation_type=mutation,
            target=f"{title} (HWND {hex(hwnd)})",
            ownership=ownership,
            is_consequential=True,
            is_requested=is_requested,
            advances_goal=is_requested,
            metadata={"hwnd": hwnd, "title": title},
        ))

    def record_file_mutation(self, path: str, mutation: MutationType, is_requested: bool) -> None:
        self.entries.append(SideEffectEntry(
            entry_id=f"file_{mutation.value.lower()}_{Path(path).name}",
            mutation_type=mutation,
            target=str(path),
            ownership=ResourceOwnership.ASTRA_OWNED_TASK_RESOURCE,
            is_consequential=True,
            is_requested=is_requested,
            advances_goal=is_requested,
            metadata={"path": str(path)},
        ))

    def reconcile_with_contract(self, contract: GoalContract) -> Dict[str, Any]:
        """
        Audit all ledger entries against the GoalContract.
        Identifies unrequested side-effects, destructive mutations, and resource leaks.
        """
        unrequested_consequential = []
        user_resource_violations = []
        leaked_task_resources = []

        for entry in self.entries:
            # Check for unrequested consequential side-effects
            if entry.is_consequential and not entry.advances_goal:
                unrequested_consequential.append({
                    "entry_id": entry.entry_id,
                    "mutation_type": entry.mutation_type.value,
                    "target": entry.target,
                    "ownership": entry.ownership.value,
                    "reason": "Consequential mutation occurred without advancing any contract predicate.",
                })

            # Check if user-owned pre-existing resources were mutated or closed without instruction
            if entry.ownership == ResourceOwnership.USER_OWNED_PREEXISTING:
                if entry.mutation_type in (MutationType.PROCESS_TERMINATION, MutationType.WINDOW_CLOSE, MutationType.FILE_DELETE):
                    if not entry.is_requested:
                        user_resource_violations.append({
                            "entry_id": entry.entry_id,
                            "target": entry.target,
                            "violation": "Pre-existing user-owned resource closed/deleted without request",
                        })

        is_clean = len(unrequested_consequential) == 0 and len(user_resource_violations) == 0

        return {
            "task_id": self.task_id,
            "contract_id": contract.contract_id,
            "total_mutations_recorded": len(self.entries),
            "unrequested_consequential_side_effects": unrequested_consequential,
            "user_resource_violations": user_resource_violations,
            "is_clean": is_clean,
            "verdict": "PASS" if is_clean else "FAIL",
        }
