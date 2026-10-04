"""Laya shadow router adapter for AstraRun v0.3.

Provides isolated, non-autoregressive semantic decision-making without granting
production execution authority.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from astrarun.core.crash import record_subsystem_operation
from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.base import BaseRouter

logger = get_logger("astrarun.routing.laya")

# Standard intent taxonomy defined in docs/INTENT_TAXONOMY.md
INTENT_CRITERIA = {
    "open_app": "Launch an installed desktop application",
    "open_folder": "Open a local folder in File Explorer",
    "open_url": "Navigate to a website URL",
    "open_project": "Open a software development workspace or project",
    "find_file": "Search for or open an individual document or file",
    "process_action": "Manage, restart, or kill running processes or ports",
    "system_action": "System, hardware, volume, or power actions",
    "ai_query": "Ask a conversational AI or coding question",
    "browser_action": "Search the web or perform in-browser actions",
    "unknown": "Ambiguous, unsupported, or unsafe request"
}

# Only these intents have live execution tools in AstraRun v0.3
EXECUTABLE_INTENTS = {"open_app", "open_folder", "open_url"}


@dataclass
class LayaDecision:
    """Rich semantic decision output produced by Laya."""
    intent: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    is_executable_now: bool = False
    requires_resolution: bool = False
    latency_ms: float = 0.0
    raw_result: dict[str, Any] = field(default_factory=dict)
    source: str = "laya"
    error: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.intent != "unknown" and self.error is None


class LayaProcessClient:
    """
    Supervises an isolated child process running Laya inference.
    
    Protects the resident desktop shell (AstraRun.exe) from native PyTorch, CUDA,
    or tokenizers crash termination. All communication is JSON IPC over stdio pipes.
    """

    def __init__(
        self,
        model_id: str = "convaiinnovations/laya",
        device: str = "cpu",
        timeout_ms: float = 3000.0,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.timeout_ms = timeout_ms
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._req_counter = 0
        self._warmup_started = False
        self._last_error: Optional[str] = None

    def _ensure_worker_running(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True

        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True

            try:
                from astrarun.core.paths import get_cache_dir, is_release_mode
                hf_cache_dir = str(get_cache_dir() / "huggingface") if is_release_mode() else "E:/AI_Models/HF_CACHE"

                env = os.environ.copy()
                env["HF_HOME"] = hf_cache_dir
                env["HF_HUB_OFFLINE"] = "1"
                env["TRANSFORMERS_OFFLINE"] = "1"
                env["PYTHONUNBUFFERED"] = "1"

                # Command selection
                if getattr(sys, "frozen", False):
                    cmd = [sys.executable, "--worker-type", "laya"]
                else:
                    cmd = [sys.executable, "-m", "astrarun.routing.laya_worker"]

                record_subsystem_operation("LAYA_WORKER_STARTING", {"cmd": cmd})
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=env,
                    creationflags=0x08000000 if sys.platform == "win32" else 0,
                )
                logger.info("Spawned isolated LayaWorker PID %d", self._proc.pid)
                return True
            except Exception as err:
                self._last_error = f"Failed to spawn Laya worker: {err}"
                logger.error(self._last_error)
                return False

    def predict(self, text: str, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send predict request to isolated worker over stdin/stdout."""
        if not self._ensure_worker_running():
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "probabilities": {},
                "latency_ms": 0.0,
                "error": self._last_error or "Laya worker not running",
            }

        self._req_counter += 1
        req_id = f"laya-req-{self._req_counter}"
        payload = {"id": req_id, "action": "predict", "text": text}
        if criteria:
            payload["criteria"] = criteria

        record_subsystem_operation("LAYA_REQUEST_SENT", {"req_id": req_id, "text": text})

        try:
            assert self._proc is not None and self._proc.stdin is not None and self._proc.stdout is not None
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()

            line = self._proc.stdout.readline()
            if not line:
                # Worker exited or crashed
                code = self._proc.poll()
                record_subsystem_operation("WORKER_EXITED", {"exit_code": code, "last_request": text})
                logger.warning("[CRASH_CONTAINED] LayaWorker exited with code %s during request '%s'", code, text)
                self._proc = None
                return {
                    "intent": "unknown",
                    "confidence": 0.0,
                    "probabilities": {},
                    "latency_ms": 0.0,
                    "error": f"LayaWorker terminated (code {code})",
                }

            record_subsystem_operation("IDLE")
            data = json.loads(line.strip())
            return data
        except Exception as err:
            code = self._proc.poll() if self._proc else None
            record_subsystem_operation("WORKER_EXITED", {"exit_code": code, "error": str(err), "last_request": text})
            logger.warning("[CRASH_CONTAINED] Exception communicating with LayaWorker: %s (proc exit_code=%s)", err, code)
            if self._proc:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "probabilities": {},
                "latency_ms": 0.0,
                "error": str(err),
            }

    def warmup_async(self) -> None:
        """Start warmup in background daemon thread without blocking resident UI."""
        if self._warmup_started:
            return
        self._warmup_started = True

        def _do_warmup():
            if self._ensure_worker_running() and self._proc and self._proc.stdin and self._proc.stdout:
                try:
                    self._proc.stdin.write(json.dumps({"id": "warmup-0", "action": "warmup"}) + "\n")
                    self._proc.stdin.flush()
                    resp = self._proc.stdout.readline()
                    logger.debug("LayaWorker warmup response: %s", resp.strip())
                except Exception as e:
                    logger.debug("LayaWorker background warmup failed: %s", e)

        t = threading.Thread(target=_do_warmup, daemon=True, name="LayaWorker-Warmup")
        t.start()

    def crash_for_test(self) -> None:
        """Explicitly crash the worker to test resident crash containment."""
        if self._ensure_worker_running() and self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write(json.dumps({"action": "crash_for_test"}) + "\n")
                self._proc.stdin.flush()
            except Exception:
                pass

    def shutdown(self) -> None:
        """Clean shutdown of worker subprocess."""
        if self._proc and self._proc.poll() is None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
                    self._proc.stdin.flush()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            self._proc = None


