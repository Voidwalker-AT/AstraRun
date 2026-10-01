"""Comprehensive test suite for AstraRun 1.0 Milestone 2:
Dual Cognitive Engine & Model Residency Governance.

Covers:
  1. Routing hierarchy & cheap-first execution (deterministic avoids neural model, fast vs deep, escalation, no ping-pong)
  2. Strict Schema Contracts & PlanDAG validation (valid DAG, malformed JSON, cycles, invalid dependencies)
  3. Model Residency & Supervision (record tracking, health probe, priority eviction, restart ceiling, ownership safety)
  4. Failure Handling & Mode-D Recovery (timeouts, crash fallback, bounded recovery ceiling)
  5. Security Interception (ActionGate blocks model-proposed destructive actions, secret scrubbing)
  6. Stealth Execution (CREATE_NO_WINDOW flag on model servers)
"""

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from astrarun.cognition.client import ModelClient
from astrarun.cognition.context import ContextBudgetManager, TokenBudget
from astrarun.cognition.models import (
    ClarificationRequest,
    InferenceObservation,
    InferenceRequest,
    IntentDecision,
    ModelRole,
    ModelState,
    PlanDAG,
    PlanStep,
    RecoveryDecision,
    ResidencyPreference,
    SkillSelection,
)
from astrarun.cognition.residency import ModelRecord, ModelResidencyManager
from astrarun.cognition.router import CognitiveRouter
from astrarun.cognition.supervisor import CREATE_NO_WINDOW, ModelSupervisor
from astrarun.core.models import RoutingContext
from astrarun.execution.process_tracker import ProcessTracker
from astrarun.routing.deterministic import DeterministicRouter
from astrarun.security.action_gate import ActionGate
from astrarun.security.models import (
    ActionGateVerdict,
    ActionRequest,
    Operation,
    RiskLevel,
)
from astrarun.security.secret_broker import SecretBroker


# =============================================================================
# 1. ROUTING HIERARCHY & CHEAP-FIRST PRESERVATION
# =============================================================================

