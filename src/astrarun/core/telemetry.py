"""Production-native run-scoped causal telemetry engine for AstraRun.

Replaces post-hoc grep with structured causal events strictly scoped by run_id.
Every relevant event contains cryptographic hashes, causal parent linkage,
monotonic and wall timestamps, and execution context.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class CausalEventType(str, Enum):
    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    REQUEST_INGRESS_CLASSIFIED = "REQUEST_INGRESS_CLASSIFIED"
    REQUEST_DOWNSTREAM_SELECTED = "REQUEST_DOWNSTREAM_SELECTED"
    GOAL_INTERPRETED = "GOAL_INTERPRETED"
    PLAN_CREATED = "PLAN_CREATED"
    MODEL_REQUEST = "MODEL_REQUEST"
    MODEL_RESPONSE = "MODEL_RESPONSE"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    ACTION_AUTHORIZED = "ACTION_AUTHORIZED"
    ACTION_BLOCKED = "ACTION_BLOCKED"
    ACTION_DISPATCHED = "ACTION_DISPATCHED"
    ACTION_RESULT = "ACTION_RESULT"
    STATE_OBSERVED = "STATE_OBSERVED"
    POSTCONDITION_VERIFIED = "POSTCONDITION_VERIFIED"
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    ARTIFACT_DELIVERED = "ARTIFACT_DELIVERED"
    RESULT_PRESENTATION_REQUESTED = "RESULT_PRESENTATION_REQUESTED"
    RESULT_PRESENTED = "RESULT_PRESENTED"
    RESOURCE_REGISTERED = "RESOURCE_REGISTERED"
    RESOURCE_DISPOSED = "RESOURCE_DISPOSED"
    RESOURCE_RESTORATION_VERIFIED = "RESOURCE_RESTORATION_VERIFIED"
    GOAL_COMPLETED = "GOAL_COMPLETED"
    RUN_TERMINATED = "RUN_TERMINATED"
    TASK_FAILED = "TASK_FAILED"


class DownstreamPipeline(str, Enum):
    """Authoritative downstream pipeline handling an operational goal."""
    META_HANDLER = "META_HANDLER"
    PURE_QUERY = "PURE_QUERY"
    AGENT_EXECUTION_ENGINE = "AGENT_EXECUTION_ENGINE"
    UI_INTERACTION_FAST_PATH = "UI_INTERACTION_FAST_PATH"
    DETERMINISTIC_ROUTER = "DETERMINISTIC_ROUTER"
    MACHINE_QUERY_ENGINE = "MACHINE_QUERY_ENGINE"
    LEGACY_LAYA_WORKFLOW = "LEGACY_LAYA_WORKFLOW"
    INLINE_LEGACY = "INLINE_LEGACY"
    UNKNOWN = "UNKNOWN"


def compute_hash(data: Any) -> str:
    """Compute deterministic SHA-256 hash for strings, bytes, or JSON-serializable objects."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return hashlib.sha256(data).hexdigest()
    if isinstance(data, str):
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    try:
        serialized = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()
    except Exception:
        return hashlib.sha256(str(data).encode("utf-8")).hexdigest()


@dataclass
class CausalEvent:
    event_id: str
    run_id: str
    task_id: str
    parent_event_id: Optional[str]
    timestamp_monotonic: float
    timestamp_wall: float
    event_type: str
    component: str
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    model_id: Optional[str] = None
    capability: Optional[str] = None
    authorization_verdict: Optional[str] = None
    resulting_event_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "parent_event_id": self.parent_event_id,
            "timestamp_monotonic": self.timestamp_monotonic,
            "timestamp_wall": self.timestamp_wall,
            "event_type": self.event_type,
            "component": self.component,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "model_id": self.model_id,
            "capability": self.capability,
            "authorization_verdict": self.authorization_verdict,
            "resulting_event_id": self.resulting_event_id,
            "data": self.data,
        }


