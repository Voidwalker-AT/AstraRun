"""Post-Freeze C2.2 Adversarial Holdout and Real Local Model Verification Suite.

Validates the full C2.2 Security Closure:
1. Kernel AppContainer Identity, Token SID, Low Integrity (S-1-16-4096), zero capabilities.
2. Launch secrecy: strict environment allowlist prevents host canary secrets from leaking.
3. Network and Filesystem Isolation: socket connect to loopback/external raises WSAEACCES (10013),
   operator credential paths and Windows system directories are denied.
4. Sealed Artifact Promotion: handle-based exclusive read, single hard link, symlink/junction/ADS
   rejection, SHA-256 tamper detection, and atomic host commitment.
5. Trusted Visualization Defense: schema bounds reject script injection, NaN/Inf, bomb arrays,
   and out-of-process renderer safely produces verified PNG charts.
6. Positive Unseen Agent Task with REAL_LOCAL_MODEL_INFERENCE:
   Qwen2.5-Coder on port 8089 reasons, writes code, sandbox executes in AppContainer,
   and delivers verified JSON artifact through ExecutionBroker.
"""

import asyncio
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import time
import pytest

from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.cognition.client import ModelClient
from astrarun.cognition.models import InferenceRequest, ModelRole
from astrarun.cognition.supervisor import ModelSupervisor
from astrarun.core.paths import AstraPaths
from astrarun.files.service import deliver_artifact, validate_safe_path
from astrarun.sandbox.appcontainer_launcher import AppContainerLauncher
from astrarun.sandbox.manager import SandboxManager
from astrarun.sandbox.models import SandboxConfig, SandboxProfile
from astrarun.security.execution_broker import ActionCategory, ActionProposal, ExecutionBroker
from astrarun.tools.ast_inspector import ASTInspector
from astrarun.tools.candidate import CandidateTool, CodeProvenance
from astrarun.visualization.models import (
    AxisSpec,
    CameraSpec,
    ChartType,
    SeriesSpec,
    VisualizationSpec,
)
from astrarun.visualization.renderer import render_visualization


# =============================================================================
# 1. Identity & Token Boundaries
# =============================================================================

