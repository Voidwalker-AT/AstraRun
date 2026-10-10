"""Formal Multi-Dimensional Acceptance Model and Predicate Evaluator for Phase F0-23."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from astrarun.evaluation.execution_truth import (
    ExecutionStage,
    ExecutionTruthOracle,
    evaluate_resource_cleanup,
    summarize_case_outcomes,
)


class AcceptanceDimension(str, Enum):
    """Independent evaluation dimensions required for trustworthy task acceptance."""
    INTENT_CORRECTNESS = "INTENT_CORRECTNESS"
    ENTITY_CORRECTNESS = "ENTITY_CORRECTNESS"
    MODALITY_CORRECTNESS = "MODALITY_CORRECTNESS"
    PLAN_RELEVANCE = "PLAN_RELEVANCE"
    EXECUTION_REALITY = "EXECUTION_REALITY"
    STATE_TRANSITION_CORRECTNESS = "STATE_TRANSITION_CORRECTNESS"
    OUTPUT_CORRECTNESS = "OUTPUT_CORRECTNESS"
    SIDE_EFFECT_CLEANLINESS = "SIDE_EFFECT_CLEANLINESS"
    RESOURCE_CLEANUP = "RESOURCE_CLEANUP"
    SECURITY_COMPLIANCE = "SECURITY_COMPLIANCE"
    PROVENANCE = "PROVENANCE"


class InteractionModality(str, Enum):
    DIRECT_RESULT_ALLOWED = "DIRECT_RESULT_ALLOWED"
    APPLICATION_UI_REQUIRED = "APPLICATION_UI_REQUIRED"
    BROWSER_UI_REQUIRED = "BROWSER_UI_REQUIRED"
    SPECIFIC_TOOL_REQUIRED = "SPECIFIC_TOOL_REQUIRED"
    ANY_VALID_METHOD = "ANY_VALID_METHOD"


@dataclass
class AcceptancePredicate:
    """Strongly-typed acceptance predicate with explicit evidence grounding."""
    predicate_id: str
    name: str
    dimension: AcceptanceDimension
    evidence_source: str
    evaluator: str
    failure_reason: str
    is_mandatory: bool = True
    confidence: float = 1.0
    satisfied: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DimensionVerdict:
    dimension: AcceptanceDimension
    passed: bool
    score: float
    reasons: List[str] = field(default_factory=list)
    predicates_evaluated: int = 0
    predicates_passed: int = 0


@dataclass
class TaskAcceptanceReport:
    """Complete multi-dimensional acceptance report."""
    case_id: str
    prompt: str
    overall_verdict: str  # PASS | FAIL | BLOCKED | NOT_APPLICABLE
    passed: bool
    dimensions: Dict[str, DimensionVerdict] = field(default_factory=dict)
    predicates: List[AcceptancePredicate] = field(default_factory=list)
    unexpected_side_effects: List[Dict[str, Any]] = field(default_factory=list)
    security_provenance: Dict[str, Any] = field(default_factory=dict)
    resource_delta: Dict[str, Any] = field(default_factory=dict)
    model_provenance: Dict[str, Any] = field(default_factory=dict)
    summary_message: str = ""
    execution_truth: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "prompt": self.prompt,
            "overall_verdict": self.overall_verdict,
            "passed": self.passed,
            "dimensions": {k: asdict(v) for k, v in self.dimensions.items()},
            "predicates": [asdict(p) for p in self.predicates],
            "unexpected_side_effects": self.unexpected_side_effects,
            "security_provenance": self.security_provenance,
            "resource_delta": self.resource_delta,
            "model_provenance": self.model_provenance,
            "summary_message": self.summary_message,
            "execution_truth": self.execution_truth,
        }


class FormalAcceptanceOracle:
    """
    Evaluates whether an AstraRun task execution satisfies its acceptance contract
    across all 11 independent dimensions.
    """

    def evaluate(
        self,
        case_id: str,
        prompt: str,
        contract: Optional[Any],
        plan: Optional[Any],
        execution_trace: Optional[List[Dict[str, Any]]],
        pre_state: Optional[Dict[str, Any]] = None,
        post_state: Optional[Dict[str, Any]] = None,
        side_effects: Optional[List[Dict[str, Any]]] = None,
        security_log: Optional[List[Dict[str, Any]]] = None,
        resource_delta: Optional[Dict[str, Any]] = None,
        model_provenance: Optional[Dict[str, Any]] = None,
        custom_predicates: Optional[List[AcceptancePredicate]] = None,
    ) -> TaskAcceptanceReport:
        dim_verdicts: Dict[str, DimensionVerdict] = {}
        all_predicates: List[AcceptancePredicate] = custom_predicates or []

        # 1. INTENT CORRECTNESS
        intent_preds = [p for p in all_predicates if p.dimension == AcceptanceDimension.INTENT_CORRECTNESS]
        intent_passed = True
        intent_reasons = []
        if contract is None:
            intent_passed = False
            intent_reasons.append("GoalContract was null or missing")
        for p in intent_preds:
            if p.is_mandatory and not p.satisfied:
                intent_passed = False
                intent_reasons.append(p.failure_reason)
        dim_verdicts[AcceptanceDimension.INTENT_CORRECTNESS.value] = DimensionVerdict(
            dimension=AcceptanceDimension.INTENT_CORRECTNESS,
            passed=intent_passed,
            score=1.0 if intent_passed else 0.0,
            reasons=intent_reasons,
            predicates_evaluated=len(intent_preds),
            predicates_passed=sum(1 for p in intent_preds if p.satisfied),
        )

        # 2. ENTITY CORRECTNESS
        # Vacuous pass is forbidden: empty entity evidence is not proof of correct app identity.
        entity_preds = [p for p in all_predicates if p.dimension == AcceptanceDimension.ENTITY_CORRECTNESS]
        entity_reasons: List[str] = []
        if not entity_preds:
            entity_passed = False
            entity_reasons.append("ENTITY_CORRECTNESS has no evidence predicates; identity unverified")
        else:
            entity_passed = True
            for p in entity_preds:
                if p.is_mandatory and not p.satisfied:
                    entity_passed = False
                    entity_reasons.append(p.failure_reason)
        dim_verdicts[AcceptanceDimension.ENTITY_CORRECTNESS.value] = DimensionVerdict(
            dimension=AcceptanceDimension.ENTITY_CORRECTNESS,
            passed=entity_passed,
            score=1.0 if entity_passed else 0.0,
            reasons=entity_reasons,
            predicates_evaluated=len(entity_preds),
            predicates_passed=sum(1 for p in entity_preds if p.satisfied),
        )

        # 3. MODALITY CORRECTNESS
        modality_preds = [p for p in all_predicates if p.dimension == AcceptanceDimension.MODALITY_CORRECTNESS]
        modality_passed = True
        modality_reasons = []
        for p in modality_preds:
            if p.is_mandatory and not p.satisfied:
                modality_passed = False
                modality_reasons.append(p.failure_reason)
        dim_verdicts[AcceptanceDimension.MODALITY_CORRECTNESS.value] = DimensionVerdict(
            dimension=AcceptanceDimension.MODALITY_CORRECTNESS,
            passed=modality_passed,
            score=1.0 if modality_passed else 0.0,
            reasons=modality_reasons,
            predicates_evaluated=len(modality_preds),
            predicates_passed=sum(1 for p in modality_preds if p.satisfied),
        )

        # 4. PLAN RELEVANCE
        plan_preds = [p for p in all_predicates if p.dimension == AcceptanceDimension.PLAN_RELEVANCE]
        plan_passed = True
        plan_reasons = []
        for p in plan_preds:
            if p.is_mandatory and not p.satisfied:
                plan_passed = False
                plan_reasons.append(p.failure_reason)
        dim_verdicts[AcceptanceDimension.PLAN_RELEVANCE.value] = DimensionVerdict(
            dimension=AcceptanceDimension.PLAN_RELEVANCE,
            passed=plan_passed,
            score=1.0 if plan_passed else 0.0,
            reasons=plan_reasons,
            predicates_evaluated=len(plan_preds),
            predicates_passed=sum(1 for p in plan_preds if p.satisfied),
        )

        # 5. EXECUTION REALITY
        # Planning validity or an empty/absent trace is never physical execution evidence.
        exec_preds = [p for p in all_predicates if p.dimension == AcceptanceDimension.EXECUTION_REALITY]
        exec_reasons: List[str] = []
        exec_passed = True
        has_execution_trace = bool(execution_trace)
        if not has_execution_trace:
            exec_passed = False
            exec_reasons.append(
                "EXECUTION_REALITY failed: no execution trace provided (planning is not execution)"
            )
        if not exec_preds:
            exec_passed = False
            exec_reasons.append("EXECUTION_REALITY has no evidence predicates; physical execution unverified")
        for p in exec_preds:
            if p.is_mandatory and not p.satisfied:
                exec_passed = False
                exec_reasons.append(p.failure_reason)
        dim_verdicts[AcceptanceDimension.EXECUTION_REALITY.value] = DimensionVerdict(
            dimension=AcceptanceDimension.EXECUTION_REALITY,
            passed=exec_passed,
            score=1.0 if exec_passed else 0.0,
            reasons=exec_reasons,
            predicates_evaluated=len(exec_preds),
            predicates_passed=sum(1 for p in exec_preds if p.satisfied),
        )

        # 6. STATE TRANSITION CORRECTNESS
        st_preds = [p for p in all_predicates if p.dimension == AcceptanceDimension.STATE_TRANSITION_CORRECTNESS]
        st_passed = True
        st_reasons = []
        for p in st_preds:
            if p.is_mandatory and not p.satisfied:
                st_passed = False
                st_reasons.append(p.failure_reason)
        dim_verdicts[AcceptanceDimension.STATE_TRANSITION_CORRECTNESS.value] = DimensionVerdict(
            dimension=AcceptanceDimension.STATE_TRANSITION_CORRECTNESS,
            passed=st_passed,
            score=1.0 if st_passed else 0.0,
            reasons=st_reasons,
            predicates_evaluated=len(st_preds),
            predicates_passed=sum(1 for p in st_preds if p.satisfied),
        )

        # 7. OUTPUT CORRECTNESS
        out_preds = [p for p in all_predicates if p.dimension == AcceptanceDimension.OUTPUT_CORRECTNESS]
        out_passed = True
        out_reasons = []
        for p in out_preds:
            if p.is_mandatory and not p.satisfied:
                out_passed = False
                out_reasons.append(p.failure_reason)
        dim_verdicts[AcceptanceDimension.OUTPUT_CORRECTNESS.value] = DimensionVerdict(
            dimension=AcceptanceDimension.OUTPUT_CORRECTNESS,
            passed=out_passed,
            score=1.0 if out_passed else 0.0,
            reasons=out_reasons,
            predicates_evaluated=len(out_preds),
            predicates_passed=sum(1 for p in out_preds if p.satisfied),
        )

        # 8. SIDE-EFFECT CLEANLINESS
        unexpected_se: List[Dict[str, Any]] = []
        if side_effects:
            for se in side_effects:
                if se.get("is_unexpected", False) or se.get("category") == "UNREQUESTED_CONSEQUENTIAL":
                    unexpected_se.append(se)
        se_passed = len(unexpected_se) == 0
        se_reasons = [f"Unrequested side effect: {se.get('action')}" for se in unexpected_se]
        dim_verdicts[AcceptanceDimension.SIDE_EFFECT_CLEANLINESS.value] = DimensionVerdict(
            dimension=AcceptanceDimension.SIDE_EFFECT_CLEANLINESS,
            passed=se_passed,
            score=1.0 if se_passed else 0.0,
            reasons=se_reasons,
            predicates_evaluated=len(side_effects or []),
            predicates_passed=len((side_effects or [])) - len(unexpected_se),
        )

        # 9. RESOURCE CLEANUP
        # Missing delta, uncleaned process, cleanup exception, or never-executed cleanup => FAIL.
        r_delta = resource_delta or {}
        cleanup_stage = evaluate_resource_cleanup(resource_delta)
        cleanup_passed = cleanup_stage.satisfied
        cleanup_reasons = [] if cleanup_passed else [cleanup_stage.reason]
        dim_verdicts[AcceptanceDimension.RESOURCE_CLEANUP.value] = DimensionVerdict(
            dimension=AcceptanceDimension.RESOURCE_CLEANUP,
            passed=cleanup_passed,
            score=1.0 if cleanup_passed else 0.0,
            reasons=cleanup_reasons,
            predicates_evaluated=1,
            predicates_passed=1 if cleanup_passed else 0,
        )

        # 10. SECURITY COMPLIANCE
        sec_passed = True
        sec_reasons = []
        if security_log:
            for s in security_log:
                if s.get("bypassed", False) or not s.get("gate_authorized", True):
                    sec_passed = False
                    sec_reasons.append(f"Security mediation failure on step: {s.get('action')}")
        dim_verdicts[AcceptanceDimension.SECURITY_COMPLIANCE.value] = DimensionVerdict(
            dimension=AcceptanceDimension.SECURITY_COMPLIANCE,
            passed=sec_passed,
            score=1.0 if sec_passed else 0.0,
            reasons=sec_reasons,
            predicates_evaluated=len(security_log or []),
            predicates_passed=sum(1 for s in (security_log or []) if s.get("gate_authorized", True) and not s.get("bypassed", False)),
        )

        # 11. PROVENANCE
        prov_passed = True
        prov_reasons = []
        if model_provenance and model_provenance.get("fabricated", False):
            prov_passed = False
            prov_reasons.append("Model inference or execution evidence was fabricated")
        dim_verdicts[AcceptanceDimension.PROVENANCE.value] = DimensionVerdict(
            dimension=AcceptanceDimension.PROVENANCE,
            passed=prov_passed,
            score=1.0 if prov_passed else 0.0,
            reasons=prov_reasons,
            predicates_evaluated=1,
            predicates_passed=1 if prov_passed else 0,
        )

        all_passed = all(dv.passed for dv in dim_verdicts.values())
        overall_verdict = "PASS" if all_passed else "FAIL"

        fail_msgs = []
        for dv in dim_verdicts.values():
            if not dv.passed:
                fail_msgs.extend([f"[{dv.dimension.value}] {r}" for r in dv.reasons])

        summary = "All 11 acceptance dimensions satisfied." if all_passed else "; ".join(fail_msgs)

        # Staged completion truth: PASS may only claim GOAL_COMPLETED when the full chain holds.
        truth = ExecutionTruthOracle().evaluate(
            case_id=case_id,
            plan_valid=dim_verdicts.get(AcceptanceDimension.PLAN_RELEVANCE.value, DimensionVerdict(
                dimension=AcceptanceDimension.PLAN_RELEVANCE, passed=False, score=0.0
            )).passed,
            action_dispatched=has_execution_trace,
            action_succeeded=dim_verdicts.get(AcceptanceDimension.EXECUTION_REALITY.value, DimensionVerdict(
                dimension=AcceptanceDimension.EXECUTION_REALITY, passed=False, score=0.0
            )).passed,
            state_observed=dim_verdicts.get(AcceptanceDimension.STATE_TRANSITION_CORRECTNESS.value, DimensionVerdict(
                dimension=AcceptanceDimension.STATE_TRANSITION_CORRECTNESS, passed=False, score=0.0
            )).passed or dim_verdicts.get(AcceptanceDimension.OUTPUT_CORRECTNESS.value, DimensionVerdict(
                dimension=AcceptanceDimension.OUTPUT_CORRECTNESS, passed=False, score=0.0
            )).passed,
            postcondition_satisfied=dim_verdicts.get(AcceptanceDimension.OUTPUT_CORRECTNESS.value, DimensionVerdict(
                dimension=AcceptanceDimension.OUTPUT_CORRECTNESS, passed=False, score=0.0
            )).passed,
            resource_cleanup_verified=cleanup_passed,
            extra={"overall_verdict": overall_verdict},
        )
        # Dimensional FAIL must never be upgraded by staged truth.
        if not all_passed:
            truth.goal_completed = False
            if truth.blocked_reason == "":
                truth.blocked_reason = "One or more acceptance dimensions failed"
        if not truth.goal_completed and overall_verdict == "PASS":
            overall_verdict = "FAIL"
            all_passed = False
            summary = "Overall PASS blocked by incomplete execution-truth stage chain."

        return TaskAcceptanceReport(
            case_id=case_id,
            prompt=prompt,
            overall_verdict=overall_verdict,
            passed=all_passed,
            dimensions=dim_verdicts,
            predicates=all_predicates,
            unexpected_side_effects=unexpected_se,
            security_provenance={"events": security_log or [], "status": "AUTHORIZED" if sec_passed else "VIOLATION"},
            resource_delta=r_delta,
            model_provenance=model_provenance or {},
            summary_message=summary,
            execution_truth=truth.to_dict(),
        )


def summarize_generalization_cases(case_outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Public helper: honest multi-dimensional generalization accounting."""
    return summarize_case_outcomes(case_outcomes)
