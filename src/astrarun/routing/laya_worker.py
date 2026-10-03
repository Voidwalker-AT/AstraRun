"""Isolated Out-of-Process Laya Worker for AstraRun 1.0.

Runs in a separate child process communicating via line-delimited JSON IPC over
stdin and stdout. Isolates PyTorch, transformers, and native weights from the
resident desktop GUI process (AstraRun.exe).

If this process suffers a fatal native crash (e.g. 0xc0000409, abort, CUDA exception),
AstraRun.exe remains completely unaffected.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, Optional


DEFAULT_QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": "Which action does the user intend?",
        "criteria": {
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
    }
}


class LayaWorker:
    """Dedicated inference worker for Laya semantic routing."""

    def __init__(self, model_id: str = "convaiinnovations/laya", device: str = "cpu") -> None:
        self.model_id = model_id
        self.device = device
        self._agent = None
        self._load_error: Optional[str] = None
        self._initialized = False

    def load_model(self) -> bool:
        """Attempt to load the underlying Laya model within this isolated process."""
        if self._initialized:
            return self._agent is not None

        self._initialized = True
        try:
            import laya
            t0 = time.perf_counter()
            self._agent = laya.load(model_id_or_path=self.model_id, device=self.device)
            load_ms = (time.perf_counter() - t0) * 1000
            sys.stderr.write(f"[LayaWorker] Model '{self.model_id}' loaded on {self.device} in {load_ms:.1f}ms\n")
            sys.stderr.flush()
            return True
        except ImportError as err:
            self._load_error = f"Laya package not installed in worker: {err}"
            sys.stderr.write(f"[LayaWorker] Warning: {self._load_error}\n")
            sys.stderr.flush()
            return False
        except Exception as err:
            self._load_error = f"Failed to load Laya model in worker: {err}"
            sys.stderr.write(f"[LayaWorker] Error: {self._load_error}\n")
            sys.stderr.flush()
            return False

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a single JSON request."""
        req_id = req.get("id", "req-0")
        action = req.get("action", "predict")

        if action == "ping":
            return {"id": req_id, "status": "pong", "loaded": self._agent is not None}

        if action == "warmup":
            ok = self.load_model()
            return {
                "id": req_id,
                "status": "ready" if ok else "failed",
                "loaded": ok,
                "device": self.device,
                "model": self.model_id,
                "error": self._load_error,
            }

        if action == "crash_for_test":
            sys.stderr.write("[LayaWorker] Simulating intentional worker crash for containment test\n")
            sys.stderr.flush()
            os._exit(99)

        if action == "predict":
            text = str(req.get("text", "")).strip()
            criteria = req.get("criteria")
            if not text:
                return {
                    "id": req_id,
                    "intent": "unknown",
                    "confidence": 0.0,
                    "probabilities": {},
                    "latency_ms": 0.0,
                    "error": "Empty query",
                }

            if not self._initialized:
                self.load_model()

            if self._agent is None:
                return {
                    "id": req_id,
                    "intent": "unknown",
                    "confidence": 0.0,
                    "probabilities": {},
                    "latency_ms": 0.0,
                    "error": self._load_error or "Laya model unavailable",
                }

            try:
                t0 = time.perf_counter()
                raw_result = self._agent.predict(text, criteria or DEFAULT_QUESTIONS)
                latency_ms = (time.perf_counter() - t0) * 1000

                if criteria:
                    return {
                        "id": req_id,
                        "raw_result": raw_result,
                        "latency_ms": round(latency_ms, 2),
                        "error": None,
                    }
                else:
                    answers = raw_result.get("answers", {})
                    intent_answer = answers.get("intent", {})
                    chosen_intent = intent_answer.get("choice", "unknown")
                    probs = intent_answer.get("probabilities", {})
                    conf = float(intent_answer.get("confidence", probs.get(chosen_intent, 0.0)))

                    return {
                        "id": req_id,
                        "intent": chosen_intent,
                        "confidence": conf,
                        "probabilities": probs,
                        "raw_result": raw_result,
                        "latency_ms": round(latency_ms, 2),
                        "error": None,
                    }
            except Exception as err:
                return {
                    "id": req_id,
                    "intent": "unknown",
                    "confidence": 0.0,
                    "probabilities": {},
                    "latency_ms": 0.0,
                    "error": str(err),
                }

        return {"id": req_id, "error": f"Unknown action: {action}"}


def run_worker_loop() -> int:
    """Read line-delimited JSON commands from stdin, write JSON responses to stdout."""
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass
    if sys.stdin is None or sys.stdout is None:
        return 1
    worker = LayaWorker()

    for line in sys.stdin:
        clean = line.strip()
        if not clean:
            continue
        try:
            req = json.loads(clean)
            if req.get("action") == "shutdown":
                sys.stdout.write(json.dumps({"id": req.get("id", "req-0"), "status": "shutting_down"}) + "\n")
                sys.stdout.flush()
                break

            resp = worker.handle_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as err:
            err_resp = {"error": f"Worker parse error: {err}"}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

    return 0


if __name__ == "__main__":
    sys.exit(run_worker_loop())