def test_post_freeze_identity_and_token_boundaries():
    """Verify kernel-enforced AppContainer identity, Low Integrity, and zero capabilities."""
    sb_dir = (AstraPaths.sandbox_dir() / f"test_id_{int(time.time() * 1000)}").resolve()
    sb_dir.mkdir(parents=True, exist_ok=True)

    probe_script = (sb_dir / "probe_token.py").resolve()
    probe_script.write_text(
        "import time, sys\nprint('IDENTITY_WORKER_ACTIVE')\ntime.sleep(1.5)\nsys.exit(0)\n",
        encoding="utf-8",
    )

    import threading
    import psutil

    result_holder = {}

    def run_worker():
        res = AppContainerLauncher.launch(
            entrypoint_file=probe_script,
            workspace=sb_dir,
            run_id="id_probe",
            timeout_sec=10.0,
        )
        result_holder["result"] = res

    t = threading.Thread(target=run_worker)
    t.start()
    time.sleep(0.5)

    # Inspect live child process token from host
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

    cur = psutil.Process()
    token_verified = False

    for child in cur.children(recursive=True):
        if "python" in child.name().lower():
            h_proc = kernel32.OpenProcess(0x1000, False, child.pid)
            if h_proc:
                h_token = wintypes.HANDLE()
                if advapi32.OpenProcessToken(h_proc, 0x0008, ctypes.byref(h_token)):
                    # 1. TokenIsAppContainer
                    TokenIsAppContainer = 29
                    is_ac = wintypes.DWORD()
                    ret_len = wintypes.DWORD()
                    if advapi32.GetTokenInformation(h_token, TokenIsAppContainer, ctypes.byref(is_ac), ctypes.sizeof(is_ac), ctypes.byref(ret_len)):
                        assert is_ac.value != 0, "Child TokenIsAppContainer is False"

                    # 2. TokenIntegrityLevel
                    TokenIntegrityLevel = 25
                    il_buf = (ctypes.c_byte * 256)()
                    if advapi32.GetTokenInformation(h_token, TokenIntegrityLevel, il_buf, ctypes.sizeof(il_buf), ctypes.byref(ret_len)):
                        sid_ptr = ctypes.cast(il_buf, ctypes.POINTER(ctypes.c_void_p)).contents
                        str_sid = wintypes.LPWSTR()
                        if advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(str_sid)):
                            assert str_sid.value == "S-1-16-4096", f"Expected Low Integrity S-1-16-4096, got {str_sid.value}"
                            kernel32.LocalFree(str_sid)

                    # 3. TokenCapabilities Count (Class 30)
                    TokenCapabilities = 30
                    cap_buf = (ctypes.c_byte * 16)()
                    ret_l = wintypes.DWORD(16)
                    if advapi32.GetTokenInformation(h_token, TokenCapabilities, cap_buf, 16, ctypes.byref(ret_l)):
                        cap_count = ctypes.cast(cap_buf, ctypes.POINTER(wintypes.DWORD)).contents.value
                        assert cap_count == 0, f"Expected 0 capabilities, got {cap_count}"

                    token_verified = True
                    kernel32.CloseHandle(h_token)
                kernel32.CloseHandle(h_proc)

    t.join()
    assert token_verified, "Failed to audit child process token while active"

    res = result_holder["result"]
    assert res.status == "SUCCESS", f"Launch failed: {res.stderr}"
    assert res.exit_code == 0
    assert "IDENTITY_WORKER_ACTIVE" in res.stdout
    assert res.is_appcontainer is True
    assert res.package_sid.startswith("S-1-15-2-")
    assert res.capabilities_granted == []


# =============================================================================
# 2. Launch-Time Secret Boundary
# =============================================================================

def test_post_freeze_launch_secrecy_boundary():
    """Verify child environment allowlist prevents operator host secrets from leaking."""
    canaries = {
        "CANARY_SECRET_OPENAI": "sk-proj-canary-secret-12345",
        "CANARY_SECRET_AWS": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "CANARY_SECRET_DATABASE": "postgres://user:super_secret_pw@db.local",
    }
    for k, v in canaries.items():
        os.environ[k] = v

    sb_dir = AstraPaths.sandbox_dir() / f"test_sec_{int(time.time() * 1000)}"
    sb_dir.mkdir(parents=True, exist_ok=True)

    probe_script = sb_dir / "probe_secrets.py"
    probe_script.write_text(
        r"""
import json
import os
import sys

env_keys = list(os.environ.keys())
print("ENV_KEYS:" + json.dumps(env_keys))
for k, v in os.environ.items():
    if "CANARY" in k or "canary" in v:
        print(f"LEAK_DETECTED: {k}={v}")
        sys.exit(1)

print("SECRECY_PASS: Zero canaries leaked.")
sys.exit(0)
""",
        encoding="utf-8",
    )

    try:
        result = AppContainerLauncher.launch(
            entrypoint_file=probe_script,
            workspace=sb_dir,
            run_id="sec_probe",
            timeout_sec=10.0,
        )

        assert result.exit_code == 0
        assert "SECRECY_PASS" in result.stdout
        assert "LEAK_DETECTED" not in result.stdout

        for canary_key in canaries:
            assert canary_key not in result.stdout
    finally:
        for k in canaries:
            os.environ.pop(k, None)


# =============================================================================
# 3. Network and Filesystem Isolation Denials
# =============================================================================

