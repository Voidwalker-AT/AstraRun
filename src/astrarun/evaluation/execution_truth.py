"""Execution-truth and completion-stage model for F0-24A.1.

Generic invariants:
- A successful intermediate action is NOT task completion.
- Planning validity is NOT physical execution.
- GOAL_COMPLETED requires ordered evidence stages with postconditions satisfied.
- Resource cleanup cannot report clean when unverified or failed.
- Pass-rate accounting never collapses partial success into a fake 100%.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionStage(str, Enum):
    """Ordered stages from plan acceptance to goal completion."""

    PLAN_VALID = "PLAN_VALID"
    ACTION_DISPATCHED = "ACTION_DISPATCHED"
    ACTION_SUCCEEDED = "ACTION_SUCCEEDED"
    STATE_OBSERVED = "STATE_OBSERVED"
    POSTCONDITION_SATISFIED = "POSTCONDITION_SATISFIED"
    RESOURCE_CLEANUP_VERIFIED = "RESOURCE_CLEANUP_VERIFIED"
    GOAL_COMPLETED = "GOAL_COMPLETED"


# Strict progression: each stage requires all prior stages.
_STAGE_ORDER: List[ExecutionStage] = [
    ExecutionStage.PLAN_VALID,
    ExecutionStage.ACTION_DISPATCHED,
    ExecutionStage.ACTION_SUCCEEDED,
    ExecutionStage.STATE_OBSERVED,
    ExecutionStage.POSTCONDITION_SATISFIED,
    ExecutionStage.RESOURCE_CLEANUP_VERIFIED,
    ExecutionStage.GOAL_COMPLETED,
]

_STAGE_RANK: Dict[ExecutionStage, int] = {s: i for i, s in enumerate(_STAGE_ORDER)}


@dataclass
class StageEvidence:
    stage: ExecutionStage
    satisfied: bool
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionTruthReport:
    case_id: str
    stages: List[StageEvidence] = field(default_factory=list)
    goal_completed: bool = False
    highest_stage: Optional[ExecutionStage] = None
    blocked_reason: str = ""

    @property
    def max_reached_rank(self) -> int:
        reached = [s for s in self.stages if s.satisfied]
        if not reached:
            return -1
        return max(_STAGE_RANK[s.stage] for s in reached)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "goal_completed": self.goal_completed,
            "highest_stage": self.highest_stage.value if self.highest_stage else None,
            "blocked_reason": self.blocked_reason,
            "stages": [
                {
                    "stage": s.stage.value,
                    "satisfied": s.satisfied,
                    "reason": s.reason,
                    "evidence": s.evidence,
                }
                for s in self.stages
            ],
        }


class ExecutionTruthOracle:
    """Evaluates whether completion may be claimed from staged evidence."""

    def evaluate(
        self,
        case_id: str,
        plan_valid: bool,
        action_dispatched: bool,
        action_succeeded: bool,
        state_observed: bool,
        postcondition_satisfied: bool,
        resource_cleanup_verified: bool,
        extra: Optional[Dict[str, Any]] = None,
    ) -> CompletionTruthReport:
        signals = {
            ExecutionStage.PLAN_VALID: (plan_valid, "Plan structural validation"),
            ExecutionStage.ACTION_DISPATCHED: (action_dispatched, "Action dispatched through broker"),
            ExecutionStage.ACTION_SUCCEEDED: (action_succeeded, "Action reported success"),
            ExecutionStage.STATE_OBSERVED: (state_observed, "Observed state after action"),
            ExecutionStage.POSTCONDITION_SATISFIED: (postcondition_satisfied, "Requested postconditions satisfied"),
            ExecutionStage.RESOURCE_CLEANUP_VERIFIED: (resource_cleanup_verified, "Task-owned resources verified clean"),
        }

        stages: List[StageEvidence] = []
        first_failed: Optional[ExecutionStage] = None
        highest: Optional[ExecutionStage] = None

        for stage in _STAGE_ORDER:
            if stage == ExecutionStage.GOAL_COMPLETED:
                break
            ok, label = signals[stage]
            stages.append(
                StageEvidence(
                    stage=stage,
                    satisfied=bool(ok),
                    reason=label if ok else f"{label}: missing or false",
                    evidence=dict(extra or {}),
                )
            )
            if not ok and first_failed is None:
                first_failed = stage
            if ok:
                highest = stage

        goal_completed = first_failed is None
        if goal_completed:
            stages.append(
                StageEvidence(
                    stage=ExecutionStage.GOAL_COMPLETED,
                    satisfied=True,
                    reason="All prior stages satisfied with evidence",
                    evidence=dict(extra or {}),
                )
            )
            highest = ExecutionStage.GOAL_COMPLETED
        else:
            stages.append(
                StageEvidence(
                    stage=ExecutionStage.GOAL_COMPLETED,
                    satisfied=False,
                    reason=f"Blocked at {first_failed.value}",
                    evidence=dict(extra or {}),
                )
            )

        return CompletionTruthReport(
            case_id=case_id,
            stages=stages,
            goal_completed=goal_completed,
            highest_stage=highest,
            blocked_reason="" if goal_completed else f"Incomplete stage chain at {first_failed.value if first_failed else 'unknown'}",
        )


_REQUIRED_RESIDUE_COUNT_KEYS = (
    "orphaned_processes",
    "orphaned_windows",
    "active_ledger_resources",
)


def evaluate_resource_cleanup(resource_delta: Optional[Dict[str, Any]]) -> StageEvidence:
    """
    Fail-closed resource-cleanup verification.

    PASS requires affirmative evidence, not missing-field defaults:
    - resources_owned is explicit True/False
    - cleanup_executed is explicit True when cleanup ran
    - residue measurements exist for process, window, and ledger counts
    - process lifecycle is verified when a task-owned process was required
    - no cleanup exception
    - all measured residue counts are zero

    Missing required measurements are UNKNOWN/FAIL, never inferred as zero/success.
    Zero-resource tasks must assert resources_owned=false plus measured residue zeros.
    """
    if resource_delta is None:
        return StageEvidence(
            stage=ExecutionStage.RESOURCE_CLEANUP_VERIFIED,
            satisfied=False,
            reason="No resource lifecycle evidence provided",
            evidence={"provided": False},
        )
    if not isinstance(resource_delta, dict):
        return StageEvidence(
            stage=ExecutionStage.RESOURCE_CLEANUP_VERIFIED,
            satisfied=False,
            reason="Resource lifecycle evidence must be a dict of affirmative measurements",
            evidence={"provided": True, "type": type(resource_delta).__name__},
        )

    reasons: List[str] = []
    evidence: Dict[str, Any] = {
        "provided": True,
        "resources_owned": resource_delta.get("resources_owned"),
        "process_cleanup_required": resource_delta.get("process_cleanup_required"),
        "process_residue_measured": resource_delta.get("process_residue_measured"),
        "window_residue_measured": resource_delta.get("window_residue_measured"),
        "ledger_residue_measured": resource_delta.get("ledger_residue_measured"),
        "cleanup_executed": resource_delta.get("cleanup_executed"),
        "process_cleaned_up": resource_delta.get("process_cleaned_up"),
        "cleanup_exception": resource_delta.get("cleanup_exception"),
    }

    if evidence["cleanup_exception"]:
        reasons.append(f"Cleanup raised exception: {evidence['cleanup_exception']}")

    resources_owned = evidence["resources_owned"]
    if resources_owned not in (True, False):
        reasons.append(
            "resources_owned is UNKNOWN/missing; ownership must be explicit "
            "(resources_owned=false for zero-resource tasks, true when task-owned resources exist)"
        )
    else:
        evidence["resources_owned"] = bool(resources_owned)

    if evidence["cleanup_executed"] is not True:
        reasons.append(
            "cleanup_executed is UNKNOWN/missing/false; affirmative cleanup execution is required"
        )

    process_cleanup_required = evidence["process_cleanup_required"]
    if process_cleanup_required not in (True, False):
        reasons.append(
            "process_cleanup_required is UNKNOWN/missing; declare whether process lifecycle cleanup was required"
        )

    for key in ("process_residue_measured", "window_residue_measured", "ledger_residue_measured"):
        if evidence[key] is not True:
            reasons.append(f"{key} is not true; residue must be measured, not inferred from missing fields")

    measured: Dict[str, Optional[int]] = {}
    for key in _REQUIRED_RESIDUE_COUNT_KEYS:
        raw = resource_delta.get(key, None)
        if raw is None:
            evidence[key] = None
            reasons.append(f"{key} is UNKNOWN/missing; zero cannot be inferred")
            continue
        try:
            count = int(raw)
        except (TypeError, ValueError):
            evidence[key] = raw
            reasons.append(f"{key} is not an integer measurement: {raw!r}")
            continue
        if count < 0:
            evidence[key] = count
            reasons.append(f"{key} measurement is negative: {count}")
            continue
        evidence[key] = count
        measured[key] = count
        if count > 0:
            reasons.append(f"{key} residue remains: {count}")

    if process_cleanup_required is True:
        process_cleaned_up = evidence["process_cleaned_up"]
        if process_cleaned_up is not True:
            reasons.append(
                "process_cleanup_required=true requires affirmative process_cleaned_up=true "
                f"(got {process_cleaned_up!r})"
            )
    elif process_cleanup_required is False and resources_owned is False:
        # Zero-resource path: process cleanup not required; process_cleaned_up optional.
        pass
    elif process_cleanup_required is False and resources_owned is True:
        # Resources owned but no process involved: residue count must still be measured as zero.
        if evidence["process_cleaned_up"] is False:
            reasons.append("process_cleaned_up=false contradicts process_cleanup_required=false")

    ok = not reasons
    return StageEvidence(
        stage=ExecutionStage.RESOURCE_CLEANUP_VERIFIED,
        satisfied=ok,
        reason="Cleanup verified with affirmative residue measurements" if ok else "; ".join(reasons),
        evidence=evidence,
    )


def resource_cleanup_verdict(resource_delta: Optional[Dict[str, Any]]) -> str:
    """PASS_CLEAN only when cleanup ran and left no contradiction or residue."""
    if resource_delta is None:
        return "FAIL"
    stage = evaluate_resource_cleanup(resource_delta)
    return "PASS_CLEAN" if stage.satisfied else "FAIL"


@dataclass
class DimensionOutcome:
    dimension: str
    planning: Optional[bool] = None
    execution: Optional[bool] = None
    verification: Optional[bool] = None
    cleanup: Optional[bool] = None


def summarize_case_outcomes(
    outcomes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Honest multi-dimensional generalization accounting.

    Never collapses planning/execution/verification/cleanup into a single
    invented 100% success number. 119/120 is reported as 119/120.
    """
    total = len(outcomes)
    if total == 0:
        return {
            "total_cases": 0,
            "passed_cases": 0,
            "failed_cases": 0,
            "fraction": "0/0",
            "pass_rate_pct": None,
            "planning_passed": 0,
            "execution_passed": 0,
            "verification_passed": 0,
            "cleanup_passed": 0,
            "dimensions_reported_separately": True,
            "combined_fake_100pct": False,
        }

    def _count(key: str) -> int:
        return sum(1 for o in outcomes if o.get(key) is True)

    passed = sum(1 for o in outcomes if o.get("passed") is True)
    failed = total - passed
    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": failed,
        "fraction": f"{passed}/{total}",
        "pass_rate_pct": round((passed / total) * 100.0, 4) if total else None,
        "planning_passed": _count("planning"),
        "execution_passed": _count("execution"),
        "verification_passed": _count("verification"),
        "cleanup_passed": _count("cleanup"),
        "false_completion_count": sum(1 for o in outcomes if o.get("false_completion") is True),
        "false_completion_rate_pct": round(
            (sum(1 for o in outcomes if o.get("false_completion") is True) / total) * 100.0, 4
        )
        if total
        else None,
        "dimensions_reported_separately": True,
        "combined_fake_100pct": False,
        "note": "Zero false completions is NOT overall success. Partial failures remain visible.",
    }


def assert_pass_rate_not_fabricated(passed: int, total: int, reported_pct: Optional[float]) -> List[str]:
    """Return accounting violations if a reported percentage misrepresents the fraction."""
    violations: List[str] = []
    if total <= 0:
        if reported_pct is not None and reported_pct > 0:
            violations.append("Non-zero pass rate reported for empty case set")
        return violations
    honest = (passed / total) * 100.0
    if passed < total and reported_pct is not None and reported_pct >= 100.0:
        violations.append(
            f"Reported {reported_pct}% implies perfect success but fraction is {passed}/{total} ({honest:.4f}%)"
        )
    if passed == total and reported_pct is not None and abs(reported_pct - 100.0) > 1e-9 and abs(reported_pct - honest) > 0.05:
        violations.append(f"Reported {reported_pct}% inconsistent with {passed}/{total}")
    if passed < total and reported_pct is not None and abs(reported_pct - honest) > 0.05:
        violations.append(f"Reported {reported_pct}% inconsistent with honest {honest:.4f}%")
    return violations