class CausalTelemetry:
    """Singleton causal telemetry coordinator managing run scopes and disk persistence."""

    _instance: Optional[CausalTelemetry] = None
    _lock = threading.RLock()

    def __init__(self):
        self._active_run_id: Optional[str] = None
        self._active_task_id: Optional[str] = None
        self._last_event_id: Optional[str] = None
        self._task_parent_links: Dict[str, str] = {}
        self._events_by_run: Dict[str, List[CausalEvent]] = {}
        self._active_contract: Optional[Any] = None
        self._execution_state: Dict[str, Any] = {}
        self._evidence_state: Dict[str, Any] = {}

    def set_active_contract(self, contract: Any) -> None:
        with self._lock:
            self._active_contract = contract

    def set_execution_state(self, state: Dict[str, Any]) -> None:
        with self._lock:
            self._execution_state.update(state)

    def set_evidence_state(self, state: Dict[str, Any]) -> None:
        with self._lock:
            self._evidence_state.update(state)

    @classmethod
    def get_instance(cls) -> CausalTelemetry:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def runs_dir(self) -> Path:
        from astrarun.core.paths import AstraPaths
        d = AstraPaths.data_dir() / "runs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def start_run(
        self,
        query: str,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        component: str = "AstraApplication",
    ) -> str:
        """Start a new root run scope and emit REQUEST_RECEIVED."""
        with self._lock:
            self._active_run_id = run_id or f"run_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
            self._active_task_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
            self._last_event_id = None
            self._events_by_run[self._active_run_id] = []
            self._active_contract = None
            self._execution_state = {}
            self._evidence_state = {}

            input_h = compute_hash(query)
            self._emit_raw(
                event_type=CausalEventType.REQUEST_RECEIVED.value,
                component=component,
                data={"query": query},
                input_hash=input_h,
            )
            return self._active_run_id

    @property
    def active_run_id(self) -> Optional[str]:
        return self._active_run_id

    @property
    def active_task_id(self) -> Optional[str]:
        return self._active_task_id

    def register_contract(
        self,
        contract: Any,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Register active GoalContract with causal telemetry and authoritative completion gate."""
        with self._lock:
            self._active_contract = contract
            eff_run_id = run_id or self._active_run_id
            eff_task_id = task_id or self._active_task_id
            try:
                from astrarun.agent.completion_gate import AuthoritativeCompletionGate
                AuthoritativeCompletionGate.register_contract(
                    contract=contract,
                    run_id=eff_run_id,
                    task_id=eff_task_id,
                )
            except Exception as err:
                import logging
                logging.getLogger("astrarun.core.telemetry").error(
                    "Failed to register contract with AuthoritativeCompletionGate: %s", err
                )

    def set_active_contract(self, contract: Any) -> None:
        """Set active contract for the current run scope."""
        self.register_contract(contract)

    def set_task_context(self, task_id: str, parent_task_id: Optional[str] = None) -> None:
        """Update active task ID and register parent task linkage."""
        with self._lock:
            if parent_task_id and self._active_task_id:
                self._task_parent_links[task_id] = parent_task_id
            self._active_task_id = task_id

    def _emit_raw(
        self,
        event_type: str,
        component: str,
        data: Optional[Dict[str, Any]] = None,
        parent_event_id: Optional[str] = None,
        input_hash: Optional[str] = None,
        output_hash: Optional[str] = None,
        model_id: Optional[str] = None,
        capability: Optional[str] = None,
        authorization_verdict: Optional[str] = None,
        resulting_event_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> CausalEvent:
        """Raw internal emission and persistence without gate recursion."""
        run_id = self._active_run_id or f"run_ad_hoc_{int(time.time())}"
        eff_task_id = task_id or self._active_task_id or "task_root"
        eff_parent = parent_event_id or self._last_event_id
        event_id = f"cev_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"

        event_data = dict(data or {})
        if eff_task_id in self._task_parent_links:
            event_data["parent_task_id"] = self._task_parent_links[eff_task_id]

        event = CausalEvent(
            event_id=event_id,
            run_id=run_id,
            task_id=eff_task_id,
            parent_event_id=eff_parent,
            timestamp_monotonic=time.monotonic(),
            timestamp_wall=time.time(),
            event_type=event_type,
            component=component,
            input_hash=input_hash,
            output_hash=output_hash,
            model_id=model_id,
            capability=capability,
            authorization_verdict=authorization_verdict,
            resulting_event_id=resulting_event_id,
            data=event_data,
        )

        if run_id not in self._events_by_run:
            self._events_by_run[run_id] = []
        self._events_by_run[run_id].append(event)
        self._last_event_id = event_id

        # Write event to run-specific file
        try:
            run_file = self.runs_dir / f"{run_id}.jsonl"
            with open(run_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")

            # Master append-only stream
            stream_file = self.runs_dir / "causal_stream.jsonl"
            with open(stream_file, "a", encoding="utf-8") as sf:
                sf.write(json.dumps(event.to_dict()) + "\n")
        except Exception as err:
            import logging
            logging.getLogger("astrarun.core.telemetry").error(
                "Failed to persist causal telemetry event %s for run %s: %s",
                event.event_id, run_id, err
            )

        return event

    def emit(
        self,
        event_type: str,
        component: str,
        data: Optional[Dict[str, Any]] = None,
        parent_event_id: Optional[str] = None,
        input_hash: Optional[str] = None,
        output_hash: Optional[str] = None,
        model_id: Optional[str] = None,
        capability: Optional[str] = None,
        authorization_verdict: Optional[str] = None,
        resulting_event_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Optional[CausalEvent]:
        """Record and persist a structured causal event, gated authoritatively."""
        with self._lock:
            run_id = self._active_run_id or f"run_ad_hoc_{int(time.time())}"
            eff_task_id = task_id or self._active_task_id or "task_root"

            if event_type == CausalEventType.GOAL_COMPLETED.value:
                ev_status = (data or {}).get("status")
                if ev_status != "SUCCESS":
                    import logging
                    logging.getLogger("astrarun.core.telemetry").error(
                        "GOAL_COMPLETED emission rejected: non-SUCCESS status '%s' cannot emit GOAL_COMPLETED (use RUN_TERMINATED/TASK_FAILED).",
                        ev_status,
                    )
                    return None

                from astrarun.agent.completion_gate import AuthoritativeCompletionGate
                run_events = [e.to_dict() for e in self._events_by_run.get(run_id, [])]
                ev_combined = dict(self._evidence_state)
                ev_combined.setdefault("events", run_events)
                ev_combined.setdefault("run_id", run_id)
                ev_combined.setdefault("task_id", eff_task_id)

                gate_res = AuthoritativeCompletionGate.can_complete(
                    goal_contract=self._active_contract,
                    execution_state=self._execution_state,
                    evidence_state=ev_combined,
                    active_run_id=run_id,
                    active_task_id=eff_task_id,
                )
                if not gate_res.can_complete:
                    import logging
                    logging.getLogger("astrarun.core.telemetry").warning(
                        "Direct emission of GOAL_COMPLETED rejected by AuthoritativeCompletionGate: %s",
                        gate_res.message
                    )
                    return None

            return self._emit_raw(
                event_type=event_type,
                component=component,
                data=data,
                parent_event_id=parent_event_id,
                input_hash=input_hash,
                output_hash=output_hash,
                model_id=model_id,
                capability=capability,
                authorization_verdict=authorization_verdict,
                resulting_event_id=resulting_event_id,
                task_id=task_id,
            )

    def end_run(
        self,
        status: str = "SUCCESS",
        message: str = "",
        component: str = "AstraApplication",
        goal_contract: Optional[Any] = None,
        execution_state: Optional[Dict[str, Any]] = None,
        evidence_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[CausalEvent]:
        """Finalize run scope, emitting GOAL_COMPLETED if approved or RUN_TERMINATED if not."""
        with self._lock:
            if not self._active_run_id:
                return None

            run_id = self._active_run_id
            task_id = self._active_task_id or "task_root"

            if goal_contract:
                self._active_contract = goal_contract
                from astrarun.agent.completion_gate import AuthoritativeCompletionGate
                AuthoritativeCompletionGate.register_contract(
                    contract=goal_contract,
                    run_id=run_id,
                    task_id=task_id,
                )
            if execution_state:
                self._execution_state.update(execution_state)
            if evidence_state:
                self._evidence_state.update(evidence_state)

            final_status = status
            final_message = message
            completed_flag = False

            if status == "SUCCESS":
                from astrarun.agent.completion_gate import AuthoritativeCompletionGate
                run_events = [e.to_dict() for e in self._events_by_run.get(run_id, [])]
                ev_combined = dict(self._evidence_state)
                ev_combined.setdefault("events", run_events)
                ev_combined.setdefault("run_id", run_id)
                ev_combined.setdefault("task_id", task_id)

                gate_res = AuthoritativeCompletionGate.can_complete(
                    goal_contract=self._active_contract,
                    execution_state=self._execution_state,
                    evidence_state=ev_combined,
                    active_run_id=run_id,
                    active_task_id=task_id,
                )
                if gate_res.can_complete:
                    completed_flag = True
                    final_status = "SUCCESS"
                    final_message = gate_res.message or message
                    ev = self._emit_raw(
                        event_type=CausalEventType.GOAL_COMPLETED.value,
                        component=component,
                        data={"status": final_status, "message": final_message, "completed": True},
                        task_id=task_id,
                    )
                else:
                    import logging
                    logging.getLogger("astrarun.core.telemetry").warning(
                        "Cannot end run %s with SUCCESS: %s", run_id, gate_res.message
                    )
                    final_status = gate_res.status
                    final_message = gate_res.message
                    completed_flag = False
                    ev = self._emit_raw(
                        event_type=CausalEventType.RUN_TERMINATED.value,
                        component=component,
                        data={"status": final_status, "message": final_message, "completed": False},
                        task_id=task_id,
                    )
            else:
                ev = self._emit_raw(
                    event_type=CausalEventType.RUN_TERMINATED.value,
                    component=component,
                    data={"status": final_status, "message": final_message, "completed": False},
                    task_id=task_id,
                )

            # Cleanup contract registration in AuthoritativeCompletionGate
            try:
                from astrarun.agent.completion_gate import AuthoritativeCompletionGate
                AuthoritativeCompletionGate.unregister_contract(
                    run_id=run_id,
                    task_id=task_id,
                )
            except Exception:
                pass

            self._active_run_id = None
            self._active_task_id = None
            self._active_contract = None
            self._execution_state = {}
            self._evidence_state = {}
            self._last_event_id = None
            return ev

    def get_run_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Retrieve all immutable causal events for a specific run_id."""
        with self._lock:
            # Check disk first
            run_file = self.runs_dir / f"{run_id}.jsonl"
            if run_file.exists():
                try:
                    events = []
                    seen_ids = set()
                    with open(run_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                ev = json.loads(line.strip())
                                eid = ev.get("event_id")
                                if eid and eid in seen_ids:
                                    continue
                                if eid:
                                    seen_ids.add(eid)
                                events.append(ev)
                    return events
                except Exception:
                    pass
            # Fallback to memory
            return [ev.to_dict() for ev in self._events_by_run.get(run_id, [])]

    @property
    def events(self) -> List[CausalEvent]:
        """Return all in-memory causal events across all runs."""
        with self._lock:
            all_evs = []
            for ev_list in self._events_by_run.values():
                all_evs.extend(ev_list)
            return all_evs

    def emit_ingress_classified(
        self,
        request_id: str,
        origin: str,
        ingress_route: str,
        reason_code: str,
        task_id: Optional[str] = None,
    ) -> Optional[CausalEvent]:
        """Emit structured REQUEST_INGRESS_CLASSIFIED causal telemetry event."""
        return self.emit(
            event_type=CausalEventType.REQUEST_INGRESS_CLASSIFIED.value,
            component="RequestBoundaryRouter",
            data={
                "request_id": request_id,
                "origin": origin,
                "ingress_route": ingress_route,
                "reason_code": reason_code,
            },
            task_id=task_id,
        )

    def emit_downstream_selected(
        self,
        request_id: str,
        downstream_pipeline: str | DownstreamPipeline,
        task_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[CausalEvent]:
        """Emit structured REQUEST_DOWNSTREAM_SELECTED causal telemetry event."""
        pipeline_val = (
            downstream_pipeline.value
            if hasattr(downstream_pipeline, "value")
            else str(downstream_pipeline)
        )
        data: Dict[str, Any] = {
            "request_id": request_id,
            "downstream_pipeline": pipeline_val,
        }
        if details:
            data.update(details)
        return self.emit(
            event_type=CausalEventType.REQUEST_DOWNSTREAM_SELECTED.value,
            component="AstraApplication.Dispatcher",
            data=data,
            task_id=task_id,
        )

    @property
    def active_run_id(self) -> Optional[str]:
        return self._active_run_id

    @property
    def active_task_id(self) -> Optional[str]:
        return self._active_task_id

    @property
    def last_event_id(self) -> Optional[str]:
        return self._last_event_id