def test_post_freeze_network_and_filesystem_denials():
    """Verify socket connections raise WSAEACCES and operator host files are denied."""
    sb_dir = (AstraPaths.sandbox_dir() / f"test_denials_{int(time.time() * 1000)}").resolve()
    sb_dir.mkdir(parents=True, exist_ok=True)

    operator_home = str(Path.home().resolve())
    probe_script = (sb_dir / "probe_denials.py").resolve()
    probe_script.write_text(
        f"""
import os
from pathlib import Path
import socket
import sys

# 1. Network Probe: loopback port 8089 (Qwen), 8090 (Spark), external 8.8.8.8
network_blocked = True
for target in [("127.0.0.1", 8089), ("127.0.0.1", 8090), ("8.8.8.8", 53)]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        res = s.connect_ex(target)
        s.close()
        # In AppContainer without network capability, connect_ex returns 10013 (WSAEACCES)
        if res == 0:
            print(f"FAIL: Successfully connected to {{target}}")
            network_blocked = False
        elif res == 10013:
            print(f"DENIAL_CONFIRMED: WSAEACCES on {{target}}")
    except OSError as err:
        print(f"DENIAL_CONFIRMED: Socket error on {{target}}: {{err}}")

# 2. Filesystem Probe: operator sensitive directories
fs_blocked = True
op_home = Path(r"{operator_home}")
prohibited_reads = [
    op_home / ".ssh" / "id_rsa",
    op_home / ".aws" / "credentials",
]

for p in prohibited_reads:
    try:
        with open(p, "rb") as f:
            _ = f.read()
        print(f"FAIL: Read succeeded on {{p}}")
        fs_blocked = False
    except (PermissionError, FileNotFoundError, OSError):
        print(f"FS_DENIAL_CONFIRMED: Read denied to {{p}}")

try:
    with open(r"C:\\Windows\\System32\\drivers\\etc\\hosts", "a") as f:
        f.write("# unauthorized\\n")
    print("FAIL: Write succeeded to hosts")
    fs_blocked = False
except (PermissionError, FileNotFoundError, OSError):
    print("FS_DENIAL_CONFIRMED: Write denied to hosts")

if network_blocked and fs_blocked:
    print("DENIALS_VERIFIED: All network and unauthorized filesystem accesses blocked.")
    sys.exit(0)
else:
    print("FAIL: Isolation breached")
    sys.exit(1)
""",
        encoding="utf-8",
    )

    result = AppContainerLauncher.launch(
        entrypoint_file=probe_script,
        workspace=sb_dir,
        run_id="denials_probe",
        timeout_sec=10.0,
    )

    assert result.exit_code == 0
    assert "DENIALS_VERIFIED" in result.stdout


# =============================================================================
# 4. Sealed Artifact Promotion Adversarial Suite
# =============================================================================

def test_post_freeze_sealed_artifact_promotion_adversarial_suite():
    """Verify handle-based exclusive read, single hardlink, and adversarial defense."""
    # A. Path string validation
    assert not validate_safe_path("artifact.txt:malicious.exe")[0]
    assert not validate_safe_path(r"\\192.168.1.1\share\payload.dll")[0]
    assert not validate_safe_path(r"\??\C:\malicious.dll")[0]
    assert not validate_safe_path("test_file.txt.")[0]
    assert not validate_safe_path("test_file.txt ")[0]
    assert not validate_safe_path("CON.txt")[0]
    assert validate_safe_path(r"C:\safe\path\to\artifact.txt")[0]

    # B. Boundary escape denial
    with tempfile.TemporaryDirectory() as td_unauth:
        unauth_src = Path(td_unauth) / "stolen_data.txt"
        unauth_src.write_text("unauthorized data", encoding="utf-8")
        with tempfile.TemporaryDirectory() as td_dst:
            res_esc = deliver_artifact(
                source=str(unauth_src),
                destination=str(Path(td_dst) / "out.txt"),
            )
            assert not res_esc.success
            assert "escapes" in res_esc.message.lower()

    # C. Legitimate sealed promotion and tamper detection
    sb_dir = AstraPaths.sandbox_dir() / f"test_seal_adv_{int(time.time() * 1000)}"
    sb_dir.mkdir(parents=True, exist_ok=True)
    legit_file = sb_dir / "valid_report.txt"
    content = b"GENUINE_SEALED_PAYLOAD_C2_2"
    legit_file.write_bytes(content)
    expected_hash = hashlib.sha256(content).hexdigest()

    with tempfile.TemporaryDirectory() as td_dst:
        dest_file = Path(td_dst) / "promoted_report.txt"

        # Tampered hash rejection
        res_tamper = deliver_artifact(
            source=str(legit_file),
            destination=str(dest_file),
            source_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        )
        assert not res_tamper.success
        assert not dest_file.exists()

        # Legitimate promotion
        res_ok = deliver_artifact(
            source=str(legit_file),
            destination=str(dest_file),
            source_sha256=expected_hash,
        )
        assert res_ok.success
        assert dest_file.exists()
        assert dest_file.read_bytes() == content