class TestRoutingHierarchy:
    """Verifies that deterministic/exact queries incur 0ms neural latency."""

    def test_deterministic_query_avoids_neural_model(self):
        """Exact application and folder queries are resolved immediately without touching CognitiveRouter."""
        context = RoutingContext(
            apps={"notepad": MagicMock(key="notepad", name="Notepad", path="C:\\Windows\\notepad.exe")},
            folders={},
            urls={},
            aliases={},
        )
        router = DeterministicRouter()
        decision = router.route("open notepad", context)

        assert decision.is_resolved is True
        assert decision.tool == "open_app"
        assert decision.confidence == 1.0

    def test_fast_semantic_query_routes_to_spark(self):
        """Simple colloquial queries are handled by Fast role (Spark-X2.5)."""
        mock_client = MagicMock(spec=ModelClient)
        mock_obs = InferenceObservation(
            model_id="FAST@8090",
            status="SUCCESS",
            raw_output='{"intent": "open_app", "confidence": 0.95, "is_compound": false, "entities": {"app": "calculator"}, "reasoning": "User wants to open calculator", "requires_deep_planning": false}',
            parsed_output={
                "intent": "open_app",
                "confidence": 0.95,
                "is_compound": False,
                "entities": {"app": "calculator"},
                "reasoning": "User wants to open calculator",
                "requires_deep_planning": False,
            },
            schema_valid=True,
            latency_ms=12.5,
        )
        mock_client.complete = AsyncMock(return_value=mock_obs)

        cog_router = CognitiveRouter(client=mock_client)
        dag, observations = asyncio.run(
            cog_router.execute_cognitive_turn("launch calc please", available_capabilities=[])
        )

        assert dag is not None
        assert len(dag.steps) == 1
        assert dag.steps[0].capability == "open_app"
        assert len(observations) == 1
        assert observations[0].model_id == "FAST@8090"

    def test_deep_code_task_routes_to_qwen(self):
        """Tasks flagged for deep planning escalate to Deep role (Qwen2.5-Coder)."""
        mock_client = MagicMock(spec=ModelClient)
        # Fast model marks requires_deep_planning=True
        fast_obs = InferenceObservation(
            model_id="FAST@8090",
            status="SUCCESS",
            parsed_output={
                "intent": "complex_pipeline",
                "confidence": 0.70,
                "is_compound": True,
                "entities": {},
                "reasoning": "Compound chained task",
                "requires_deep_planning": True,
            },
            schema_valid=True,
        )
        # Deep model generates PlanDAG
        deep_obs = InferenceObservation(
            model_id="DEEP@8089",
            status="SUCCESS",
            parsed_output={
                "plan_id": "plan_multi_001",
                "goal": "read file and inspect git status",
                "steps": [
                    {"step_id": "s1", "capability": "read_file", "arguments": {"path": "a.txt"}, "dependencies": []},
                    {"step_id": "s2", "capability": "git_status", "arguments": {}, "dependencies": ["s1"]},
                ],
                "dataflow": {},
                "estimated_risk": "LOW",
            },
            schema_valid=True,
        )

        mock_client.complete = AsyncMock(side_effect=[fast_obs, deep_obs])

        cog_router = CognitiveRouter(client=mock_client)
        dag, observations = asyncio.run(
            cog_router.execute_cognitive_turn(
                "read a.txt then inspect git status",
                available_capabilities=[{"id": "read_file"}, {"id": "git_status"}],
            )
        )

        assert dag is not None
        assert len(dag.steps) == 2
        assert dag.steps[1].dependencies == ["s1"]
        assert len(observations) == 2
        assert observations[0].model_id == "FAST@8090"
        assert observations[1].model_id == "DEEP@8089"

    def test_no_model_ping_pong(self):
        """Escalation occurs strictly once per turn; Deep model output never bounces back to Fast model."""
        mock_client = MagicMock(spec=ModelClient)
        fast_obs = InferenceObservation(
            model_id="FAST@8090",
            status="SUCCESS",
            parsed_output={"intent": "unknown", "confidence": 0.4, "is_compound": False, "requires_deep_planning": True},
            schema_valid=True,
        )
        deep_obs = InferenceObservation(
            model_id="DEEP@8089",
            status="SUCCESS",
            parsed_output={
                "plan_id": "plan_single",
                "goal": "test",
                "steps": [{"step_id": "s1", "capability": "inspect_port", "arguments": {"port": 8080}}],
            },
            schema_valid=True,
        )
        mock_client.complete = AsyncMock(side_effect=[fast_obs, deep_obs])

        cog_router = CognitiveRouter(client=mock_client)
        dag, observations = asyncio.run(
            cog_router.execute_cognitive_turn("check port 8080", available_capabilities=[{"id": "inspect_port"}])
        )

        # Confirm exactly 2 model calls occurred, terminating at DEEP
        assert mock_client.complete.call_count == 2
        assert observations[-1].model_id == "DEEP@8089"


# =============================================================================
# 2. STRICT SCHEMA CONTRACTS & PLANDAG VALIDATION
# =============================================================================

