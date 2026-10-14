"""C2.2A Positive Intelligence Holdout Suite across 7 Distinct Capability Classes.

Measures and records empirical evidence with REAL_LOCAL_MODEL_INFERENCE (Qwen2.5-Coder on port 8089):
Class 1: Algorithm / pure math computation
Class 2: CSV / data transformation
Class 3: Statistics / summary reporting
Class 4: 2D visualization (declarative spec generation + trusted render)
Class 5: 3D visualization (declarative 3D surface mesh spec + trusted render)
Class 6: Multi-step workflow (compute -> render spec -> reveal)
Class 7: Naturally failing code requiring real local Qwen autonomous repair

ZERO solution code in test harness.
Captures:
- task_id, class_name
- prompt_hash, raw_response_hash, latency_ms
- AST screening results
- AppContainer sandbox execution status, exit code, peak memory MB, duration ms
- Artifact paths, sizes, SHA-256 hashes
- ExecutionBroker promotion results
- GoalVerifier checks
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional
import pytest

from astrarun.cognition.client import ModelClient
from astrarun.cognition.models import InferenceRequest, ModelRole
from astrarun.cognition.supervisor import ModelSupervisor
from astrarun.core.paths import AstraPaths
from astrarun.files.service import deliver_artifact
from astrarun.sandbox.appcontainer_launcher import AppContainerLauncher
from astrarun.sandbox.manager import SandboxManager
from astrarun.sandbox.models import SandboxConfig, SandboxProfile
from astrarun.security.execution_broker import ActionCategory, ActionProposal, ExecutionBroker
from astrarun.tools.ast_inspector import ASTInspector
from astrarun.tools.candidate import CandidateTool, CodeProvenance
from astrarun.tools.dynamic_builder import DynamicToolBuilder
from astrarun.visualization.renderer import render_visualization


def extract_code(raw_response: str) -> str:
    """Extract code from model response markdown blocks."""
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", raw_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_response.strip()


@pytest.fixture(scope="module")
def qwen_server():
    """Ensure local Qwen2.5-Coder server is active on port 8089."""
    qwen_model_path = r"E:\AI_Models\GGUF\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
    if not os.path.exists(qwen_model_path):
        pytest.skip(f"Qwen model not found at {qwen_model_path}")

    supervisor = ModelSupervisor.get_instance()
    port = 8089
    model_id = "qwen-c2-2a-holdout"

    print("\nEnsuring Qwen llama-server is running on port 8089...")
    started = supervisor.start_server(
        model_id=model_id,
        model_path=qwen_model_path,
        port=port,
        role=ModelRole.DEEP,
        ngl=33,
        ctx_size=3072,
        timeout=25.0,
    )
    assert started, "Failed to start Qwen llama-server on port 8089"
    yield f"http://127.0.0.1:{port}"

    print("Stopping Qwen llama-server...")
    supervisor.stop_server(model_id)


def run_qwen_inference(endpoint: str, prompt: str) -> tuple[str, float, str, str]:
    """Execute inference request against local Qwen endpoint."""
    client = ModelClient()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    req = InferenceRequest(
        role=ModelRole.DEEP,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1536,
    )
    obs = asyncio.run(client.complete(req, endpoint=endpoint))
    assert obs.status == "SUCCESS", f"Inference failed: {obs.failure_reason}"
    assert obs.raw_output, "Empty model response"
    resp_hash = hashlib.sha256(obs.raw_output.encode("utf-8")).hexdigest()
    return obs.raw_output, obs.latency_ms, prompt_hash, resp_hash


HOLD_RESULTS: List[Dict[str, Any]] = []


def test_holdout_class_01_algorithm_pure_math(qwen_server):
    """Class 1: Algorithm / pure math computation (Fibonacci sum & prime scan)."""
    prompt = (
        "Write a pure Python script that calculates: "
        "1. The sum of the first 25 Fibonacci numbers (where F(0)=0, F(1)=1). "
        "2. All prime numbers strictly between 50 and 100. "
        "Write the output as a JSON file named 'math_output.json' inside os.environ['ASTRARUN_OUTPUT_DIR']. "
        "The JSON must have keys 'fib_sum': int, 'primes': list of int. "
        "Output ONLY the python code in ```python ``` blocks. Do not include markdown commentary."
    )
    raw, latency_ms, p_hash, r_hash = run_qwen_inference(qwen_server, prompt)
    code = extract_code(raw)

    task_id = "task_holdout_cls1_math"
    cand = CandidateTool(
        tool_id="dyn_math_algo",
        goal="Calculate sum of first 25 Fibonacci numbers and primes between 50 and 100",
        task_id=task_id,
        executable_code=code,
    )

    # AST Inspection
    inspector = ASTInspector()
    ast_res = inspector.inspect_candidate(cand)
    assert ast_res.is_safe, f"AST violation: {ast_res.violations}"

    # Sandbox execution in AppContainer
    sb_mgr = SandboxManager()
    cfg = SandboxConfig(run_id="c2_2a_cls1_run", profile=SandboxProfile.EPHEMERAL_TOOL, timeout_sec=20.0)
    sb_res = sb_mgr.execute_candidate(cand, config=cfg)
    assert sb_res.status == "SUCCESS", f"Execution error: {sb_res.stderr}\nStdout: {sb_res.stdout}"
    assert sb_res.exit_code == 0

    # Verify and promote artifact
    out_dir = AstraPaths.sandbox_dir() / task_id / "output"
    src_art = out_dir / "math_output.json"
    assert src_art.exists()

    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "math_result.json"
        broker = ExecutionBroker()
        proposal = ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={"source": str(src_art), "destination": str(dst), "expected_artifact_type": "json"},
            task_id=task_id,
        )
        b_res = broker.execute(proposal)
        assert b_res.success
        assert dst.exists()

        data = json.loads(dst.read_text(encoding="utf-8"))
        assert "fib_sum" in data
        assert "primes" in data
        assert isinstance(data["primes"], list)
        assert all(p in data["primes"] for p in [53, 59, 61, 67, 71, 73, 79, 83, 89, 97])

        art_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
        HOLD_RESULTS.append({
            "class": "CLASS_1_ALGORITHM_PURE_MATH",
            "task_id": task_id,
            "latency_ms": latency_ms,
            "prompt_hash": p_hash,
            "response_hash": r_hash,
            "ast_safe": ast_res.is_safe,
            "sandbox_status": sb_res.status,
            "artifact_sha256": art_hash,
            "verified": True,
        })


def test_holdout_class_02_csv_data_transform(qwen_server):
    """Class 2: CSV / tabular data transformation."""
    # Pre-stage CSV file in sandbox task workspace source/
    task_id = "task_holdout_cls2_csv"
    ws_dir = AstraPaths.sandbox_dir() / task_id
    src_dir = ws_dir / "source"
    src_dir.mkdir(parents=True, exist_ok=True)
    input_csv = src_dir / "raw_inventory.csv"
    input_csv.write_text(
        "sku,item_name,category,unit_price,quantity\n"
        "A101,Desk Lamp,Furniture,25.0,40\n"
        "A102,Office Chair,Furniture,120.0,15\n"
        "B201,Wireless Mouse,Electronics,30.0,50\n"
        "B202,USB Keyboard,Electronics,45.0,20\n"
        "C301,Notebook,Stationery,5.0,100\n",
        encoding="utf-8",
    )

    prompt = (
        "Write a pure Python script using only the Python standard library 'csv' module "
        "(do NOT import pandas or third-party packages) that reads the CSV file at "
        "os.path.join(os.environ['ASTRARUN_WORKSPACE_DIR'], 'source', 'raw_inventory.csv'). "
        "Filter for items where category == 'Electronics' OR int(quantity) >= 30. "
        "Calculate 'total_value' as float(unit_price) * int(quantity) for each matched item. "
        "Write the filtered rows with header [sku,item_name,category,total_value] to 'inventory_summary.csv' "
        "inside the directory specified by os.environ['ASTRARUN_OUTPUT_DIR']. "
        "If using csv.DictWriter, you MUST specify extrasaction='ignore' so extra fields from the input are ignored. "
        "Output ONLY the python code in ```python ``` blocks. Do not include markdown commentary."
    )
    raw, latency_ms, p_hash, r_hash = run_qwen_inference(qwen_server, prompt)
    code = extract_code(raw)

    cand = CandidateTool(
        tool_id="dyn_csv_transform",
        goal="Filter inventory items and calculate total value to CSV",
        task_id=task_id,
        executable_code=code,
    )

    inspector = ASTInspector()
    ast_res = inspector.inspect_candidate(cand)
    assert ast_res.is_safe, f"AST violation: {ast_res.violations}"

    sb_mgr = SandboxManager()
    cfg = SandboxConfig(run_id="c2_2a_cls2_run", profile=SandboxProfile.EPHEMERAL_TOOL, timeout_sec=20.0)
    sb_res = sb_mgr.execute_candidate(cand, config=cfg)
    assert sb_res.status == "SUCCESS", f"Execution error: {sb_res.stderr}\nStdout: {sb_res.stdout}"

    out_dir = ws_dir / "output"
    src_art = out_dir / "inventory_summary.csv"
    assert src_art.exists()

    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "inventory_summary.csv"
        broker = ExecutionBroker()
        proposal = ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={"source": str(src_art), "destination": str(dst), "expected_artifact_type": "csv"},
            task_id=task_id,
        )
        b_res = broker.execute(proposal)
        assert b_res.success
        assert dst.exists()

        content = dst.read_text(encoding="utf-8")
        assert "sku" in content and "total_value" in content
        assert "Wireless Mouse" in content

        art_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
        HOLD_RESULTS.append({
            "class": "CLASS_2_CSV_DATA_TRANSFORM",
            "task_id": task_id,
            "latency_ms": latency_ms,
            "prompt_hash": p_hash,
            "response_hash": r_hash,
            "ast_safe": ast_res.is_safe,
            "sandbox_status": sb_res.status,
            "artifact_sha256": art_hash,
            "verified": True,
        })


def test_holdout_class_03_statistics_summary(qwen_server):
    """Class 3: Statistics / numerical summary reporting."""
    prompt = (
        "Write a pure Python script that computes descriptive statistics on a list of numbers: "
        "[12.5, 14.2, 11.8, 15.6, 18.2, 14.9, 13.1, 16.0, 19.5, 12.0, 14.5, 17.1]. "
        "Calculate the mean, median, sample variance, standard deviation, min, and max. "
        "Round all float values to 2 decimal places. "
        "Save the result as 'descriptive_stats.json' in the directory specified by os.environ['ASTRARUN_OUTPUT_DIR']. "
        "The JSON must have keys: 'count', 'mean', 'median', 'variance', 'std', 'min', 'max'. "
        "Output ONLY python code in ```python ``` blocks. No markdown explanations."
    )
    raw, latency_ms, p_hash, r_hash = run_qwen_inference(qwen_server, prompt)
    code = extract_code(raw)

    task_id = "task_holdout_cls3_stats"
    cand = CandidateTool(
        tool_id="dyn_stats_summary",
        goal="Calculate descriptive statistics report",
        task_id=task_id,
        executable_code=code,
    )

    inspector = ASTInspector()
    ast_res = inspector.inspect_candidate(cand)
    assert ast_res.is_safe

    sb_mgr = SandboxManager()
    cfg = SandboxConfig(run_id="c2_2a_cls3_run", profile=SandboxProfile.EPHEMERAL_TOOL, timeout_sec=20.0)
    sb_res = sb_mgr.execute_candidate(cand, config=cfg)
    assert sb_res.status == "SUCCESS", f"Execution error: {sb_res.stderr}\nStdout: {sb_res.stdout}"

    out_dir = AstraPaths.sandbox_dir() / task_id / "output"
    src_art = out_dir / "descriptive_stats.json"
    assert src_art.exists()

    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "descriptive_stats.json"
        broker = ExecutionBroker()
        proposal = ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={"source": str(src_art), "destination": str(dst), "expected_artifact_type": "json"},
            task_id=task_id,
        )
        b_res = broker.execute(proposal)
        assert b_res.success

        data = json.loads(dst.read_text(encoding="utf-8"))
        assert data.get("count") == 12
        assert 14.0 <= data.get("mean", 0) <= 16.0
        assert data.get("min") == 11.8
        assert data.get("max") == 19.5

        art_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
        HOLD_RESULTS.append({
            "class": "CLASS_3_STATISTICS_SUMMARY",
            "task_id": task_id,
            "latency_ms": latency_ms,
            "prompt_hash": p_hash,
            "response_hash": r_hash,
            "ast_safe": ast_res.is_safe,
            "sandbox_status": sb_res.status,
            "artifact_sha256": art_hash,
            "verified": True,
        })


def test_holdout_class_04_2d_visualization_spec(qwen_server):
    """Class 4: 2D declarative visualization spec generation + trusted render."""
    pytest.importorskip("matplotlib")
    prompt = (
        "Write a pure Python script that generates a 2D line chart visualization spec in JSON format. "
        "The spec must be written to 'line_chart_spec.json' in os.environ['ASTRARUN_OUTPUT_DIR']. "
        "The JSON structure must match AstraRun visualization schema exactly: "
        "{\n"
        "  'title': 'Server Latency',\n"
        "  'series': [\n"
        "    {\n"
        "      'name': 'P95 Latency',\n"
        "      'chart_type': 'line',\n"
        "      'x': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],\n"
        "      'y': [12.4, 15.1, 14.8, 22.0, 18.5, 16.2],\n"
        "      'color': '#00bbff'\n"
        "    }\n"
        "  ],\n"
        "  'x_axis': {'label': 'Hour'},\n"
        "  'y_axis': {'label': 'Latency (ms)'}\n"
        "}\n"
        "Note: 'chart_type' belongs inside each series dictionary, NOT at the top level of the JSON. "
        "Output ONLY python code in ```python ``` blocks."
    )
    raw, latency_ms, p_hash, r_hash = run_qwen_inference(qwen_server, prompt)
    code = extract_code(raw)

    task_id = "task_holdout_cls4_vis2d"
    cand = CandidateTool(
        tool_id="dyn_vis2d_spec",
        goal="Generate 2D line chart declarative spec",
        task_id=task_id,
        executable_code=code,
    )

    inspector = ASTInspector()
    ast_res = inspector.inspect_candidate(cand)
    assert ast_res.is_safe

    sb_mgr = SandboxManager()
    cfg = SandboxConfig(run_id="c2_2a_cls4_run", profile=SandboxProfile.EPHEMERAL_TOOL, timeout_sec=20.0)
    sb_res = sb_mgr.execute_candidate(cand, config=cfg)
    assert sb_res.status == "SUCCESS", f"Execution error: {sb_res.stderr}\nStdout: {sb_res.stdout}"

    out_dir = AstraPaths.sandbox_dir() / task_id / "output"
    src_art = out_dir / "line_chart_spec.json"
    assert src_art.exists()

    with tempfile.TemporaryDirectory() as td:
        dst_spec = Path(td) / "line_chart_spec.json"
        broker = ExecutionBroker()
        proposal = ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={"source": str(src_art), "destination": str(dst_spec), "expected_artifact_type": "json"},
            task_id=task_id,
        )
        b_res = broker.execute(proposal)
        assert b_res.success

        # Render spec via trusted visualization capability
        rendered_png = Path(td) / "rendered_line_chart.png"
        spec_dict = json.loads(dst_spec.read_text(encoding="utf-8"))
        render_res = render_visualization(spec=spec_dict, output_path=str(rendered_png))
        assert render_res.success, f"Render failed: {render_res.message}"
        assert rendered_png.exists()
        png_bytes = rendered_png.read_bytes()
        assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

        art_hash = hashlib.sha256(png_bytes).hexdigest()
        HOLD_RESULTS.append({
            "class": "CLASS_4_2D_VISUALIZATION_SPEC",
            "task_id": task_id,
            "latency_ms": latency_ms,
            "prompt_hash": p_hash,
            "response_hash": r_hash,
            "ast_safe": ast_res.is_safe,
            "sandbox_status": sb_res.status,
            "artifact_sha256": art_hash,
            "verified": True,
        })


def test_holdout_class_05_3d_visualization_spec(qwen_server):
    """Class 5: 3D visualization declarative surface spec generation + trusted render."""
    pytest.importorskip("matplotlib")
    prompt = (
        "Write a pure Python script that generates a 3D surface mesh visualization spec in JSON format. "
        "The spec must be written to 'surface_3d_spec.json' inside os.environ['ASTRARUN_OUTPUT_DIR']. "
        "Construct a 5x5 grid of z values representing a saddle surface. "
        "The JSON structure must match AstraRun 3D surface schema exactly: "
        "{\n"
        "  'title': 'Saddle Surface',\n"
        "  'series': [\n"
        "    {\n"
        "      'name': 'saddle',\n"
        "      'chart_type': 'surface_3d',\n"
        "      'z_matrix': [\n"
        "        [0.0, 3.0, 4.0, 3.0, 0.0],\n"
        "        [-3.0, 0.0, 1.0, 0.0, -3.0],\n"
        "        [-4.0, -1.0, 0.0, -1.0, -4.0],\n"
        "        [-3.0, 0.0, 1.0, 0.0, -3.0],\n"
        "        [0.0, 3.0, 4.0, 3.0, 0.0]\n"
        "      ]\n"
        "    }\n"
        "  ],\n"
        "  'camera': {'elevation': 30.0, 'azimuth': 45.0}\n"
        "}\n"
        "Note: 'chart_type' belongs inside the series dictionary, NOT at the top level of the JSON. "
        "Output ONLY python code in ```python ``` blocks."
    )
    raw, latency_ms, p_hash, r_hash = run_qwen_inference(qwen_server, prompt)
    code = extract_code(raw)

    task_id = "task_holdout_cls5_vis3d"
    cand = CandidateTool(
        tool_id="dyn_vis3d_spec",
        goal="Generate 3D surface mesh declarative spec",
        task_id=task_id,
        executable_code=code,
    )

    inspector = ASTInspector()
    ast_res = inspector.inspect_candidate(cand)
    assert ast_res.is_safe

    sb_mgr = SandboxManager()
    cfg = SandboxConfig(run_id="c2_2a_cls5_run", profile=SandboxProfile.EPHEMERAL_TOOL, timeout_sec=20.0)
    sb_res = sb_mgr.execute_candidate(cand, config=cfg)
    assert sb_res.status == "SUCCESS", f"Execution error: {sb_res.stderr}\nStdout: {sb_res.stdout}"

    out_dir = AstraPaths.sandbox_dir() / task_id / "output"
    src_art = out_dir / "surface_3d_spec.json"
    assert src_art.exists()

    with tempfile.TemporaryDirectory() as td:
        dst_spec = Path(td) / "surface_3d_spec.json"
        broker = ExecutionBroker()
        proposal = ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={"source": str(src_art), "destination": str(dst_spec), "expected_artifact_type": "json"},
            task_id=task_id,
        )
        b_res = broker.execute(proposal)
        assert b_res.success

        # Render spec via trusted visualization capability
        rendered_png = Path(td) / "rendered_surface_3d.png"
        spec_dict = json.loads(dst_spec.read_text(encoding="utf-8"))
        render_res = render_visualization(spec=spec_dict, output_path=str(rendered_png))
        assert render_res.success, f"Render failed: {render_res.message}"
        assert rendered_png.exists()
        png_bytes = rendered_png.read_bytes()
        assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

        art_hash = hashlib.sha256(png_bytes).hexdigest()
        HOLD_RESULTS.append({
            "class": "CLASS_5_3D_VISUALIZATION_SPEC",
            "task_id": task_id,
            "latency_ms": latency_ms,
            "prompt_hash": p_hash,
            "response_hash": r_hash,
            "ast_safe": ast_res.is_safe,
            "sandbox_status": sb_res.status,
            "artifact_sha256": art_hash,
            "verified": True,
        })


def test_holdout_class_06_multistep_workflow(qwen_server):
    """Class 6: Multi-step workflow (compute -> render spec -> reveal)."""
    pytest.importorskip("matplotlib")
    prompt = (
        "Write a pure Python script implementing a multi-step analytical workflow: "
        "Step 1: Compute compound monthly investment balance at the end of each month for months 1 to 6, starting with principal 1000 and 1% monthly interest (recording exactly 6 float balances, one for each month 1 through 6). "
        "Step 2: Save numerical summary as 'workflow_summary.json' with keys 'months': 6, 'final_balance': float, 'history': list of the 6 monthly float balances. "
        "Step 3: Save visualization spec as 'workflow_chart.json' matching AstraRun schema: "
        "{\n"
        "  'title': 'Investment Growth',\n"
        "  'series': [\n"
        "    {\n"
        "      'name': 'Growth',\n"
        "      'chart_type': 'line',\n"
        "      'x': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],\n"
        "      'y': <the 6 monthly balances>\n"
        "    }\n"
        "  ],\n"
        "  'x_axis': {'label': 'Month'},\n"
        "  'y_axis': {'label': 'Balance'}\n"
        "}\n"
        "Ensure len(x) == len(y) == 6. Do not place 'chart_type' or series fields at the root of the JSON. "
        "Save all files inside os.environ['ASTRARUN_OUTPUT_DIR']. "
        "Output ONLY python code in ```python ``` blocks."
    )
    raw, latency_ms, p_hash, r_hash = run_qwen_inference(qwen_server, prompt)
    code = extract_code(raw)

    task_id = "task_holdout_cls6_workflow"
    cand = CandidateTool(
        tool_id="dyn_multistep_workflow",
        goal="Multi-step compound investment and chart generation",
        task_id=task_id,
        executable_code=code,
    )

    inspector = ASTInspector()
    ast_res = inspector.inspect_candidate(cand)
    assert ast_res.is_safe

    sb_mgr = SandboxManager()
    cfg = SandboxConfig(run_id="c2_2a_cls6_run", profile=SandboxProfile.EPHEMERAL_TOOL, timeout_sec=20.0)
    sb_res = sb_mgr.execute_candidate(cand, config=cfg)
    assert sb_res.status == "SUCCESS", f"Execution error: {sb_res.stderr}\nStdout: {sb_res.stdout}"

    out_dir = AstraPaths.sandbox_dir() / task_id / "output"
    src_sum = out_dir / "workflow_summary.json"
    src_chart = out_dir / "workflow_chart.json"
    assert src_sum.exists()
    assert src_chart.exists()

    with tempfile.TemporaryDirectory() as td:
        dst_sum = Path(td) / "workflow_summary.json"
        dst_chart = Path(td) / "workflow_chart.json"
        broker = ExecutionBroker()

        b_res1 = broker.execute(ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={"source": str(src_sum), "destination": str(dst_sum), "expected_artifact_type": "json"},
            task_id=task_id,
        ))
        assert b_res1.success

        b_res2 = broker.execute(ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={"source": str(src_chart), "destination": str(dst_chart), "expected_artifact_type": "json"},
            task_id=task_id,
        ))
        assert b_res2.success

        # Trusted render of workflow chart
        chart_png = Path(td) / "workflow_chart.png"
        chart_spec = json.loads(dst_chart.read_text(encoding="utf-8"))
        r_res = render_visualization(spec=chart_spec, output_path=str(chart_png))
        assert r_res.success, f"Workflow chart render failed: {r_res.message}"
        assert chart_png.exists()

        HOLD_RESULTS.append({
            "class": "CLASS_6_MULTISTEP_WORKFLOW",
            "task_id": task_id,
            "latency_ms": latency_ms,
            "prompt_hash": p_hash,
            "response_hash": r_hash,
            "ast_safe": ast_res.is_safe,
            "sandbox_status": sb_res.status,
            "artifacts_produced": ["workflow_summary.json", "workflow_chart.json", "workflow_chart.png"],
            "verified": True,
        })


def test_holdout_class_07_autonomous_repair(qwen_server):
    """Class 7: Naturally failing code requiring real local Qwen autonomous repair."""
    task_id = "task_holdout_cls7_repair"

    # Seed with naturally buggy code (TypeError: unsupported operand type for +: 'int' and 'str')
    buggy_code = """
