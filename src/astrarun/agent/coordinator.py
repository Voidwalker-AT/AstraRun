"""AgentCoordinator: Central turn orchestrator for AstraRun 1.0 intelligent spine.

Orchestrates the entire user turn lifecycle:
INGESTED -> OBSERVED -> FAST_TRACK_OR_REASON -> DECIDED -> EXECUTING -> VERIFYING -> SYNTHESIZING -> COMPLETING -> COMMITTED

Invariants:
- AgentCoordinator owns no semantic domain knowledge.
- Models NEVER execute tools directly. All tool steps pass through ExecutionBroker + ActionGate.
- Deterministic systems govern and verify; models propose and synthesize.
- Zero raw shell or uncontrolled subprocess execution.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.agent.completion_gate import AuthoritativeCompletionGate
from astrarun.agent.fast_track import SingleStepFastTrack
from astrarun.agent.indexer import CapabilitySemanticIndex
from astrarun.agent.verifier import StepVerifier
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.cognition.turn_models import PlanStep, TurnDecision, TurnMode
from astrarun.cognition.turn_reasoner import TurnReasoner
from astrarun.cognition.sufficiency import (
    KnowledgeSufficiencyEvaluator,
    KnowledgeSufficiencyResult,
    SufficiencyReason,
)
from astrarun.cognition.acquisition import (
    InformationAcquisitionPlanner,
    AcquisitionPlan,
)
from astrarun.computer_use.world.summary import WorldStateAdapter, WorldStateSummary
from astrarun.core.logging import get_logger
from astrarun.ingress.models import RequestEnvelope
from astrarun.security.execution_broker import ActionCategory, ActionProposal, ExecutionBroker
from astrarun.session.events import (
    AcquisitionPlanCreatedEvent,
    AssistantResponseEvent,
    EventType,
    InformationNeedCreatedEvent,
    KnowledgeSufficiencyEvaluatedEvent,
    ReasoningDecisionEvent,
    SessionEvent,
    ToolCallEvent,
    ToolObservationEvent,
    TurnCompletedEvent,
    UserTurnEvent,
    VerificationEvent,
    WorldObservationEvent,
)
from astrarun.session.models import (
    ArtifactKind,
    ConversationSession,
    PinnedArtifact,
    TurnRecord,
)
from astrarun.session.store import SessionStore
from astrarun.agent.interruption import (
    InterruptionAssessment,
    InterruptionPolicyEngine,
    InterruptionType,
    WorldDriftDetector,
    WorldResourceSnapshot,
)

logger = get_logger("astrarun.agent.coordinator")


class TurnStatus(str, Enum):
    """Lifecycle status of a completed or paused turn."""
    SUCCESS = "SUCCESS"
    PAUSED_CONFIRMATION = "PAUSED_CONFIRMATION"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    # Extended Coordinator States (Objective B)
    PAUSED_USER_ACTIVE = "PAUSED_USER_ACTIVE"
    WORLD_STATE_CHANGED = "WORLD_STATE_CHANGED"
    REOBSERVING = "REOBSERVING"
    RECOVERING = "RECOVERING"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"
    # Phase 1: Information Acquisition State
    INFORMATION_REQUIRED = "INFORMATION_REQUIRED"


@dataclass
class TurnResult:
    """Strongly typed result returned from AgentCoordinator.handle_turn."""
    turn_id: str
    status: TurnStatus
    response_text: str
    decision: Optional[TurnDecision] = None
    tool_observations: List[Dict[str, Any]] = field(default_factory=list)
    artifacts_pinned: List[PinnedArtifact] = field(default_factory=list)
    session_id: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentCoordinator:
    """
    Unified intelligence coordinator orchestrating multi-turn conversation and governed OS actions.
    """

    _instance: Optional[AgentCoordinator] = None

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        broker: Optional[ExecutionBroker] = None,
        reasoner: Optional[TurnReasoner] = None,
        session_store: Optional[SessionStore] = None,
        indexer: Optional[CapabilitySemanticIndex] = None,
        verifier: Optional[StepVerifier] = None,
        drift_detector: Optional[WorldDriftDetector] = None,
        sufficiency_evaluator: Optional[KnowledgeSufficiencyEvaluator] = None,
        acquisition_planner: Optional[InformationAcquisitionPlanner] = None,
    ) -> None:
        self.registry = registry or CapabilityRegistry()
        self.broker = broker or ExecutionBroker(capability_registry=self.registry)
        self.reasoner = reasoner or TurnReasoner()
        self.session_store = session_store or SessionStore.get_instance()
        self.indexer = indexer or CapabilitySemanticIndex(registry=self.registry)
        self.verifier = verifier or StepVerifier()
        self.drift_detector = drift_detector or WorldDriftDetector()
        self.policy_engine = InterruptionPolicyEngine()
        self.sufficiency_evaluator = sufficiency_evaluator or KnowledgeSufficiencyEvaluator()
        self.acquisition_planner = acquisition_planner or InformationAcquisitionPlanner()

    @classmethod
    def get_instance(cls) -> AgentCoordinator:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def handle_turn(
        self,
        envelope: RequestEnvelope,
        session: Optional[ConversationSession] = None,
    ) -> TurnResult:
        """
        Execute a complete conversational or operational turn through the intelligence spine.
        """
        t0 = time.perf_counter()
        turn_id = f"turn-{uuid.uuid4().hex[:12]}"

        # 1. INGESTED: Ensure active session
        active_session = session or self.session_store.get_or_create(envelope.session_id)
        user_text = envelope.raw_query or envelope.normalized_query

        # Semantic Topic tracking & provenance
        turn_topic, is_new_topic = self._extract_turn_topic(user_text, active_session.get_active_topic())
        if turn_topic:
            active_session.set_active_topic(turn_topic)

        user_event = UserTurnEvent(
            session_id=active_session.session_id,
            turn_id=turn_id,
            user_text=user_text,
            origin=envelope.origin.value if hasattr(envelope.origin, "value") else str(envelope.origin),
        )
        self.session_store.record_event(user_event)

        # 2. OBSERVED: Acquire compact world state
        world_summary = WorldStateAdapter.get_current_summary(task_id=envelope.request_id)
        obs_event = WorldObservationEvent(
            session_id=active_session.session_id,
            turn_id=turn_id,
            foreground_app=world_summary.foreground_app or "",
            foreground_pid=world_summary.foreground_pid,
            visible_window_count=len(world_summary.visible_windows),
            modal_dialog_active=bool(world_summary.active_dialogs),
            task_id=envelope.request_id,
        )
        self.session_store.record_event(obs_event)

        # 3. KNOWLEDGE SUFFICIENCY & FAST_TRACK_OR_REASON
        fast_decision = SingleStepFastTrack.match(user_text)
        if fast_decision is not None:
            logger.debug("Turn %s resolved via SingleStepFastTrack: %s", turn_id, fast_decision.goal_summary)
            is_obs = any(
                step.capability_id in ("battery_status", "inspect_process")
                for step in fast_decision.plan_steps
            )
            suff_reason = (
                SufficiencyReason.SUFFICIENT_OBSERVABLE_STATE.value
                if is_obs
                else SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE.value
            )
            suff_expl = (
                "Workstation observation resolvable via authorized live capability on fast-track path."
                if is_obs
                else "Self-sufficient operational command on fast-track path."
            )
            suff_event = KnowledgeSufficiencyEvaluatedEvent(
                session_id=active_session.session_id,
                turn_id=turn_id,
                is_sufficient=True,
                reason=suff_reason,
                confidence=1.0,
                explanation=suff_expl,
                task_id=envelope.request_id,
            )
            self.session_store.record_event(suff_event)
            decision = fast_decision
        else:
            # 3A. Evaluate Knowledge Sufficiency (< 15ms local heuristic)
            sufficiency = self.sufficiency_evaluator.evaluate(
                query=user_text,
                session=active_session,
                world_state=world_summary,
            )
            suff_event = KnowledgeSufficiencyEvaluatedEvent(
                session_id=active_session.session_id,
                turn_id=turn_id,
                is_sufficient=sufficiency.is_sufficient,
                reason=sufficiency.reason.value,
                confidence=sufficiency.confidence,
                missing_aspects=sufficiency.missing_aspects,
                explanation=sufficiency.explanation,
                task_id=envelope.request_id,
            )
            self.session_store.record_event(suff_event)

            if not sufficiency.is_sufficient:
                # 3B. Formulate Information Acquisition Plan
                acq_plan = self.acquisition_planner.plan_acquisition(
                    query=user_text,
                    sufficiency=sufficiency,
                    session=active_session,
                )
                for need in acq_plan.needs:
                    need_ev = InformationNeedCreatedEvent(
                        session_id=active_session.session_id,
                        turn_id=turn_id,
                        need_id=need.need_id,
                        description=need.description,
                        need_type=need.need_type.value,
                        freshness=need.freshness.value,
                        authority=need.authority.value,
                        priority=need.priority,
                        privacy_sensitive=need.privacy_sensitive,
                        task_id=envelope.request_id,
                    )
                    self.session_store.record_event(need_ev)

                plan_ev = AcquisitionPlanCreatedEvent(
                    session_id=active_session.session_id,
                    turn_id=turn_id,
                    plan_id=acq_plan.plan_id,
                    need_count=len(acq_plan.needs),
                    evidence_request_count=len(acq_plan.evidence_requests),
                    target_sources=[s.identifier for r in acq_plan.evidence_requests for s in r.target_sources],
                    user_summary=acq_plan.user_summary,
                    task_id=envelope.request_id,
                )
                self.session_store.record_event(plan_ev)

                # Return structured INFORMATION_REQUIRED turn
                return self._commit_turn(
                    turn_id=turn_id,
                    status=TurnStatus.INFORMATION_REQUIRED,
                    user_text=user_text,
                    assistant_text=acq_plan.user_summary,
                    decision=TurnDecision(
                        mode=TurnMode.CLARIFY if sufficiency.reason == SufficiencyReason.AMBIGUOUS_GOAL else TurnMode.DIRECT_ANSWER,
                        assistant_reply=acq_plan.user_summary,
                        goal_summary=f"Information Acquisition Plan: {user_text}",
                        confidence=sufficiency.confidence,
                        model_role="ACQUISITION_PLANNER",
                        metadata={"acquisition_plan": acq_plan.to_dict()},
                    ),
                    session=active_session,
                    t0=t0,
                    envelope=envelope,
                    metadata={"acquisition_plan": acq_plan.to_dict()},
                )

            # Semantic retrieval for Top-6 capability schemas
            top_retrievals = self.indexer.retrieve(user_text, top_k=6)
            candidate_schemas = []
            for r in top_retrievals:
                schema = self.registry.get_capability_schema(r.capability_id)
                if schema:
                    candidate_schemas.append(schema)

            if sufficiency.observable_capability_id:
                obs_schema = self.registry.get_capability_schema(sufficiency.observable_capability_id)
                if obs_schema and all(s.id != obs_schema.id for s in candidate_schemas):
                    candidate_schemas.insert(0, obs_schema)

            decision = self.reasoner.reason_turn(
                query=user_text,
                session=active_session,
                world_state=world_summary,
                candidate_schemas=candidate_schemas,
            )

        # 4. DECIDED: Record reasoning decision event
        cap_ids = [step.capability_id for step in decision.plan_steps]
        reason_event = ReasoningDecisionEvent(
            session_id=active_session.session_id,
            turn_id=turn_id,
            decision_mode=decision.mode.value,
            selected_capability_ids=cap_ids,
            structured_arguments={s.capability_id: s.arguments for s in decision.plan_steps},
            goal_summary=decision.goal_summary or "",
            model_role=decision.model_role,
            confidence=decision.confidence,
            task_id=envelope.request_id,
        )
        self.session_store.record_event(reason_event)

        # 4A. Handle DIRECT_ANSWER
        if decision.mode == TurnMode.DIRECT_ANSWER:
            reply = decision.assistant_reply or "I have processed your request."
            return self._commit_turn(
                turn_id=turn_id,
                status=TurnStatus.SUCCESS,
                user_text=user_text,
                assistant_text=reply,
                decision=decision,
                session=active_session,
                t0=t0,
                envelope=envelope,
            )

        # 4B. Handle CLARIFY
        if decision.mode == TurnMode.CLARIFY:
            question = decision.clarification_question or decision.assistant_reply or "Could you please clarify your request?"
            active_session.active_clarification = question
            return self._commit_turn(
                turn_id=turn_id,
                status=TurnStatus.CLARIFICATION_REQUIRED,
                user_text=user_text,
                assistant_text=question,
                decision=decision,
                session=active_session,
                t0=t0,
                envelope=envelope,
            )

        # 4C. Handle REFUSE
        if decision.mode == TurnMode.REFUSE:
            refusal = decision.assistant_reply or "I cannot execute this request due to security policies."
            return self._commit_turn(
                turn_id=turn_id,
                status=TurnStatus.BLOCKED,
                user_text=user_text,
                assistant_text=refusal,
                decision=decision,
                session=active_session,
                t0=t0,
                envelope=envelope,
                error="REFUSED",
            )

        # 5. EXECUTING: Governed execution of plan steps via ExecutionBroker
        tool_observations: List[Dict[str, Any]] = []
        artifacts_pinned: List[PinnedArtifact] = []

        # Resolve pronoun references in arguments using semantic lineage
        self._resolve_conversational_references(decision, active_session, user_text)

        last_post_snap: Optional[WorldResourceSnapshot] = None

        for idx, step in enumerate(decision.plan_steps):
            # 5.0 VERIFY ASSUMPTIONS before continuing to dependent step N+1, or check pre-action takeover/drift at step 0
            if idx > 0 and last_post_snap is not None:
                assumptions_valid, pre_drift = self.drift_detector.verify_assumptions(
                    step_args=step.arguments,
                    last_snapshot=last_post_snap,
                )
                if not assumptions_valid and pre_drift:
                    logger.warning("Interruption detected before step %s: %s", step.step_id, pre_drift.details)
                    policy_outcome = self.policy_engine.apply_policy(
                        pre_drift, step.arguments, active_session
                    )
                    status_enum = getattr(TurnStatus, pre_drift.recommended_coordinator_state, TurnStatus.WAITING_CLARIFICATION)
                    return self._commit_turn(
                        turn_id=turn_id,
                        status=status_enum,
                        user_text=user_text,
                        assistant_text=policy_outcome["message"],
                        decision=decision,
                        session=active_session,
                        t0=t0,
                        envelope=envelope,
                        metadata={"interruption": policy_outcome, "step_id": step.step_id},
                    )
            elif idx == 0:
                # Pre-action check before step 0 begins: check for physical user takeover or active interruption
                initial_snap = self.drift_detector.capture_snapshot(step.arguments)
                if initial_snap.user_input_detected or self.drift_detector._simulated_fault:
                    pre_drift = self.drift_detector.detect_drift(
                        before=initial_snap,
                        after=initial_snap,
                        action_capability=step.capability_id,
                        target_info=step.arguments,
                    )
                    if pre_drift and pre_drift.has_drift:
                        logger.warning("Pre-action takeover/drift detected before step 0: %s", pre_drift.details)
                        policy_outcome = self.policy_engine.apply_policy(
                            pre_drift, step.arguments, active_session
                        )
                        status_enum = getattr(TurnStatus, pre_drift.recommended_coordinator_state, TurnStatus.WAITING_CLARIFICATION)
                        return self._commit_turn(
                            turn_id=turn_id,
                            status=status_enum,
                            user_text=user_text,
                            assistant_text=policy_outcome["message"],
                            decision=decision,
                            session=active_session,
                            t0=t0,
                            envelope=envelope,
                            metadata={"interruption": policy_outcome, "step_id": step.step_id},
                        )

            # 5.1 PRE-ACTION WORLD OBSERVATION
            pre_snap = self.drift_detector.capture_snapshot(step.arguments)

            # Auto-bind foreground HWND if window capability omitted target HWND
            if step.capability_id in ("snap_window_left", "snap_window_right", "maximize_window", "minimize_window"):
                if "hwnd" not in step.arguments or not step.arguments["hwnd"]:
                    step.arguments["hwnd"] = pre_snap.foreground_hwnd or 0

            # Emit ToolCallEvent
            call_ev = ToolCallEvent(
                session_id=active_session.session_id,
                turn_id=turn_id,
                capability_id=step.capability_id,
                arguments=step.arguments,
                task_id=envelope.request_id,
                step_id=step.step_id,
            )
            self.session_store.record_event(call_ev)

            # Broker invocation
            proposal = ActionProposal(
                capability_id=step.capability_id,
                parameters=step.arguments,
                task_id=envelope.request_id,
                step_id=step.step_id,
                source="coordinator",
                dry_run=envelope.dry_run,
            )

            broker_res = self.broker.execute(proposal)

            # 5A. Policy BLOCK - Governed security invariant takes precedence
            if broker_res.verdict == "BLOCK" or broker_res.blocked:
                obs_ev = ToolObservationEvent(
                    session_id=active_session.session_id,
                    turn_id=turn_id,
                    capability_id=step.capability_id,
                    success=False,
                    error=broker_res.message,
                    task_id=envelope.request_id,
                    step_id=step.step_id,
                )
                self.session_store.record_event(obs_ev)
                msg = f"Operation blocked by security governance: {broker_res.message}"
                return self._commit_turn(
                    turn_id=turn_id,
                    status=TurnStatus.BLOCKED,
                    user_text=user_text,
                    assistant_text=msg,
                    decision=decision,
                    session=active_session,
                    t0=t0,
                    envelope=envelope,
                    error=broker_res.message,
                )

            # 5B. Policy CONFIRM - Awaiting human consent
            if broker_res.verdict == "CONFIRM" or broker_res.requires_confirmation:
                active_session.active_confirmation = broker_res.confirmation_token
                obs_ev = ToolObservationEvent(
                    session_id=active_session.session_id,
                    turn_id=turn_id,
                    capability_id=step.capability_id,
                    success=False,
                    output_summary="Paused awaiting confirmation",
                    task_id=envelope.request_id,
                    step_id=step.step_id,
                )
                self.session_store.record_event(obs_ev)
                msg = f"This action requires confirmation: {broker_res.message}"
                return self._commit_turn(
                    turn_id=turn_id,
                    status=TurnStatus.PAUSED_CONFIRMATION,
                    user_text=user_text,
                    assistant_text=msg,
                    decision=decision,
                    session=active_session,
                    t0=t0,
                    envelope=envelope,
                    metadata={"confirmation_token": broker_res.confirmation_token},
                )

            # 5.2 POST-ACTION WORLD OBSERVATION & DRIFT DETECTION
            post_snap = self.drift_detector.capture_snapshot(step.arguments)
            last_post_snap = post_snap

            # 5.3 DRIFT & INTERRUPTION DETECTION
            drift_assessment = self.drift_detector.detect_drift(
                before=pre_snap,
                after=post_snap,
                action_capability=step.capability_id,
                target_info=step.arguments,
            )
            if drift_assessment and drift_assessment.has_drift:
                logger.warning("Interruption/drift detected after step %s: %s (%s)",
                               step.step_id, drift_assessment.interruption_type, drift_assessment.details)
                policy_outcome = self.policy_engine.apply_policy(
                    drift_assessment, step.arguments, active_session
                )
                status_enum = getattr(TurnStatus, drift_assessment.recommended_coordinator_state, TurnStatus.WAITING_CLARIFICATION)
                return self._commit_turn(
                    turn_id=turn_id,
                    status=status_enum,
                    user_text=user_text,
                    assistant_text=policy_outcome["message"],
                    decision=decision,
                    session=active_session,
                    t0=t0,
                    envelope=envelope,
                    metadata={"interruption": policy_outcome, "step_id": step.step_id},
                )

            # 5C. Execution Failure
            if not broker_res.success:
                obs_ev = ToolObservationEvent(
                    session_id=active_session.session_id,
                    turn_id=turn_id,
                    capability_id=step.capability_id,
                    success=False,
                    error=broker_res.message,
                    task_id=envelope.request_id,
                    step_id=step.step_id,
                )
                self.session_store.record_event(obs_ev)
                msg = f"Action execution failed: {broker_res.message}"
                return self._commit_turn(
                    turn_id=turn_id,
                    status=TurnStatus.FAILED,
                    user_text=user_text,
                    assistant_text=msg,
                    decision=decision,
                    session=active_session,
                    t0=t0,
                    envelope=envelope,
                    error=broker_res.message,
                )

            # 6. VERIFYING: Verify postconditions and pin artifacts
            verified, post_desc, pinned_art = self._verify_and_pin_artifact(
                step=step,
                broker_res=broker_res,
                turn_id=turn_id,
                dry_run=envelope.dry_run,
            )

            verif_ev = VerificationEvent(
                session_id=active_session.session_id,
                turn_id=turn_id,
                target=step.capability_id,
                strategy=step.expected_postconditions.get("strategy", "DEFAULT") if step.expected_postconditions else "DEFAULT",
                verified=verified,
                details={"message": post_desc},
                task_id=envelope.request_id,
                step_id=step.step_id,
            )
            self.session_store.record_event(verif_ev)

            if pinned_art:
                artifacts_pinned.append(pinned_art)
                active_session.pin_artifact(pinned_art.display_name, pinned_art)
                if pinned_art.kind == ArtifactKind.FILE:
                    active_session.pin_artifact("last_file", pinned_art)
                elif pinned_art.kind == ArtifactKind.APPLICATION:
                    active_session.pin_artifact("last_app", pinned_art)

            # Record ToolObservation
            summary_obs = {
                "capability_id": step.capability_id,
                "success": True,
                "verified": verified,
                "output_summary": broker_res.message,
                "data": broker_res.data,
            }
            if pinned_art and pinned_art.path:
                summary_obs["verified_path"] = pinned_art.path
            tool_observations.append(summary_obs)

            obs_ev = ToolObservationEvent(
                session_id=active_session.session_id,
                turn_id=turn_id,
                capability_id=step.capability_id,
                success=True,
                output_summary=broker_res.message,
                verified_path=pinned_art.path if pinned_art else None,
                task_id=envelope.request_id,
                step_id=step.step_id,
            )
            self.session_store.record_event(obs_ev)

        # 7. SYNTHESIZING: Formulate assistant response grounded in actual tool observations
        if tool_observations:
            assistant_reply = self.reasoner.synthesize_post_tool(
                query=user_text,
                decision=decision,
                tool_observations=tool_observations,
                session=active_session,
            )
        else:
            assistant_reply = decision.assistant_reply or "Action completed."

        # 8. COMPLETING & COMMITTING
        return self._commit_turn(
            turn_id=turn_id,
            status=TurnStatus.SUCCESS,
            user_text=user_text,
            assistant_text=assistant_reply,
            decision=decision,
            session=active_session,
            t0=t0,
            envelope=envelope,
            tool_observations=tool_observations,
            artifacts_pinned=artifacts_pinned,
        )

    def _commit_turn(
        self,
        turn_id: str,
        status: TurnStatus,
        user_text: str,
        assistant_text: str,
        decision: TurnDecision,
        session: ConversationSession,
        t0: float,
        envelope: RequestEnvelope,
        tool_observations: Optional[List[Dict[str, Any]]] = None,
        artifacts_pinned: Optional[List[PinnedArtifact]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TurnResult:
        """Record final events, update turn record in session, and return TurnResult."""
        duration_s = time.perf_counter() - t0
        meta = dict(metadata or {})
        meta["duration_s"] = duration_s
        meta["dry_run"] = envelope.dry_run

        # Record assistant response event
        resp_ev = AssistantResponseEvent(
            session_id=session.session_id,
            turn_id=turn_id,
            response_text=assistant_text,
            has_artifacts=bool(artifacts_pinned),
        )
        self.session_store.record_event(resp_ev)

        # Record turn completion event
        comp_ev = TurnCompletedEvent(
            session_id=session.session_id,
            turn_id=turn_id,
            turn_status=status.value,
            duration_s=duration_s,
            task_id=envelope.request_id,
        )
        self.session_store.record_event(comp_ev)

        # Extract conversational artifacts from assistant text for DIRECT_ANSWER and HYBRID
        conv_artifacts: List[PinnedArtifact] = []
        if decision.mode in (TurnMode.DIRECT_ANSWER, TurnMode.HYBRID_ACT_AND_ANSWER) and assistant_text:
            active_topic = session.get_active_topic() or "general"
            u_lower = user_text.lower()

            art_kind = ArtifactKind.EXPLANATION
            if any(w in u_lower for w in ("example", "snippet", "numerical", "concrete", "code")):
                art_kind = ArtifactKind.EXAMPLE
            elif "```" in assistant_text:
                art_kind = ArtifactKind.CODE

            art_id = f"art-conv-{turn_id}"
            conv_art = PinnedArtifact(
                artifact_id=art_id,
                kind=art_kind,
                display_name=f"{active_topic}_{art_kind.value.lower()}",
                verified_identity=turn_id,
                content=assistant_text,
                topic=active_topic,
                created_turn_id=turn_id,
                verified=True,
            )
            conv_artifacts.append(conv_art)
            session.pin_artifact(conv_art.display_name, conv_art)
            if art_kind in (ArtifactKind.EXAMPLE, ArtifactKind.CODE):
                session.pin_artifact("last_example", conv_art)
            elif art_kind == ArtifactKind.EXPLANATION:
                session.pin_artifact("last_explanation", conv_art)

        # Append TurnRecord to session
        tool_calls = [s.to_dict() for s in decision.plan_steps]
        turn_rec = TurnRecord(
            turn_id=turn_id,
            timestamp=time.time(),
            user_text=user_text,
            assistant_text=assistant_text,
            decision_mode=decision.mode.value,
            topic=session.get_active_topic(),
            conversational_artifacts=conv_artifacts,
            tool_calls=tool_calls,
            tool_observations=tool_observations or [],
            artifacts=artifacts_pinned or [],
            verified=(status == TurnStatus.SUCCESS),
            error_summary=error,
            metadata=meta,
        )
        session.add_turn(turn_rec)
        self._update_rolling_summary(session)
        self.session_store.save_session(session)
        self.drift_detector.reset_turn()

        return TurnResult(
            turn_id=turn_id,
            status=status,
            response_text=assistant_text,
            decision=decision,
            tool_observations=tool_observations or [],
            artifacts_pinned=artifacts_pinned or [],
            session_id=session.session_id,
            error=error,
            metadata=meta,
        )

    def _resolve_conversational_references(
        self,
        decision: TurnDecision,
        session: ConversationSession,
        query: str,
    ) -> None:
        """Resolve pronouns ('it', 'that', 'that example') using session context and pinned artifacts."""
        q_lower = query.lower()

        # Check for file resolution references: "open it", "open that"
        for step in decision.plan_steps:
            if step.capability_id in ("open_file", "reveal_file"):
                target_path = step.arguments.get("path") or ""
                if not target_path or target_path.lower() in ("it", "that", "the file", "that file"):
                    last_file = session.pinned_artifacts.get("last_file")
                    if last_file and last_file.path:
                        step.arguments["path"] = last_file.path
                        logger.debug("Resolved pronoun 'it' to pinned file path: %s", last_file.path)

            elif step.capability_id in ("write_file", "save_text_file"):
                # If writing content from prior conversation ("put that example in a text file")
                content = step.arguments.get("content") or step.arguments.get("text") or ""
                if not content or content.lower().strip() in ("that", "that example", "the example", "example", "it"):
                    resolved_art = session.resolve_conversational_artifact(content or query)
                    if resolved_art and resolved_art.content:
                        content = resolved_art.content
                        if "content" in step.arguments:
                            step.arguments["content"] = content
                        else:
                            step.arguments["text"] = content
                        logger.debug("Resolved pronoun to lineage artifact '%s' (topic=%s)",
                                     resolved_art.display_name, resolved_art.topic)
                    else:
                        for past_turn in reversed(session.turns):
                            if past_turn.assistant_text and len(past_turn.assistant_text) > 20:
                                content = past_turn.assistant_text
                                if "content" in step.arguments:
                                    step.arguments["content"] = content
                                else:
                                    step.arguments["text"] = content
                                break

    def _verify_and_pin_artifact(
        self,
        step: PlanStep,
        broker_res: Any,
        turn_id: str,
        dry_run: bool = False,
    ) -> tuple[bool, str, Optional[PinnedArtifact]]:
        """Empirically verify step consequences on the workstation and generate a PinnedArtifact."""
        cap_id = step.capability_id
        args = step.arguments

        # 1. File write
        if cap_id in ("write_file", "save_text_file"):
            path_str = args.get("path") or args.get("target")
            if not path_str:
                return False, "Missing path argument", None

            p = Path(path_str)
            if dry_run:
                art = PinnedArtifact(
                    artifact_id=f"art-{uuid.uuid4().hex[:8]}",
                    kind=ArtifactKind.FILE,
                    display_name=p.name,
                    verified_identity=str(p.resolve()),
                    path=str(p.resolve()),
                    created_turn_id=turn_id,
                    verified=True,
                    metadata={"dry_run": True},
                )
                return True, f"Simulated write to {p.name}", art

            if p.exists() and p.is_file():
                art = PinnedArtifact(
                    artifact_id=f"art-{uuid.uuid4().hex[:8]}",
                    kind=ArtifactKind.FILE,
                    display_name=p.name,
                    verified_identity=str(p.resolve()),
                    path=str(p.resolve()),
                    created_turn_id=turn_id,
                    verified=True,
                    metadata={"bytes": p.stat().st_size},
                )
                return True, f"Verified file on disk ({p.stat().st_size} bytes)", art
            return False, f"File {p} was not found on disk after write", None

        # 2. Application launch
        if cap_id == "open_application":
            app_name = args.get("app") or args.get("target") or "application"
            pid = broker_res.data.get("pid") if hasattr(broker_res, "data") else None
            art = PinnedArtifact(
                artifact_id=f"art-{uuid.uuid4().hex[:8]}",
                kind=ArtifactKind.APPLICATION,
                display_name=str(app_name),
                verified_identity=str(app_name),
                pid=pid,
                created_turn_id=turn_id,
                verified=True,
            )
            return True, f"Verified application '{app_name}' launch (pid={pid})", art

        # 3. File open
        if cap_id == "open_file":
            path_str = args.get("path")
            p = Path(path_str) if path_str else None
            art = PinnedArtifact(
                artifact_id=f"art-{uuid.uuid4().hex[:8]}",
                kind=ArtifactKind.FILE,
                display_name=p.name if p else "opened_file",
                verified_identity=str(p.resolve()) if p else "",
                path=str(p.resolve()) if p else None,
                created_turn_id=turn_id,
                verified=True,
            )
            return True, f"Opened file {p.name if p else ''}", art

        return True, "Executed successfully", None

    def _update_rolling_summary(self, session: ConversationSession) -> None:
        """Maintain compact rolling summary when conversation reaches 3+ turns."""
        if len(session.turns) <= 2:
            return
        first_topic = session.turns[0].topic or session.turns[0].user_text[:40]
        recent_topic = session.get_active_topic() or session.turns[-1].user_text[:40]
        session.rolling_summary = (
            f"Conversation started with '{first_topic}'. "
            f"Active topic: '{recent_topic}'. "
            f"Total turns: {len(session.turns)}."
        )

    @staticmethod
    def _extract_turn_topic(query: str, current_active_topic: Optional[str] = None) -> Tuple[Optional[str], bool]:
        """
        Extract the semantic topic from the query or maintain active topic for continuations.
        Returns: (topic_name, is_new_topic)
        """
        q = query.strip()
        q_lower = q.lower()

        # Continuation patterns (do NOT change topic)
        continuation_patterns = [
            r"^(?:give me|show me|provide)\s+(?:a\s+|an\s+)?(?:concrete\s+)?(?:numerical\s+)?(?:code\s+)?(?:tiny\s+)?(?:python\s+)?(?:example|snippet)",
            r"^(?:why\s+does\s+(?:that|it|this))",
            r"^(?:make\s+(?:the\s+explanation|that|it|this)\s+(?:shorter|concise|simpler))",
            r"^(?:put\s+that\s+example|save\s+that\s+example|write\s+that\s+example)",
            r"^(?:open\s+(?:it|that|the\s+file))",
            r"^(?:summarize\s+(?:that|it|this))",
            r"^(?:more\s+details|elaborate|continue)",
        ]
        for pat in continuation_patterns:
            if re.search(pat, q_lower):
                return current_active_topic, False

        # New topic patterns
        m = re.search(r"(?:now\s+)?(?:explain|what\s+is|what\s+are|tell\s+me\s+about|describe)\s+(?:why\s+)?(.+?)(?:\.|\?|$)", q_lower)
        if m:
            extracted = m.group(1).strip()
            extracted = re.sub(r"^(?:the\s+|a\s+|an\s+)", "", extracted)
            extracted = re.sub(r"\s+(?:matter|matters|works?)$", "", extracted)
            return extracted, True

        m2 = re.search(r"(?:i['\s]?m|i\s+am)\s+(?:studying|revising|learning|working\s+on)\s+(.+?)(?:\.|\?|\;|\,|$)", q_lower)
        if m2:
            return m2.group(1).strip(), True

        return current_active_topic, False