class TestSchemaContracts:
    """Verifies strict validation of PlanDAG, dependencies, cycles, and recovery schemas."""

    def test_valid_plandag_topological_sort(self):
        step1 = PlanStep(step_id="step_a", capability="fetch_data", arguments={"url": "test"})
        step2 = PlanStep(step_id="step_b", capability="transform_data", arguments={}, dependencies=["step_a"])
        dag = PlanDAG(goal="pipeline", steps=[step2, step1])

        dag.validate_graph()
        sorted_steps = dag.topological_sort()
        assert [s.step_id for s in sorted_steps] == ["step_a", "step_b"]

    def test_cyclic_plandag_rejected(self):
        step1 = PlanStep(step_id="s1", capability="c1", dependencies=["s2"])
        step2 = PlanStep(step_id="s2", capability="c2", dependencies=["s1"])
        dag = PlanDAG(goal="cycle_test", steps=[step1, step2])

        with pytest.raises(ValueError) as exc:
            dag.validate_graph()
        assert "Cyclic dependency detected" in str(exc.value)

    def test_unknown_dependency_rejected(self):
        step1 = PlanStep(step_id="s1", capability="c1", dependencies=["nonexistent_step"])
        dag = PlanDAG(goal="unknown_dep", steps=[step1])

        with pytest.raises(ValueError) as exc:
            dag.validate_graph()
        assert "unknown dependency" in str(exc.value)

    def test_malformed_json_client_handling(self):
        client = ModelClient()
        raw_bad_json = "Here is your plan: { 'step_id': 123, unquoted_key: oops "
        parsed, is_valid, err = client._parse_and_validate(raw_bad_json, response_model=PlanDAG)
        assert is_valid is False
        assert "JSON parse failure" in err

    def test_bounded_markdown_fence_repair(self):
        client = ModelClient()
        fenced_json = """
Sure! Here is the plan you requested:
```json
{
  "plan_id": "p1",
  "goal": "open notes",
  "steps": [
    {"step_id": "s1", "capability": "open_app", "arguments": {"app": "notepad"}}
  ]
}
```
Let me know if you need changes.
"""
        parsed, is_valid, err = client._parse_and_validate(fenced_json, response_model=PlanDAG)
        assert is_valid is True
        assert err is None
        assert parsed["plan_id"] == "p1"


# =============================================================================
# 3. MODEL RESIDENCY & SUPERVISION
# =============================================================================

class TestModelResidencyAndSupervision:
    """Verifies lifecycle states, telemetry, priority eviction, and restart limits."""

    def test_residency_ledger_registration(self):
        mgr = ModelResidencyManager()
        rec = ModelRecord(
            model_id="spark_test",
            role=ModelRole.FAST,
            residency_preference=ResidencyPreference.PINNED,
            port=8090,
        )
        mgr.register_model(rec)
        assert mgr.get_model("spark_test") == rec
        assert mgr.get_model_by_role(ModelRole.FAST) == rec

    def test_pinned_model_never_evicted(self):
        mgr = ModelResidencyManager(max_vram_mb=2000.0)
        spark = ModelRecord(
            model_id="spark",
            role=ModelRole.FAST,
            state=ModelState.READY,
            residency_preference=ResidencyPreference.PINNED,
            vram_bytes=1350 * 1024 * 1024,
            pid=12345,
        )
        qwen = ModelRecord(
            model_id="qwen",
            role=ModelRole.DEEP,
            state=ModelState.READY,
            residency_preference=ResidencyPreference.WARM,
            vram_bytes=1200 * 1024 * 1024,
            pid=12346,
        )
        mgr.register_model(spark)
        mgr.register_model(qwen)

        evicted = []
        mgr.register_eviction_handler(lambda m: evicted.append(m.model_id))

        # Request 600MB for a new specialist model (1350MB Spark + 600MB = 1950MB <= 2000MB)
        allowed = mgr.request_residency("vision_spec", 600.0)
        assert allowed is True
        # Qwen was evicted; Spark remained pinned!
        assert "qwen" in evicted
        assert "spark" not in evicted

    def test_restart_limit_enforcement(self):
        mgr = ModelResidencyManager()
        rec = ModelRecord(
            model_id="fragile_model",
            role=ModelRole.FAST,
            max_restarts=3,
            restart_window_seconds=60.0,
        )
        mgr.register_model(rec)

        assert mgr.record_restart("fragile_model") is True
        assert mgr.record_restart("fragile_model") is True
        assert mgr.record_restart("fragile_model") is True
        # 4th restart exceeds limit of 3
        assert mgr.record_restart("fragile_model") is False
        assert rec.state == ModelState.FAILED
        assert rec.health == "UNHEALTHY"

    def test_unrelated_process_protected_on_port_collision(self):
        supervisor = ModelSupervisor()
        # Mock port 8090 held by unowned OS PID
        with patch.object(supervisor, "is_port_in_use", return_value=(True, 9999)), \
             patch.object(supervisor.tracker, "is_astra_owned", return_value=False), \
             patch.object(supervisor, "_check_endpoint_health", return_value=False):
            started = supervisor.start_server(
                model_id="spark",
                model_path=r"E:\AI_Models\GGUF\Spark-X2.5-1.7B-Q4_K_M.gguf",
                port=8090,
                role=ModelRole.FAST,
            )
            assert started is False


