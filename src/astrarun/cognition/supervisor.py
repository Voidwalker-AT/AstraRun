"""Production Model Supervisor for isolated loopback llama-server processes.

Enforces:
  - Strict loopback binding: 127.0.0.1 (inaccessible externally)
  - Stealth execution: CREATE_NO_WINDOW (zero visible console windows)
  - Strict process ownership tracking via ProcessTracker
  - Win32 Job Object containment (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
  - Safe port collision detection (unrelated processes strictly protected)
  - Health supervision, startup verification, and bounded restart policies
"""

from __future__ import annotations

import os
import secrets
import subprocess
import time
from typing import Dict, Optional, Tuple

import httpx
import psutil

from astrarun.cognition.models import ModelRole, ModelState, ResidencyPreference
from astrarun.cognition.residency import ModelRecord, ModelResidencyManager
from astrarun.core.logging import get_logger
from astrarun.execution.job_object import Win32JobObject
from astrarun.execution.process_tracker import ProcessTracker

from astrarun.core.paths import resolve_runtime_binary

logger = get_logger("astrarun.cognition.supervisor")

CREATE_NO_WINDOW = 0x08000000
DEFAULT_SERVER_BINARY = str(resolve_runtime_binary("llama-server.exe", dev_fallback=r"E:\AI_Runtimes\llama.cpp-spark\llama-server.exe"))


