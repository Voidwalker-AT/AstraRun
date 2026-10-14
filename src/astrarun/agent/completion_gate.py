"""Authoritative Completion Gate for AstraRun.

PRIMARY ARCHITECTURAL LAW:
GOAL_COMPLETED <= REQUIRED GOAL CONTRACT POSTCONDITIONS VERIFIED

Never:
- function returned -> GOAL_COMPLETED
- plan exhausted -> GOAL_COMPLETED
- action succeeded -> GOAL_COMPLETED
- artifact exists -> GOAL_COMPLETED
- RESULT_PRESENTATION_REQUESTED -> GOAL_COMPLETED
- cleanup attempted -> GOAL_COMPLETED

Completion is derived ONLY from the explicit contract for THAT goal,
backed by run-scoped affirmative physical evidence.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from astrarun.agent.models import (
    GoalContract,
    GoalPredicate,
    PredicateStatus,
    PredicateType,
)

logger = logging.getLogger("astrarun.agent.completion_gate")


class GateVerdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class CompletionGateResult:
    verdict: GateVerdict
    can_complete: bool
    status: str  # "SUCCESS", "FAILED_UNSATISFIED_POSTCONDITIONS", etc.
    message: str
    verified_predicates: List[str] = field(default_factory=list)
    missing_predicates: List[str] = field(default_factory=list)
    failed_predicates: List[str] = field(default_factory=list)
    evidence_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "can_complete": self.can_complete,
            "status": self.status,
            "message": self.message,
            "verified_predicates": self.verified_predicates,
            "missing_predicates": self.missing_predicates,
            "failed_predicates": self.failed_predicates,
            "evidence_summary": self.evidence_summary,
        }


class AuthoritativeCompletionGate:
    """Authoritative singleton gate governing task and goal completion."""

    _contracts_by_run: Dict[str, GoalContract] = {}
    _contracts_by_task: Dict[str, GoalContract] = {}
    _lock = threading.Lock()

    @classmethod
    def register_contract(
        cls,
        contract: GoalContract,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Register a goal contract scoped to a run_id and/or task_id."""
        with cls._lock:
            if run_id:
                cls._contracts_by_run[run_id] = contract
            if task_id:
                cls._contracts_by_task[task_id] = contract
            if hasattr(contract, "contract_id") and contract.contract_id:
                cls._contracts_by_task[contract.contract_id] = contract

    @classmethod
    def get_contract(
        cls,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Optional[GoalContract]:
        """Retrieve active contract for run_id or task_id."""
        with cls._lock:
            if run_id and run_id in cls._contracts_by_run:
                return cls._contracts_by_run[run_id]
            if task_id and task_id in cls._contracts_by_task:
                return cls._contracts_by_task[task_id]
            return None

    @classmethod
    def unregister_contract(
        cls,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Unregister contract to ensure stale contracts never cross runs or tasks."""
        with cls._lock:
            if run_id and run_id in cls._contracts_by_run:
                del cls._contracts_by_run[run_id]
            if task_id and task_id in cls._contracts_by_task:
                del cls._contracts_by_task[task_id]

    @classmethod
    def clear_all_contracts(cls) -> None:
        """Clear all registered contracts (for testing or reset)."""
        with cls._lock:
            cls._contracts_by_run.clear()
            cls._contracts_by_task.clear()

    @classmethod
    def can_complete(
        cls,
        goal_contract: Optional[GoalContract],
        execution_state: Optional[Dict[str, Any]] = None,
        evidence_state: Optional[Dict[str, Any]] = None,
        active_run_id: Optional[str] = None,
        active_task_id: Optional[str] = None,
    ) -> CompletionGateResult:
        """
        Authoritative evaluation of whether a goal may complete as SUCCESS.
        All required predicates must be affirmatively verified with matching provenance.
        """
        exec_state = execution_state or {}
        ev_state = evidence_state or {}

        # 1. Contract presence check: No goal may complete without a contract or explicit postconditions
        if not goal_contract:
            # Check registered contracts by run_id or task_id
            if active_run_id or active_task_id:
                goal_contract = cls.get_contract(run_id=active_run_id, task_id=active_task_id)
            if not goal_contract:
                contract_from_exec = exec_state.get("goal_contract")
                if isinstance(contract_from_exec, GoalContract):
                    goal_contract = contract_from_exec
                else:
                    return CompletionGateResult(
                        verdict=GateVerdict.REJECTED,
                        can_complete=False,
                        status="FAILED_NO_CONTRACT",
                        message="Missing GoalContract: cannot complete without explicit contract postconditions.",
                    )

        # 2. Extract mandatory predicates
        mandatory_preds = goal_contract.get_mandatory_predicates()
        if not mandatory_preds and not goal_contract.acceptance_predicates:
            return CompletionGateResult(
                verdict=GateVerdict.REJECTED,
                can_complete=False,
                status="FAILED_NO_POSTCONDITIONS",
                message="GoalContract contains zero acceptance predicates (C1 no postconditions).",
            )

        verified: List[str] = []
        missing: List[str] = []
        failed: List[str] = []

        # 3. Evaluate each mandatory predicate
        for pred in mandatory_preds:
            pred_id = pred.predicate_id or pred.description or str(pred.predicate_type)

            # Check status
            if pred.status == PredicateStatus.PENDING:
                missing.append(f"{pred_id}: predicate is PENDING (not evaluated)")
                continue
            if pred.status == PredicateStatus.UNKNOWN:
                missing.append(f"{pred_id}: predicate status is UNKNOWN (C3)")
                continue
            if pred.status == PredicateStatus.VIOLATED:
                failed.append(f"{pred_id}: predicate is VIOLATED (C4): {pred.error_message or 'condition false'}")
                continue
            if pred.status != PredicateStatus.SATISFIED:
                failed.append(f"{pred_id}: predicate status is {pred.status}")
                continue

            # Provenance Check: Validate run_id and task_id linkage
            pred_ev = pred.evidence or {}
            ev_run_id = pred_ev.get("run_id") or ev_state.get("run_id")
            ev_task_id = pred_ev.get("task_id") or ev_state.get("task_id")

            if active_run_id and ev_run_id and ev_run_id != active_run_id:
                failed.append(f"{pred_id}: evidence run_id mismatch (expected {active_run_id}, got {ev_run_id}) (C14)")
                continue

            if active_task_id and ev_task_id and ev_task_id != active_task_id:
                failed.append(f"{pred_id}: evidence task_id mismatch (expected {active_task_id}, got {ev_task_id}) (C13)")
                continue

            # Check for stale evidence from another run (C12)
            if pred_ev.get("stale") or pred_ev.get("prior_run"):
                failed.append(f"{pred_id}: evidence is marked stale from prior run (C12)")
                continue

            # Specific predicate semantics check
            ptype = pred.predicate_type
            if isinstance(ptype, PredicateType):
                ptype_val = ptype.value
            else:
                ptype_val = str(ptype)

            if ptype_val in ("FILE_EXISTS", "FILE_NON_EMPTY", "FILE_CONTENT_CONTAINS", "FILE_CONTENT_EQUALS"):
                # Semantic content verification (C7)
                target_file = pred.parameters.get("path") or pred.parameters.get("target_artifact") or pred_ev.get("path")
                if target_file:
                    tp = Path(target_file)
                    if not tp.exists():
                        failed.append(f"{pred_id}: target artifact {target_file} does not exist on disk")
                        continue
                    if ptype_val == "FILE_NON_EMPTY":
                        try:
                            if tp.stat().st_size == 0:
                                failed.append(f"{pred_id}: artifact {target_file} is empty (0 bytes)")
                                continue
                        except Exception as e:
                            failed.append(f"{pred_id}: failed stating artifact: {e}")
                            continue
                    if ptype_val == "FILE_CONTENT_CONTAINS":
                        expected_sub = pred.parameters.get("content") or pred.parameters.get("expected_content") or ""
                        try:
                            actual_text = tp.read_text(encoding="utf-8", errors="ignore")
                            if expected_sub and expected_sub not in actual_text:
                                failed.append(f"{pred_id}: artifact content does not contain expected substring (C7)")
                                continue
                        except Exception as e:
                            failed.append(f"{pred_id}: failed reading artifact: {e}")
                            continue
                    elif ptype_val == "FILE_CONTENT_EQUALS":
                        expected_full = pred.parameters.get("content") or pred.parameters.get("expected_content") or ""
                        try:
                            actual_text = tp.read_text(encoding="utf-8", errors="ignore")
                            if expected_full and actual_text.strip() != expected_full.strip():
                                failed.append(f"{pred_id}: artifact content does not match expected (C7)")
                                continue
                        except Exception as e:
                            failed.append(f"{pred_id}: failed reading artifact: {e}")
                            continue

            verified.append(pred_id)

        # 4. Presentation Check (C5)
        # Check if presentation was contractually requested
        pres_requested = (
            bool(goal_contract.entities.get("reveal_result"))
            or bool(goal_contract.entities.get("presentation_requested"))
            or bool(exec_state.get("presentation_requested"))
            or bool(exec_state.get("reveal_result"))
        )

        if pres_requested:
            # Must verify affirmative presentation in evidence_state or events
            pres_verified = False
            pres_ev = ev_state.get("presentation") or {}
            events = ev_state.get("events") or []

            # Check explicit presentation object
            if pres_ev.get("target_observed") and pres_ev.get("hwnd"):
                pres_verified = True
            else:
                # Check events list for RESULT_PRESENTED
                for ev in events:
                    if isinstance(ev, dict) and ev.get("event_type") == "RESULT_PRESENTED":
                        d = ev.get("data") or {}
                        if d.get("target_observed") and d.get("verified_hwnd"):
                            pres_verified = True
                            break

            if not pres_verified:
                failed.append("Presentation was requested but RESULT_PRESENTED was not verified (C5)")

        # 5. Resource Disposition Check (C6)
        # Check if any resources in resource_ledger or execution_state failed cleanup
        res_disposition = ev_state.get("resources") or {}
        if res_disposition.get("failed_cleanup") or res_disposition.get("failed_cleanup_count", 0) > 0:
            failed.append("Required resource cleanup failed (C6)")

        task_id_for_ledger = active_task_id or getattr(goal_contract, "contract_id", None)
        if task_id_for_ledger:
            try:
                from astrarun.tasks.resource_ledger import AstraResourceLedger, ResourceLifecycleState
                ledger = AstraResourceLedger.get_instance()
                task_res = ledger.list_resources_for_task(task_id_for_ledger)
                for r in task_res:
                    if r.lifecycle_state == ResourceLifecycleState.FAILED_CLEANUP:
                        failed.append(f"Resource {r.resource_id} ({r.resource_type}) is in FAILED_CLEANUP (C6)")
            except Exception:
                pass

        # 6. Final Authoritative Decision
        if missing or failed:
            status_desc = "FAILED_UNSATISFIED_POSTCONDITIONS" if failed else "FAILED_INCOMPLETE_POSTCONDITIONS"
            reasons = []
            if missing:
                reasons.append(f"Missing/unverified: {'; '.join(missing)}")
            if failed:
                reasons.append(f"Failed predicates: {'; '.join(failed)}")
            return CompletionGateResult(
                verdict=GateVerdict.REJECTED,
                can_complete=False,
                status=status_desc,
                message="; ".join(reasons),
                verified_predicates=verified,
                missing_predicates=missing,
                failed_predicates=failed,
                evidence_summary={"verified_count": len(verified), "missing_count": len(missing), "failed_count": len(failed)},
            )

        return CompletionGateResult(
            verdict=GateVerdict.APPROVED,
            can_complete=True,
            status="SUCCESS",
            message=f"All {len(verified)} required goal postconditions affirmatively verified.",
            verified_predicates=verified,
            missing_predicates=[],
            failed_predicates=[],
            evidence_summary={"verified_count": len(verified)},
        )