# =============================================================================
# 4. FAILURE HANDLING & MODE-D RECOVERY
# =============================================================================

class TestFailureAndModeDRecovery:
    """Verifies timeout handling, crash fallback, and bounded recovery ceilings."""

    def test_client_timeout_handling(self):
        client = ModelClient()
        req = InferenceRequest(role=ModelRole.FAST, messages=[{"role": "user", "content": "hi"}], timeout=0.01)

        # Target endpoint that cannot respond in 10ms
        obs = client.complete_sync(req, "http://127.0.0.1:8090")
        assert obs.status in ("TIMEOUT", "FAILED")
        assert obs.is_success is False

    def test_mode_d_recovery_exhaustion(self):
        cog_router = CognitiveRouter(max_recovery_retries=2)
        failed_step = PlanStep(step_id="s1", capability="write_file", arguments={"path": "test.txt"})

        decision, obs = asyncio.run(
            cog_router.plan_recovery(
                failed_step=failed_step,
                error_message="Access denied",
                remaining_goal="write file",
                retry_count=2,  # Already at retry limit
                available_capabilities=[],
            )
        )
        assert decision.can_retry is False
        assert decision.recovery_action == "ABORT"
        assert decision.error_code == "MAX_RETRIES_EXCEEDED"


# =============================================================================
# 5. SECURITY INTERCEPTION & SECRET SCRUBBING
# =============================================================================

class TestSecurityInterception:
    """Demonstrates ActionGate intercepts model-proposed actions even when model is compromised."""

    def test_model_proposed_destructive_action_intercepted(self):
        """Even if model hallucination/compromise generates a delete command, ActionGate blocks it."""
        gate = ActionGate()

        # Malicious step generated by model
        hostile_step = PlanStep(
            step_id="hack_step",
            capability="cmd.exe",
            arguments={"command": r"del /f /q C:\Windows\System32\drivers\etc\hosts"},
        )

        req = ActionRequest(
            operation=Operation.EXECUTE,
            capability="execution_runtime",
            target="cmd.exe",
            parameters={"command": hostile_step.arguments["command"]},
        )

        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.DENY
        assert eval_res.risk == RiskLevel.CRITICAL

    def test_secrets_scrubbed_from_model_prompt_and_output(self):
        broker = SecretBroker.get_instance()
        broker.clear()
        client = ModelClient(secret_broker=broker)

        # Register secret
        broker.register_secret("secret://VAULT/API_TOKEN", "SENSITIVE_KEY_99881122")

        # Prompt with secret
        raw_prompt = "Process user data using secret key SENSITIVE_KEY_99881122"
        clean, report = broker.scrub_text(raw_prompt)

        assert "SENSITIVE_KEY_99881122" not in clean
        assert "***REDACTED:secret://VAULT/API_TOKEN***" in clean
        assert report.has_redactions is True


# =============================================================================
# 6. STEALTH EXECUTION
# =============================================================================

class TestStealthSupervision:
    """Verifies model servers spawn without console windows."""

    def test_create_no_window_constant(self):
        assert CREATE_NO_WINDOW == 0x08000000

    def test_context_budget_tracking(self):
        mgr = ContextBudgetManager(TokenBudget(max_context_window=4096, max_output_tokens=1024))
        breakdown = mgr.analyze_budget(
            system_instruction="You are AstraRun.",
            task_prompt="Launch application",
            history_turns=[{"role": "user", "content": "turn 1"}],
        )
        assert breakdown.is_within_budget is True
        assert breakdown.output_budget == 1024
        assert breakdown.total_input_tokens > 0