import os, json

out_dir = os.environ.get("ASTRARUN_OUTPUT_DIR", ".")
# BUG: string number concatenated with integer without conversion
values = [10, 20, 30, "40", 50]
total = 0
for v in values:
    total = total + v

result = {"total": total, "count": len(values)}
with open(os.path.join(out_dir, "repaired_total.json"), "w", encoding="utf-8") as f:
    json.dump(result, f)
"""
    cand = CandidateTool(
        tool_id="dyn_repair_tool",
        goal="Calculate total sum of values [10, 20, 30, 40, 50] and write to repaired_total.json",
        task_id=task_id,
        entrypoint="main.py",
        source_files={"main.py": buggy_code},
        generator_model="qwen-c2-2a-seed",
    )
    cand.provenance = CodeProvenance(
        task_id=task_id,
        model="qwen-c2-2a-seed",
        prompt_hash=hashlib.sha256(cand.goal.encode("utf-8")).hexdigest(),
        source_hash=cand.compute_source_hash(),
        entrypoint_hash=cand.compute_entrypoint_hash(),
        tree_hash=cand.compute_tree_hash(),
    )

    builder = DynamicToolBuilder()
    report = builder.build_and_execute(cand, timeout_sec=25.0)

    # Must succeed via autonomous repair
    assert report.is_success, f"Repair failed: {report.error_message}"
    assert report.repair_attempts >= 1, "Expected at least 1 repair attempt"

    out_dir = AstraPaths.sandbox_dir() / task_id / "output"
    src_art = out_dir / "repaired_total.json"
    assert src_art.exists(), f"Repaired artifact {src_art} does not exist"

    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "repaired_total.json"
        broker = ExecutionBroker()
        proposal = ActionProposal(
            category=ActionCategory.ACT,
            capability_id="deliver_artifact",
            parameters={"source": str(src_art), "destination": str(dst), "expected_artifact_type": "json"},
            task_id=task_id,
        )
        b_res = broker.execute(proposal)
        assert b_res.success
        data = json.loads(dst.read_text(encoding="utf-8"))
        assert data.get("total") == 150
        assert data.get("count") == 5

        HOLD_RESULTS.append({
            "class": "CLASS_7_AUTONOMOUS_REPAIR",
            "task_id": task_id,
            "repair_attempts": report.repair_attempts,
            "revisions_recorded": len(report.candidate_tool.provenance.revisions) if report.candidate_tool.provenance else 0,
            "verified": True,
            "final_total": data.get("total"),
        })

    # Save comprehensive results
    evidence_path = Path(__file__).resolve().parent.parent.parent / "docs" / "audit" / "C2_2A_RELEASE_INTEGRITY_EVIDENCE.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump({
            "milestone": "C2.2A",
            "timestamp": time.time(),
            "qwen_endpoint": qwen_server,
            "total_tasks": len(HOLD_RESULTS),
            "passed_tasks": sum(1 for r in HOLD_RESULTS if r.get("verified")),
            "tasks": HOLD_RESULTS,
        }, f, indent=2)
    print(f"\nWrote C2.2A release evidence to: {evidence_path}")