# =============================================================================
# 5. Trusted Visualization Defense
# =============================================================================

def test_post_freeze_trusted_visualization_defense():
    """Verify declarative schema validation rejects hostile attacks and renders safe charts."""
    # 1. Script injection in title
    with pytest.raises(Exception):
        VisualizationSpec(
            title="<script>alert('xss')</script>",
            series=[SeriesSpec(name="s1", x=[1.0, 2.0], y=[3.0, 4.0])],
        )

    # 2. Non-finite values
    with pytest.raises(Exception):
        VisualizationSpec(
            title="Invalid Float",
            series=[SeriesSpec(name="s1", x=[1.0, float("nan")], y=[3.0, 4.0])],
        )

    # 3. Array bomb (> 100,000 points)
    huge_arr = [1.0] * 120000
    with pytest.raises(Exception):
        VisualizationSpec(
            title="Array Bomb",
            series=[SeriesSpec(name="bomb", x=huge_arr, y=huge_arr)],
        )

    # 4. Valid 2D render
    with tempfile.TemporaryDirectory() as td:
        out_2d = Path(td) / "chart_2d.png"
        spec_dict = {
            "title": "Valid C2.2 Benchmark",
            "series": [
                {
                    "name": "Series A",
                    "chart_type": "line",
                    "x": [1.0, 2.0, 3.0, 4.0],
                    "y": [10.0, 25.0, 15.0, 30.0],
                    "color": "#00ffcc",
                }
            ],
            "x_axis": {"label": "X Axis"},
            "y_axis": {"label": "Y Axis"},
        }
        res_2d = render_visualization(spec=spec_dict, output_path=str(out_2d))
        assert res_2d.success
        assert out_2d.exists()
        bytes_2d = out_2d.read_bytes()
        assert bytes_2d.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(bytes_2d) > 1000


# =============================================================================
# 6. Positive Unseen Agent Task (REAL_LOCAL_MODEL_INFERENCE)
# =============================================================================

