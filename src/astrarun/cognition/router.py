"""Cognitive Router and Dynamic Orchestrator for AstraRun 1.0.

Implements the cheap-first cognitive hierarchy:
  1. Deterministic / Fuzzy / Laya pre-gate bypasses neural inference completely.
  2. Fast cognitive tier (Spark-X2.5 on :8090) handles intent, skills, and parameter binding.
  3. Deep cognitive tier (Qwen2.5-Coder on :8089) handles multi-step DAG planning and code.
  4. Structured escalation with anti-ping-pong guards.
  5. Mode-D structured failure recovery with bounded retry ceilings.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from astrarun.cognition.client import ModelClient
from astrarun.cognition.context import ContextBudgetManager
from astrarun.cognition.models import (
    ClarificationRequest,
    InferenceObservation,
    InferenceRequest,
    IntentDecision,
    ModelRole,
    PlanDAG,
    PlanStep,
    RecoveryDecision,
    SkillSelection,
)
from astrarun.cognition.residency import ModelResidencyManager
from astrarun.core.logging import get_logger
from astrarun.security.secret_broker import SecretBroker

logger = get_logger("astrarun.cognition.router")


class CognitiveRouter:
    """
    Central cognitive routing and planning coordinator.
    Routes queries to Fast (Spark) vs Deep (Qwen), enforces schema contracts,
    handles handoffs/escalations, and orchestrates Mode-D failure recovery.
    """

    def __init__(
        self,
        client: Optional[ModelClient] = None,
        residency_manager: Optional[ModelResidencyManager] = None,
        context_manager: Optional[ContextBudgetManager] = None,
        secret_broker: Optional[SecretBroker] = None,
        fast_endpoint: str = "http://127.0.0.1:8090",
        deep_endpoint: str = "http://127.0.0.1:8089",
        max_recovery_retries: int = 2,
    ) -> None:
        self.client = client or ModelClient()
        self.residency = residency_manager or ModelResidencyManager.get_instance()
        self.context_manager = context_manager or ContextBudgetManager()
        self.secret_broker = secret_broker or SecretBroker.get_instance()
        self.fast_endpoint = fast_endpoint
        self.deep_endpoint = deep_endpoint
        self.max_recovery_retries = max_recovery_retries

    # =========================================================================
    # 1. Cognitive Decision Routing (Fast Path)
    # =========================================================================

    async def route_and_interpret(
        self,
        user_prompt: str,
        context_data: Optional[Dict[str, Any]] = None,
        task_id: str = "task_route",
    ) -> tuple[IntentDecision, Optional[InferenceObservation]]:
        """
        Fast cognitive interpretation using Spark-X2.5.
        Extracts user intent, parameters, and flags whether deep planning is required.
        """
        system_prompt = (
            "You are AstraRun's Fast Cognitive Kernel. Classify the user query into a clean intent. "
            "Respond ONLY with a JSON object conforming to IntentDecision: "
            '{"intent": str, "confidence": float, "is_compound": bool, "entities": dict, "reasoning": str, "requires_deep_planning": bool}.'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Query: {user_prompt}\nContext: {context_data or {}}"},
        ]

        req = InferenceRequest(
            task_id=task_id,
            role=ModelRole.FAST,
            messages=messages,
            temperature=0.1,
            max_tokens=256,
        )

        obs = await self.client.complete(req, self.fast_endpoint, response_model=IntentDecision)

        if obs.is_success and obs.parsed_output:
            decision = IntentDecision.model_validate(obs.parsed_output)
            return decision, obs

        # If Fast model schema failed or was unparseable, fall back to safe fallback decision
        logger.warning("Fast model failed or emitted invalid schema (%s). Constructing fallback.", obs.status)
        fallback = IntentDecision(
            intent="unknown",
            confidence=0.3,
            is_compound=False,
            entities={"raw": user_prompt},
            reasoning=f"Fast cognitive parsing failed: {obs.failure_reason}",
            requires_deep_planning=True,  # Escalate to Deep model
        )
        return fallback, obs

    # =========================================================================
    # 2. Deep Planning (PlanDAG)
    # =========================================================================

    async def generate_plan_dag(
        self,
        goal: str,
        available_capabilities: List[Dict[str, Any]],
        context_data: Optional[Dict[str, Any]] = None,
        task_id: str = "task_plan",
    ) -> tuple[Optional[PlanDAG], InferenceObservation]:
        """
        Deep multi-step DAG planning using Qwen2.5-Coder.
        Emits a strictly validated PlanDAG with dependencies and dataflow.
        """
        system_prompt = (
            "You are AstraRun's Deep Autonomous Planner. Translate the goal into a deterministic PlanDAG. "
            "Every step must have a unique 'step_id', a valid 'capability', typed 'arguments', and 'dependencies'. "
            "NEVER produce cycles. Output ONLY a valid JSON object matching PlanDAG."
        )

        caps_summary = "\n".join(f"- {c.get('id')}: {c.get('description')}" for c in available_capabilities)
        user_content = f"Goal: {goal}\nAvailable Capabilities:\n{caps_summary}\nContext: {context_data or {}}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        req = InferenceRequest(
            task_id=task_id,
            role=ModelRole.DEEP,
            messages=messages,
            temperature=0.2,
            max_tokens=1024,
        )

        obs = await self.client.complete(req, self.deep_endpoint, response_model=PlanDAG)

        if obs.is_success and obs.parsed_output:
            try:
                plan = PlanDAG.model_validate(obs.parsed_output)
                plan.validate_graph()
                return plan, obs
            except Exception as e:
                obs.status = "SCHEMA_INVALID"
                obs.schema_valid = False
                obs.failure_reason = f"Graph validation failed: {str(e)}"
                return None, obs

        return None, obs

    # =========================================================================
    # 3. Escalation: Spark -> Qwen
    # =========================================================================

    async def execute_cognitive_turn(
        self,
        query: str,
        available_capabilities: List[Dict[str, Any]],
        context_data: Optional[Dict[str, Any]] = None,
        task_id: str = "task_turn",
    ) -> tuple[Optional[PlanDAG], List[InferenceObservation]]:
        """
        Execute full cognitive turn:
        1. Fast intent interpretation via Spark.
        2. Escalates to Qwen if deep planning is required, confidence is low, or task is compound.
        3. Enforces anti-ping-pong guards.
        """
        observations: List[InferenceObservation] = []

        # 1. Fast Model Pass
        intent_dec, fast_obs = await self.route_and_interpret(query, context_data, task_id=task_id)
        if fast_obs:
            observations.append(fast_obs)

        # Check Escalation Triggers
        should_escalate = (
            intent_dec.requires_deep_planning
            or intent_dec.confidence < 0.65
            or intent_dec.is_compound
            or intent_dec.intent == "unknown"
        )

        if not should_escalate:
            # Construct a lightweight, single-step PlanDAG directly from Spark's decision
            step = PlanStep(
                step_id="step_1",
                capability=intent_dec.intent,
                arguments=intent_dec.entities,
                risk_hint="LOW",
            )
            simple_dag = PlanDAG(
                goal=query,
                steps=[step],
            )
            return simple_dag, observations

        # 2. Deep Model Escalation (One-way: Spark -> Qwen, preventing ping-pong)
        logger.info("Escalating task %s to Deep Model (reason: confidence=%.2f, deep=%s, compound=%s)",
                    task_id, intent_dec.confidence, intent_dec.requires_deep_planning, intent_dec.is_compound)

        deep_dag, deep_obs = await self.generate_plan_dag(query, available_capabilities, context_data, task_id=task_id)
        if deep_obs:
            observations.append(deep_obs)

        return deep_dag, observations

    # =========================================================================
    # 4. Mode-D Failure Recovery
    # =========================================================================

    async def plan_recovery(
        self,
        failed_step: PlanStep,
        error_message: str,
        remaining_goal: str,
        retry_count: int,
        available_capabilities: List[Dict[str, Any]],
        task_id: str = "task_recovery",
    ) -> tuple[RecoveryDecision, InferenceObservation]:
        """
        Mode-D Recovery: structured replan proposition on step failure.
        Evaluated on structured action, not prose.
        """
        if retry_count >= self.max_recovery_retries:
            logger.warning("Max recovery retries (%d) reached for task %s. Aborting.", self.max_recovery_retries, task_id)
            rec = RecoveryDecision(
                failed_step_id=failed_step.step_id,
                error_code="MAX_RETRIES_EXCEEDED",
                diagnosis=f"Exhausted {self.max_recovery_retries} recovery attempts",
                recovery_action="ABORT",
                can_retry=False,
                retry_count=retry_count,
            )
            obs = InferenceObservation(model_id="rule_engine", status="SUCCESS", schema_valid=True)
            return rec, obs

        system_prompt = (
            "You are AstraRun's Mode-D Failure Recovery Specialist. A plan step failed during execution. "
            "Analyze the failure and propose a structured RecoveryDecision in JSON: "
            '{"failed_step_id": str, "error_code": str, "diagnosis": str, "recovery_action": str, '
            '"new_step": optional PlanStep, "remaining_goal": str, "can_retry": bool, "retry_count": int}.'
        )

        user_content = (
            f"Failed Step: {failed_step.model_dump()}\n"
            f"Error Observation: {error_message}\n"
            f"Remaining Goal: {remaining_goal}\n"
            f"Current Retry Count: {retry_count}\n"
            f"Capabilities: {[c.get('id') for c in available_capabilities]}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        req = InferenceRequest(
            task_id=task_id,
            role=ModelRole.DEEP,
            messages=messages,
            temperature=0.2,
            max_tokens=512,
        )

        obs = await self.client.complete(req, self.deep_endpoint, response_model=RecoveryDecision)

        if obs.is_success and obs.parsed_output:
            decision = RecoveryDecision.model_validate(obs.parsed_output)
            decision.retry_count = retry_count + 1
            if decision.retry_count > self.max_recovery_retries:
                decision.can_retry = False
                decision.recovery_action = "ABORT"
            return decision, obs

        # Fallback if recovery synthesis failed
        fallback_rec = RecoveryDecision(
            failed_step_id=failed_step.step_id,
            error_code="RECOVERY_MODEL_FAILED",
            diagnosis="Recovery model produced invalid output",
            recovery_action="ABORT",
            can_retry=False,
            retry_count=retry_count + 1,
        )
        return fallback_rec, obs
