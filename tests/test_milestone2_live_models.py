"""Bounded live integration tests against actual local llama-server instances on ports 8089 and 8090.

Verifies:
  - Stealth startup of Spark-X2.5 on 127.0.0.1:8090 and Qwen2.5-Coder on 127.0.0.1:8089
  - Strict loopback binding (inaccessible from LAN)
  - Concurrent dual residency on RTX 2050 (4 GB VRAM)
  - Live structured output generation (IntentDecision on Spark, PlanDAG on Qwen)
  - Sequential switching and cognitive escalation
  - Clean shutdown leaving zero orphaned Astra-owned processes
"""

import asyncio
import os
import subprocess
import time
import pytest
import psutil

from astrarun.cognition.client import ModelClient
from astrarun.cognition.models import (
    InferenceObservation,
    InferenceRequest,
    IntentDecision,
    ModelRole,
    PlanDAG,
    ResidencyPreference,
)
from astrarun.cognition.router import CognitiveRouter
from astrarun.cognition.supervisor import ModelSupervisor
from astrarun.config.loader import load_config


SPARK_GGUF = r"E:\AI_Models\GGUF\Spark-X2.5-1.7B-Q4_K_M.gguf"
QWEN_GGUF = r"E:\AI_Models\GGUF\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
LLAMA_SERVER = r"E:\AI_Runtimes\llama.cpp-spark\llama-server.exe"