class LayaAgentProxy:
    """Proxy object implementing the duck-typed interface of laya.Agent for callers."""

    def __init__(self, client: LayaProcessClient) -> None:
        self._client = client

    def predict(self, text: str, criteria: Optional[Dict[str, Any]] = None) -> Any:
        res = self._client.predict(text, criteria)
        if res.get("error"):
            raise RuntimeError(f"LayaWorker prediction error: {res.get('error')}")

        if criteria and "raw_result" in res:
            return res["raw_result"]

        # Return a simple mock object with attributes matching LayaAgent
        class _PredResult:
            def __init__(self, d: Dict[str, Any]):
                self.intent = d.get("intent", "unknown")
                self.confidence = d.get("confidence", 0.0)
                self.probabilities = d.get("probabilities", {})
        return _PredResult(res)


class LayaRouter(BaseRouter):
    """
    Adapter integrating the Laya decision engine behind AstraRun's BaseRouter interface.
    
    Operates out-of-process via LayaProcessClient to protect AstraRun.exe from native crashes.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", True))
        self.mode = str(self.config.get("mode", "shadow")).lower()
        self.model_id = str(self.config.get("model", "convaiinnovations/laya"))
        self.device = str(self.config.get("device", "auto")).lower()
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.75))
        self.timeout_ms = float(self.config.get("timeout_ms", 3000.0))

        self._client = LayaProcessClient(
            model_id=self.model_id,
            device=self.device,
            timeout_ms=self.timeout_ms,
        )
        self._proxy = LayaAgentProxy(self._client)
        self._load_failed = False
        self._load_error_msg = None

        if self.enabled:
            # Lazy background warmup — never blocks the UI thread
            self._client.warmup_async()

    def get_agent(self) -> Any:
        """Return the isolated agent proxy for LayaSandwichRouter or other consumers."""
        if not self.enabled:
            return None
        return self._proxy

    def predict_intent(self, request: str) -> LayaDecision:
        """
        Evaluate user request against the 10-class intent taxonomy out-of-process.
        
        Returns structured LayaDecision preserving full calibrated probability distribution.
        """
        clean_req = request.strip()
        if not clean_req:
            return LayaDecision(
                intent="unknown",
                confidence=0.0,
                probabilities={},
                is_executable_now=False,
                requires_resolution=False,
                error="Empty request"
            )

        if not self.enabled:
            return LayaDecision(
                intent="unknown",
                confidence=0.0,
                probabilities={},
                is_executable_now=False,
                requires_resolution=False,
                error="Laya router disabled"
            )

        resp = self._client.predict(clean_req)
        intent = resp.get("intent", "unknown")
        confidence = float(resp.get("confidence", 0.0))
        probs = resp.get("probabilities", {})
        err = resp.get("error")
        lat = float(resp.get("latency_ms", 0.0))

        is_exec = intent in EXECUTABLE_INTENTS and confidence >= self.confidence_threshold
        requires_res = intent in ("open_project", "find_file") or intent in EXECUTABLE_INTENTS

        return LayaDecision(
            intent=intent,
            confidence=confidence,
            probabilities={str(k): float(v) for k, v in probs.items()} if isinstance(probs, dict) else {},
            is_executable_now=is_exec,
            requires_resolution=requires_res,
            latency_ms=lat,
            raw_result=resp,
            source="laya_isolated_worker",
            error=err,
        )

    def shutdown(self) -> None:
        """Cleanly terminate the worker process."""
        self._client.shutdown()

    def predict_intent_batch(
        self,
        requests: list[str],
        batch_size: int = 16,
        questions: dict[str, Any] | None = None,
    ) -> list[LayaDecision]:
        """
        Evaluate batch of requests with high throughput vectorized inference.
        """
        clean_requests = [r.strip() for r in requests]
        agent = self.get_agent()
        if agent is None:
            err = self._load_error_msg or "Laya router disabled or unavailable"
            return [
                LayaDecision(
                    intent="unknown",
                    confidence=0.0,
                    error=err,
                )
                for _ in clean_requests
            ]

        q_spec = questions or {
            "intent": {
                "type": "choice",
                "instructions": "Which action does the user intend?",
                "criteria": INTENT_CRITERIA,
            }
        }

        t0 = time.perf_counter()
        try:
            results = agent.predict_batch(clean_requests, q_spec, batch_size=batch_size)
            total_lat = (time.perf_counter() - t0) * 1000.0
            per_query_lat = total_lat / max(1, len(clean_requests))

            decisions = []
            for clean_req, raw_output in zip(clean_requests, results):
                if not clean_req:
                    decisions.append(
                        LayaDecision(intent="unknown", confidence=0.0, error="Empty request", latency_ms=per_query_lat)
                    )
                    continue

                answers = raw_output.get("answers", {})
                intent_answer = answers.get("intent", {})
                chosen_intent = intent_answer.get("choice", "unknown")
                probs = intent_answer.get("probabilities", {})
                confidence = float(intent_answer.get("confidence", probs.get(chosen_intent, 0.0)))

                is_exec = chosen_intent in EXECUTABLE_INTENTS and confidence >= self.confidence_threshold
                requires_res = chosen_intent in ("open_project", "find_file") or chosen_intent in EXECUTABLE_INTENTS

                decisions.append(
                    LayaDecision(
                        intent=chosen_intent,
                        confidence=confidence,
                        probabilities={str(k): float(v) for k, v in probs.items()},
                        is_executable_now=is_exec,
                        requires_resolution=requires_res,
                        latency_ms=per_query_lat,
                        raw_result=raw_output,
                        source="laya",
                    )
                )
            return decisions
        except Exception as err:
            logger.error("Laya predict_batch error: %s", err, exc_info=True)
            return [
                LayaDecision(
                    intent="unknown",
                    confidence=0.0,
                    error=str(err),
                )
                for _ in clean_requests
            ]

    def route(self, request: str, context: RoutingContext) -> Decision:
        """
        Conform to the BaseRouter contract.
        
        Maps LayaDecision into AstraRun Decision.
        In shadow mode, this decision is logged but NOT executed.
        """
        laya_dec = self.predict_intent(request)
        
        if not laya_dec.is_resolved:
            return Decision(
                tool="unknown",
                args={},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya unresolved: {laya_dec.error or 'unknown intent'}"
            )

        intent = laya_dec.intent
        # Extract target argument if possible
        clean_target = re.sub(r"^(?:open|launch|start|run|show|go to|browse)\s+", "", request.strip(), flags=re.I).strip()
        
        if intent == "open_app":
            return Decision(
                tool="open_app",
                args={"app": clean_target},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya classified intent as open_app (confidence: {laya_dec.confidence:.2f})"
            )
        elif intent == "open_folder":
            return Decision(
                tool="open_folder",
                args={"folder": clean_target},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya classified intent as open_folder (confidence: {laya_dec.confidence:.2f})"
            )
        elif intent == "open_url":
            return Decision(
                tool="open_url",
                args={"url": clean_target},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya classified intent as open_url (confidence: {laya_dec.confidence:.2f})"
            )
        else:
            # Future / unexecutable intents
            return Decision(
                tool="unknown",
                args={"intent": intent, "target": clean_target},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya classified intent as future/non-executable '{intent}' (confidence: {laya_dec.confidence:.2f})"
            )

    def shutdown(self) -> None:
        """Terminate the underlying isolated process client."""
        if hasattr(self, "_client") and self._client:
            self._client.shutdown()