class ModelSupervisor:
    """
    Supervises the lifecycle of Astra-owned local llama.cpp server instances.
    """

    _instance: Optional[ModelSupervisor] = None

    def __init__(
        self,
        residency_manager: Optional[ModelResidencyManager] = None,
        process_tracker: Optional[ProcessTracker] = None,
        server_binary: Optional[str] = None,
    ) -> None:
        self.residency = residency_manager or ModelResidencyManager.get_instance()
        self.tracker = process_tracker or ProcessTracker.get_instance()
        self.server_binary = server_binary or os.environ.get("ASTRA_LLAMA_SERVER_PATH", DEFAULT_SERVER_BINARY)
        self._jobs: Dict[str, Win32JobObject] = {}
        self._popens: Dict[str, subprocess.Popen] = {}

        # Wire eviction handler from residency manager
        self.residency.register_eviction_handler(self._handle_eviction)

    @classmethod
    def get_instance(cls) -> ModelSupervisor:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _handle_eviction(self, record: ModelRecord) -> None:
        """Callback invoked when residency manager requires memory eviction."""
        logger.info("Eviction triggered for model [%s]", record.model_id)
        self.stop_server(record.model_id)

    def is_port_in_use(self, port: int) -> Tuple[bool, Optional[int]]:
        """
        Check if a TCP port is currently listening and return listening PID if found.
        """
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
                    return True, conn.pid
        except Exception as e:
            logger.debug("Error querying network connections for port %d: %s", port, e)

        # Fallback quick socket probe
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            res = s.connect_ex(("127.0.0.1", port))
            if res == 0:
                return True, None
        return False, None

    def start_server(
        self,
        model_id: str,
        model_path: str,
        port: int,
        role: ModelRole,
        preference: ResidencyPreference = ResidencyPreference.WARM,
        ngl: int = 99,
        ctx_size: int = 4096,
        threads: int = 4,
        extra_args: Optional[list[str]] = None,
        timeout: float = 30.0,
    ) -> bool:
        """
        Start an isolated llama-server instance bound strictly to loopback 127.0.0.1.
        """
        if not os.path.exists(self.server_binary):
            logger.error("llama-server binary not found at %s", self.server_binary)
            return False

        if not os.path.exists(model_path):
            logger.error("Model GGUF file not found at %s", model_path)
            return False

        # 1. Port Collision & Stale Process Handling
        in_use, listen_pid = self.is_port_in_use(port)
        if in_use:
            if listen_pid and self.tracker.is_astra_owned(listen_pid):
                logger.warning("Port %d held by stale Astra process %d. Terminating.", port, listen_pid)
                self.tracker.kill_process_tree(listen_pid)
                time.sleep(0.5)
            else:
                # Check if it is already healthy and responding as our model
                endpoint = f"http://127.0.0.1:{port}"
                if self._check_endpoint_health(endpoint):
                    logger.info("Port %d is already hosting a healthy llama-server. Attaching.", port)
                    rec = self.residency.get_model(model_id) or ModelRecord(
                        model_id=model_id,
                        role=role,
                        residency_preference=preference,
                        endpoint=endpoint,
                        port=port,
                        model_path=model_path,
                    )
                    rec.state = ModelState.READY
                    rec.health = "HEALTHY"
                    self.residency.register_model(rec)
                    return True
                else:
                    logger.error(
                        "Port %d is in use by non-Astra process (PID: %s). Refusing to interfere.",
                        port,
                        listen_pid,
                    )
                    return False

        # 2. Register/Prepare Model Record
        token = secrets.token_hex(8)
        endpoint = f"http://127.0.0.1:{port}"
        rec = self.residency.get_model(model_id)
        if not rec:
            rec = ModelRecord(
                model_id=model_id,
                role=role,
                residency_preference=preference,
                endpoint=endpoint,
                port=port,
                model_path=model_path,
                ownership_token=token,
            )
            self.residency.register_model(rec)

        self.residency.transition_state(model_id, ModelState.STARTING)

        # 3. Form Command Line with Strict Loopback
        cmd = [
            self.server_binary,
            "-m", model_path,
            "--host", "127.0.0.1",  # Strict loopback binding
            "--port", str(port),
            "-ngl", str(ngl),
            "-c", str(ctx_size),
            "--threads", str(threads),
        ]

        if role == ModelRole.FAST:
            cmd.extend(["--reasoning-budget", "0"])
        if extra_args:
            cmd.extend(extra_args)

        flags = 0
        if os.name == "nt":
            flags |= CREATE_NO_WINDOW

        job = Win32JobObject(name=f"astra_srv_{model_id}_{port}")
        self._jobs[model_id] = job

        try:
            logger.info("Spawning model server [%s] on 127.0.0.1:%d (stealth=True)", model_id, port)
            popen = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=flags,
            )
            self._popens[model_id] = popen

            # Assign process to Job Object
            if os.name == "nt" and hasattr(popen, "_handle"):
                job.assign_process(int(popen._handle))

            # Register with ProcessTracker
            self.tracker.register_process(
                pid=popen.pid,
                task_id=f"model_{model_id}",
                command=f"llama-server {model_id} on {port}",
                handle=int(popen._handle) if hasattr(popen, "_handle") else None,
            )

            rec.pid = popen.pid
            rec.load_timestamp = time.time()
            self.residency.transition_state(model_id, ModelState.WARMING)

            # 4. Wait for Server Health Readiness
            t0 = time.perf_counter()
            is_ready = False
            while (time.perf_counter() - t0) < timeout:
                if popen.poll() is not None:
                    # Process died prematurely
                    stderr_txt = popen.stderr.read().decode("utf-8", errors="replace") if popen.stderr else ""
                    logger.error("Model server [%s] exited unexpectedly (code %s): %s", model_id, popen.returncode, stderr_txt[:300])
                    self.stop_server(model_id)
                    self.residency.transition_state(model_id, ModelState.FAILED)
                    return False

                if self._check_endpoint_health(endpoint):
                    is_ready = True
                    break
                time.sleep(0.4)

            if not is_ready:
                logger.error("Model server [%s] timed out waiting for health check (%ds)", model_id, timeout)
                self.stop_server(model_id)
                self.residency.transition_state(model_id, ModelState.FAILED)
                return False

            self.residency.transition_state(model_id, ModelState.READY)
            rec.health = "HEALTHY"
            self.residency.update_telemetry(model_id)
            logger.info("Model server [%s] is READY on 127.0.0.1:%d", model_id, port)
            return True

        except Exception as e:
            logger.error("Failed to start model server [%s]: %s", model_id, e)
            self.stop_server(model_id)
            self.residency.transition_state(model_id, ModelState.FAILED)
            return False

    def _check_endpoint_health(self, endpoint: str) -> bool:
        """Query /health endpoint on llama-server."""
        url = f"{endpoint.rstrip('/')}/health"
        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(url)
                return res.status_code == 200
        except Exception:
            return False

    def health_check(self, model_id: str) -> bool:
        """Verify health of a supervised model."""
        rec = self.residency.get_model(model_id)
        if not rec or not rec.endpoint:
            return False
        is_healthy = self._check_endpoint_health(rec.endpoint)
        rec.health = "HEALTHY" if is_healthy else "UNHEALTHY"
        return is_healthy

    def ensure_running(self, model_id: str) -> bool:
        """
        Verify model is healthy, attempting bounded restart if dead.
        Respects max restart limit within rolling window.
        """
        rec = self.residency.get_model(model_id)
        if not rec:
            return False

        if self.health_check(model_id):
            return True

        logger.warning("Model server [%s] is unhealthy or dead. Evaluating restart.", model_id)
        can_restart = self.residency.record_restart(model_id)
        if not can_restart:
            logger.error("Model [%s] restart aborted: restart ceiling reached.", model_id)
            return False

        # Attempt clean restart
        self.stop_server(model_id)
        return self.start_server(
            model_id=rec.model_id,
            model_path=rec.model_path,
            port=rec.port,
            role=rec.role,
            preference=rec.residency_preference,
        )

    def stop_server(self, model_id: str) -> bool:
        """
        Safely stop a supervised model server and cleanup Job Object and ProcessTracker.
        Leaves unrelated external processes completely untouched.
        """
        rec = self.residency.get_model(model_id)
        job = self._jobs.pop(model_id, None)
        popen = self._popens.pop(model_id, None)

        if job:
            try:
                job.terminate(exit_code=0)
                job.close()
            except Exception as e:
                logger.warning("Error closing job for %s: %s", model_id, e)

        if popen:
            try:
                if psutil.pid_exists(popen.pid) and self.tracker.is_astra_owned(popen.pid):
                    self.tracker.kill_process_tree(popen.pid)
            except Exception as e:
                logger.warning("Error killing popen for %s: %s", model_id, e)

        if rec:
            self.residency.transition_state(model_id, ModelState.STOPPED)
            rec.pid = None
            rec.health = "UNKNOWN"

        logger.info("Stopped model server [%s]", model_id)
        return True

    def stop_all_servers(self) -> None:
        """Stop all active Astra-owned model servers."""
        model_ids = list(self._jobs.keys()) + list(self._popens.keys())
        for mid in set(model_ids):
            self.stop_server(mid)