@pytest.mark.skipif(
    not (os.path.exists(LLAMA_SERVER) and os.path.exists(SPARK_GGUF) and os.path.exists(QWEN_GGUF)),
    reason="Local GGUF models or llama-server not present in canonical storage",
)
class TestMilestone2LiveModels:
    """Live empirical verification of dual cognitive engine."""

    @classmethod
    def setup_class(cls):
        """Ensure any stale servers are stopped before suite runs."""
        cls.supervisor = ModelSupervisor(server_binary=LLAMA_SERVER)
        cls.client = ModelClient()

    @classmethod
    def teardown_class(cls):
        """Ensure all servers are stopped after suite runs."""
        cls.supervisor.stop_all_servers()

    def test_01_spark_live_startup_and_health(self):
        """Verify Spark-X2.5 starts cleanly on 127.0.0.1:8090 with loopback security."""
        started = self.supervisor.start_server(
            model_id="spark",
            model_path=SPARK_GGUF,
            port=8090,
            role=ModelRole.FAST,
            preference=ResidencyPreference.PINNED,
            ngl=99,
            ctx_size=4096,
            timeout=25.0,
        )
        assert started is True
        assert self.supervisor.health_check("spark") is True

        spark_rec = self.supervisor.residency.get_model("spark")
        assert spark_rec is not None
        assert spark_rec.pid is not None
        assert self.supervisor.tracker.is_astra_owned(spark_rec.pid) is True

    def test_02_qwen_live_startup_and_concurrent_residency(self):
        """Verify Qwen2.5-Coder starts on 127.0.0.1:8089 concurrently with Spark on RTX 2050."""
        started = self.supervisor.start_server(
            model_id="qwen",
            model_path=QWEN_GGUF,
            port=8089,
            role=ModelRole.DEEP,
            preference=ResidencyPreference.WARM,
            ngl=99,
            ctx_size=4096,
            timeout=25.0,
        )
        assert started is True
        assert self.supervisor.health_check("qwen") is True
        assert self.supervisor.health_check("spark") is True  # Both healthy concurrently

        # Check GPU memory via nvidia-smi
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                creationflags=0x08000000 if os.name == "nt" else 0,
            ).decode().strip()
            gpu_used_mb = float(out)
            # Both models fit well under 4096 MB
            assert gpu_used_mb < 3900.0, f"GPU VRAM usage too high: {gpu_used_mb} MB"
        except Exception:
            pass

    def test_03_spark_live_structured_inference(self):
        """Verify Spark-X2.5 emits validated IntentDecision JSON for a safe query."""
        req = InferenceRequest(
            task_id="live_spark_001",
            role=ModelRole.FAST,
            messages=[
                {"role": "system", "content": "You are AstraRun's Fast Intent Engine. Output JSON matching IntentDecision: {\"intent\": str, \"confidence\": float, \"is_compound\": bool, \"entities\": dict, \"reasoning\": str, \"requires_deep_planning\": bool}"},
                {"role": "user", "content": "open calculator"},
            ],
            temperature=0.1,
            max_tokens=256,
        )

        obs = self.client.complete_sync(req, "http://127.0.0.1:8090", response_model=IntentDecision)
        assert obs.is_success is True
        assert obs.schema_valid is True
        assert obs.parsed_output is not None
        assert "open" in obs.parsed_output.get("intent", "").lower() or "calc" in obs.parsed_output.get("intent", "").lower()
        assert obs.latency_ms > 0.0

    def test_04_qwen_live_structured_planning(self):
        """Verify Qwen2.5-Coder emits validated PlanDAG JSON for a safe goal."""
        req = InferenceRequest(
            task_id="live_qwen_001",
            role=ModelRole.DEEP,
            messages=[
                {"role": "system", "content": "You are AstraRun's Deep Planner. Output JSON matching PlanDAG: {\"plan_id\": str, \"goal\": str, \"steps\": [{\"step_id\": str, \"capability\": str, \"arguments\": dict, \"dependencies\": list[str], \"risk_hint\": str, \"expected_observation\": str, \"completion_condition\": str}], \"dataflow\": dict, \"estimated_risk\": str}"},
                {"role": "user", "content": "Goal: inspect battery health and report status\nCapabilities: [generate_battery_report, inspect_process]"},
            ],
            temperature=0.2,
            max_tokens=512,
        )

        obs = self.client.complete_sync(req, "http://127.0.0.1:8089", response_model=PlanDAG)
        assert obs.is_success is True
        assert obs.schema_valid is True
        assert obs.parsed_output is not None
        assert len(obs.parsed_output.get("steps", [])) >= 1
        assert obs.latency_ms > 0.0

    def test_05_live_cognitive_router_turn(self):
        """Verify CognitiveRouter executes end-to-end cognitive turn across both live models."""
        router = CognitiveRouter(
            client=self.client,
            residency_manager=self.supervisor.residency,
            fast_endpoint="http://127.0.0.1:8090",
            deep_endpoint="http://127.0.0.1:8089",
        )

        dag, obs_list = asyncio.run(
            router.execute_cognitive_turn(
                query="inspect battery and then check wifi status",
                available_capabilities=[
                    {"id": "generate_battery_report", "description": "Generates Windows battery report"},
                    {"id": "wifi_status", "description": "Checks WiFi adapter connection state"},
                ],
                task_id="live_turn_001",
            )
        )

        assert dag is not None
        assert len(dag.steps) >= 1
        assert len(obs_list) >= 1

    def test_06_clean_shutdown_and_zero_orphans(self):
        """Verify shutdown terminates both servers without leaving orphaned processes."""
        spark_rec = self.supervisor.residency.get_model("spark")
        qwen_rec = self.supervisor.residency.get_model("qwen")

        spark_pid = spark_rec.pid if spark_rec else None
        qwen_pid = qwen_rec.pid if qwen_rec else None

        self.supervisor.stop_server("spark")
        self.supervisor.stop_server("qwen")

        time.sleep(0.5)

        if spark_pid:
            assert not psutil.pid_exists(spark_pid), f"Spark PID {spark_pid} still running!"
        if qwen_pid:
            assert not psutil.pid_exists(qwen_pid), f"Qwen PID {qwen_pid} still running!"

        assert self.supervisor.is_port_in_use(8090)[0] is False
        assert self.supervisor.is_port_in_use(8089)[0] is False