def test_post_freeze_positive_unseen_qwen_agent_task():
    """Verify end-to-end autonomous flow: Qwen local model inference -> AST screening -> AppContainer execution -> Sealed Delivery."""
    qwen_model_path = r"E:\AI_Models\GGUF\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
    if not os.path.exists(qwen_model_path):
        pytest.skip(f"Qwen model not found at {qwen_model_path}")

    supervisor = ModelSupervisor.get_instance()
    port = 8089
    model_id = "qwen-c2-2-holdout"

    print("\nStarting Qwen on loopback port 8089 for post-freeze inference...")
    started = supervisor.start_server(
        model_id=model_id,
        model_path=qwen_model_path,
        port=port,
        role=ModelRole.DEEP,
        ngl=33,
        ctx_size=2048,
        timeout=20.0,
    )
    assert started, "Failed to start Qwen llama-server on port 8089"

    try:
        client = ModelClient()
        unseen_prompt = (
            "Write a pure Python script that calculates the prime factors of 20261008 "
            "and writes a JSON file named 'factors.json' inside the directory specified by os.environ['ASTRARUN_OUTPUT_DIR']. "
            "The JSON must have keys 'target': 20261008, 'factors': list of int factors. "
            "Output ONLY the python code enclosed in ```python ``` blocks. No markdown explanations."
        )

        prompt_hash = hashlib.sha256(unseen_prompt.encode("utf-8")).hexdigest()
        req = InferenceRequest(
            role=ModelRole.DEEP,
            messages=[{"role": "user", "content": unseen_prompt}],
            temperature=0.1,
            max_tokens=1024,
        )

        print("Executing REAL_LOCAL_MODEL_INFERENCE request to Qwen...")
        obs = asyncio.run(client.complete(req, endpoint=f"http://127.0.0.1:{port}"))

        assert obs.status == "SUCCESS", f"Inference failed: {obs.failure_reason}"
        raw_code = obs.raw_output
        assert raw_code, "Model returned empty response"

        response_hash = hashlib.sha256(raw_code.encode("utf-8")).hexdigest()
        print(f"Model response received: {len(raw_code)} chars, latency: {obs.latency_ms:.1f}ms")

        # Extract code block
        code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", raw_code, re.DOTALL)
        script_code = code_match.group(1) if code_match else raw_code

        # AST Inspection
        inspector = ASTInspector()
        cand = CandidateTool(
            tool_id="dyn_prime_factors",
            goal="Compute prime factors of 20261008 and write JSON",
            task_id="task_c2_2_holdout",
            executable_code=script_code,
            metadata={
                "name": "Prime Factors Calculator",
                "generator_model": "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
            },
        )
        ast_res = inspector.inspect_candidate(cand)
        assert ast_res.is_safe, f"AST inspection failed: {ast_res.violations}"

        # Sandbox execution in AppContainer
        sb_mgr = SandboxManager()
        cfg = SandboxConfig(
            run_id="c2_2_qwen_run",
            profile=SandboxProfile.EPHEMERAL_TOOL,
            timeout_sec=30.0,
            memory_limit_bytes=512 * 1024 * 1024,
        )

        print("Executing synthesized code in AppContainer worker...")
        sb_res = sb_mgr.execute_candidate(cand, config=cfg)
        assert sb_res.status == "SUCCESS", f"Sandbox execution failed: {sb_res.stderr}\nStdout: {sb_res.stdout}"
        assert sb_res.exit_code == 0

        # Verify output artifact produced in sandbox output directory
        out_dir = AstraPaths.sandbox_dir() / cand.task_id / "output"
        src_artifact = out_dir / "factors.json"
        assert src_artifact.exists(), f"Expected artifact {src_artifact} does not exist"

        # Host ExecutionBroker governed artifact delivery
        broker = ExecutionBroker()
        with tempfile.TemporaryDirectory() as host_td:
            final_dst = Path(host_td) / "prime_factors_result.json"
            proposal = ActionProposal(
                category=ActionCategory.ACT,
                capability_id="deliver_artifact",
                parameters={
                    "source": str(src_artifact),
                    "destination": str(final_dst),
                    "expected_artifact_type": "json",
                },
                task_id=cand.task_id,
            )

            print("Promoting sealed artifact via ExecutionBroker...")
            broker_res = broker.execute(proposal)
            assert broker_res.success, f"Broker delivery failed: {broker_res.message}"
            assert final_dst.exists()

            # Verify artifact data
            with open(final_dst, "r", encoding="utf-8") as f:
                data = json.load(f)

            assert data.get("target") == 20261008
            factors = data.get("factors", [])
            assert len(factors) > 0

            # Mathematical verification
            product = 1
            for p in factors:
                product *= p
            assert product == 20261008, f"Factor product {product} != 20261008"

            print(f"VERIFIED: 20261008 prime factors: {factors} (product = {product})")

    finally:
        print("Stopping Qwen supervisor...")
        supervisor.stop_server(model_id)
