"""AstraApplication: Unified Application Composition Root and Canonical Pipeline.

Centralizes lifecycle management, dependency injection, single-instance enforcement,
and the canonical user-request pipeline for AstraRun v0.9.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from astrarun.capabilities.models import CapabilityCategory, CapabilityResult, WindowEntity
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.store import ObservationStore
from astrarun.config.loader import AppConfig, load_config
from astrarun.context.engine import WorkstationContextEngine
from astrarun.core.logging import get_logger, setup_logging
from astrarun.core.models import ActionGateOutcome, ActionGateResult, Decision, RoutingContext, ToolRisk
from astrarun.discovery.apps import AppDiscoveryCache
from astrarun.discovery.folders import FolderResolver
from astrarun.hotkeys.manager import HotkeyManager
from astrarun.learning.aliases import AliasManager
from astrarun.learning.engine import LearningEngine
from astrarun.learning.memory import MemoryStore
from astrarun.learning.persistence import LearningPersistence
from astrarun.learning.skills import SkillManager
from astrarun.nlp.engine import NLPEngine
from astrarun.nlp.models import NLPEntityType, StructuredUtterance, UserRequest
from astrarun.policy.action_gate import ActionGate
from astrarun.projects.registry import ProjectRegistry
from astrarun.routing.deterministic import DeterministicRouter
from astrarun.routing.entity_resolver import EntityResolutionEngine, ProposedAction
from astrarun.search.index import SearchIndex
from astrarun.search.models import SearchResult
from astrarun.tasks.events import TaskEventBus
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.manager import TaskManager
from astrarun.tasks.models import Task, TaskError, TaskEventType, TaskResult, TaskStatus
from astrarun.telemetry.collector import RoutingEventCollector
from astrarun.telemetry.shadow_collector import LayaShadowEventCollector
from astrarun.usage.store import UsageStore
from astrarun.windows.controller import undo_last_window_move
from astrarun.windows.models import LayoutType
from astrarun.windows.monitors import enumerate_monitors, resolve_monitor
from astrarun.windows.policy import is_astrarun_window, register_astrarun_hwnd
from astrarun.windows.resolver import WindowResolution, WindowResolver
from astrarun.windows.undo import WindowRestoreStack, restore_stack
from astrarun.workflows.compiler import WorkflowCompiler
from astrarun.workflows.engine import WorkflowEngine
from astrarun.workflows.models import WorkflowProposal

logger = get_logger("astrarun.app")


@dataclass
class ExecutionResult:
    """Standardized response from the canonical request pipeline to the UI."""
    type: str  # "fast_path", "capability_result", "list_result", "confirm", "clarify", "blocked", "command", "reasoning_required", "error"
    success: bool = True
    message: str = ""
    task: Optional[Task] = None
    capability_result: Optional[CapabilityResult] = None
    data: Optional[dict[str, Any]] = None
    candidates: list[Any] = field(default_factory=list)
    confirmation_token: Optional[str] = None
    risk: ToolRisk = ToolRisk.LOW
    prompt: str = ""


class SingleInstanceLock:
    """Windows-native single instance lock using a named Win32 Mutex."""

    def __init__(self, mutex_name: str = "AstraRun_SingleInstance_Mutex"):
        self.mutex_name = mutex_name
        self.mutex_handle: Optional[int] = None
        self.is_primary_instance: bool = False

    def acquire(self) -> bool:
        if sys.platform != "win32":
            self.is_primary_instance = True
            return True

        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        self.mutex_handle = kernel32.CreateMutexW(None, False, self.mutex_name)
        last_error = kernel32.GetLastError()

        if last_error == ERROR_ALREADY_EXISTS:
            logger.warning("Another instance of AstraRun is already running.")
            self.is_primary_instance = False
            return False

        self.is_primary_instance = True
        logger.debug("Acquired single-instance mutex: %s", self.mutex_name)
        return True

    def release(self) -> None:
        if sys.platform == "win32" and self.mutex_handle:
            ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
            self.mutex_handle = None
            logger.debug("Released single-instance mutex.")


class AstraApplication:
    """
    Composition root holding and orchestrating all AstraRun subsystems.
    Enforces unified lifecycle, dependency injection, and single pipeline entry.
    """

    def __init__(self, config_dir: str = "config"):
        logger.info("Initializing AstraApplication composition root...")
        self.config_dir = config_dir

        # 1. Config & Logging
        self.config: AppConfig = load_config(config_dir)
        self.settings = self.config.settings

        # 2. Telemetry & Usage
        self.usage_store = UsageStore("data/usage.json")
        telem_cfg = self.settings.get("telemetry", {})
        self.telemetry = RoutingEventCollector(
            event_file=telem_cfg.get("file", "data/routing_events.jsonl"),
            enabled=bool(telem_cfg.get("enabled", True)),
            store_raw_request=bool(telem_cfg.get("store_raw_request", True)),
        )

        # 3. Discovery & Search
        self.app_cache = AppDiscoveryCache(self.config.configured_apps)
        self.folder_resolver = FolderResolver()
        self.search_index = SearchIndex(usage_store=self.usage_store)
        self.search_index.build_from_sources(
            apps=self.app_cache.apps,
            folders=self.folder_resolver.folders,
            urls=self.config.urls,
            aliases=self.config.aliases,
        )

        # 4. Project Registry & Workstation Context
        self.project_registry = ProjectRegistry("workspace.json")
        self.context_engine = WorkstationContextEngine(
            persistence_file="data/context_state.json",
            project_registry=self.project_registry,
        )

        # 5. Observation Store & Capability Registry
        self.observation_store = ObservationStore()
        self.capability_registry = CapabilityRegistry(observation_store=self.observation_store)

        # 6. Task Runtime & Event Bus
        os.makedirs("data", exist_ok=True)
        self.task_event_bus = TaskEventBus()
        self.task_ledger = TaskLedger("data/astra_history.db")
        self.task_manager = TaskManager(
            ledger=self.task_ledger,
            event_bus=self.task_event_bus,
        )

        # 7. Semantic Memory & Learning Subsystem
        learning_cfg = self.settings.get("learning", {})
        self.learning_persistence = LearningPersistence("data/astra_learning.db")
        self.memory_store = MemoryStore(persistence=self.learning_persistence)
        self.alias_manager = AliasManager(
            memory_store=self.memory_store,
            static_aliases=self.config.aliases,
        )
        self.skill_manager = SkillManager(persistence=self.learning_persistence)
        self.learning_engine = LearningEngine(
            config=learning_cfg,
            persistence=self.learning_persistence,
            memory_store=self.memory_store,
            alias_manager=self.alias_manager,
            skill_manager=self.skill_manager,
        )

        # 8. Entity Resolution, Windows & NLP
        self.entity_resolver = EntityResolutionEngine(
            project_registry=self.project_registry,
            alias_manager=self.alias_manager,
        )
        self.window_resolver = WindowResolver()
        self.restore_stack = restore_stack

        self.nlp_engine = NLPEngine(project_registry=self.project_registry)
        self.workflow_compiler = WorkflowCompiler(tool_registry=self.capability_registry)
        self.workflow_engine = WorkflowEngine(context_engine=self.context_engine)
        self.action_gate = ActionGate(capability_registry=self.capability_registry)

        # 9. Deterministic Router & Routing Context
        self.deterministic_router = DeterministicRouter()
        self.routing_context = RoutingContext(
            apps=self.app_cache.apps,
            folders=self.folder_resolver.folders,
            urls=self.config.urls,
            aliases=self.config.aliases,
            search_index=self.search_index,
            telemetry=self.telemetry,
            usage_store=self.usage_store,
        )

        # Single instance lock
        self.single_instance = SingleInstanceLock()

        # Track active origin window captured prior to launcher summon
        self.origin_window: Optional[WindowEntity] = None

        logger.info("AstraApplication composition root ready. Registered capabilities: %d", len(self.capability_registry.list_capabilities()))

    def capture_origin_window(self) -> Optional[WindowEntity]:
        """
        Capture the foreground window the user was interacting with immediately
        before AstraRun was summoned via hotkey. Guards against Astra mutating itself.
        """
        if sys.platform != "win32":
            return None

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or is_astrarun_window(hwnd):
            return None

        from astrarun.windows.discovery import foreground_window
        fg_res = foreground_window()
        if fg_res.success and fg_res.data:
            d = fg_res.data
            self.origin_window = WindowEntity(
                hwnd=d.get("hwnd", 0),
                title=d.get("title", ""),
                pid=d.get("pid", 0),
                app_id=d.get("app_id", ""),
                bounds=d.get("bounds", (0, 0, 0, 0)),
                state=d.get("state", "normal"),
                visible=True,
            )
            logger.debug("Captured origin window: '%s' (HWND %d)", self.origin_window.title, self.origin_window.hwnd)
            return self.origin_window
        return None

    def refresh_discovery(self) -> None:
        """Rescan installed apps, folders, and rebuild search index."""
        logger.info("Refreshing applications and search index...")
        self.app_cache.refresh()
        self.folder_resolver.refresh()
        self.search_index.build_from_sources(
            apps=self.app_cache.apps,
            folders=self.folder_resolver.folders,
            urls=self.config.urls,
            aliases=self.config.aliases,
        )
        self.routing_context.apps = self.app_cache.apps
        self.routing_context.folders = self.folder_resolver.folders

    def _complete_task(self, task: Task, cap_res: CapabilityResult) -> None:
        """Helper to build TaskResult and invoke task_manager.complete_task."""
        result = TaskResult(
            task_id=task.id,
            success=cap_res.success,
            status=TaskStatus.COMPLETED if cap_res.success else TaskStatus.FAILED,
            message=cap_res.message,
            summary=cap_res.message,
            data=cap_res.data if isinstance(cap_res.data, dict) else {},
            capabilities_used=[cap_res.capability] if cap_res.capability else [],
            duration_ms=cap_res.latency_ms,
        )
        self.task_manager.complete_task(task.id, result)
        if hasattr(self, "learning_engine") and self.learning_engine:
            self.learning_engine.ingest_task_async(task)

    def _fail_task(self, task: Task, message: str, capability: Optional[str] = None) -> None:
        """Helper to build TaskError and invoke task_manager.fail_task."""
        err = TaskError(code="EXECUTION_ERROR", message=message, capability=capability)
        self.task_manager.fail_task(task.id, err)
        if hasattr(self, "learning_engine") and self.learning_engine:
            self.learning_engine.ingest_task_async(task)

    def handle_request(
        self,
        query: str,
        origin_window: Optional[int | WindowEntity] = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """
        Canonical entry point for all natural language and launcher commands.
        Enforces: Fast Path -> Direct Navigation -> Rich NLP & Capabilities.
        """
        clean = query.strip()
        if not clean:
            return ExecutionResult(type="error", success=False, message="Empty query.")

        active_origin = origin_window or self.origin_window
        if isinstance(active_origin, int):
            active_origin = WindowEntity(
                hwnd=active_origin,
                title=f"Window {active_origin}",
                pid=9999,
                app_id="active_app",
            )

        # -------------------------------------------------------------
        # 1. DIRECT NAVIGATION & SYSTEM COMMANDS
        # -------------------------------------------------------------
        lower_q = clean.lower()

        if lower_q in ("history", "open history", "show history"):
            return ExecutionResult(type="command", success=True, message="open_history")

        if lower_q in ("memory", "show memory", "what have you learned?", "learned aliases", "open memory"):
            return ExecutionResult(type="command", success=True, message="open_memory")

        if lower_q in ("skills", "show skills", "learned skills", "open skills"):
            return ExecutionResult(type="command", success=True, message="open_skills")

        if lower_q in ("settings", "preferences", "config", "open settings"):
            return ExecutionResult(type="command", success=True, message="open_settings")

        if lower_q in ("diagnostics", "system diagnostics", "show diagnostics", "open diagnostics"):
            return ExecutionResult(type="command", success=True, message="open_diagnostics")

        if lower_q in ("undo", "undo window", "undo last window move", "undo layout"):
            undo_res = undo_last_window_move()
            return ExecutionResult(
                type="capability_result",
                success=undo_res.success,
                message=undo_res.message,
                capability_result=undo_res,
            )

        if lower_q in ("help", "what can you do?", "capabilities", "commands"):
            caps = self.capability_registry.list_capabilities()
            grouped: dict[str, list[str]] = {}
            for c in caps:
                cat = c.category.value
                grouped.setdefault(cat, []).append(f"• {c.id}: {c.description}")
            return ExecutionResult(
                type="list_result",
                success=True,
                message="AstraRun Workstation Capabilities",
                data={"grouped_capabilities": grouped, "count": len(caps)},
            )

        # -------------------------------------------------------------
        # 2. FAST PATH: Instant Deterministic Routing (< 3ms)
        # -------------------------------------------------------------
        # Check if the query is a simple prefix or single-word app launch
        words = clean.split()
        is_simple_verb = words[0].lower() in ("open", "launch", "start", "show", "go", "run") and len(words) <= 3
        is_single_term = len(words) == 1 and not re.search(r"[:#\d]", clean)

        if is_simple_verb or is_single_term:
            decision = self.deterministic_router.route(clean, self.routing_context)
            if decision.is_resolved and decision.tool != "unknown":
                logger.info("Fast path triggered: '%s' -> %s", clean, decision.tool)
                task = self.task_manager.create_task(request_text=clean, source="user_fast_path")
                self.task_manager.transition_status(task.id, TaskStatus.RUNNING)

                # Dispatch tool (map 'open_app' to 'open_application')
                tool_name = "open_application" if decision.tool == "open_app" else decision.tool
                if dry_run and tool_name == "open_application":
                    cap_res = CapabilityResult.ok(
                        capability="open_application",
                        message=f"Application '{decision.args.get('app', '')}' launched successfully (dry run).",
                        data=decision.args,
                    )
                else:
                    cap_res = self.capability_registry.execute(tool_name, decision.args, task_id=task.id)

                if cap_res.success:
                    self._complete_task(task, cap_res)
                    if self.usage_store:
                        target_id = decision.args.get("app") or decision.args.get("folder") or decision.args.get("url")
                        if target_id:
                            self.usage_store.record_launch(target_id)
                    return ExecutionResult(
                        type="fast_path",
                        success=True,
                        message=cap_res.message,
                        task=task,
                        capability_result=cap_res,
                    )
                else:
                    self._fail_task(task, cap_res.message, capability=tool_name)
                    return ExecutionResult(
                        type="error",
                        success=False,
                        message=cap_res.message,
                        task=task,
                        capability_result=cap_res,
                    )

        # -------------------------------------------------------------
        # 3. RICH PATH: Task Creation, Hybrid NLP, Entity Resolution, Safety Gating
        # -------------------------------------------------------------
        task = self.task_manager.create_task(request_text=clean, source="user_launcher")
        self.task_manager.transition_status(task.id, TaskStatus.PARSING)

        try:
            # Parse query into StructuredUtterance IR
            snapshot = self.context_engine.get_snapshot()
            utterance: StructuredUtterance = self.nlp_engine.parse(
                request=UserRequest(text=clean),
                context=snapshot,
            )

            # Check for AI Bridge Reasoning escalation
            escalation = self.nlp_engine.check_reasoning_escalation(utterance)
            if escalation is not None:
                self.task_manager.transition_status(task.id, TaskStatus.WAITING_CLARIFICATION)
                return ExecutionResult(
                    type="reasoning_required",
                    success=True,
                    message=escalation.explanation or "Complex diagnostic reasoning required.",
                    task=task,
                    data=escalation.to_dict(),
                )

            # Specialized Window Resolution for Window Actions
            is_window_action = any(
                c.action in (
                    "move_window", "move_window_to_monitor", "snap_window_left",
                    "snap_window_right", "maximize_window", "minimize_window",
                    "restore_window", "focus_window", "close_window"
                )
                for c in utterance.clauses
            )

            resolved_window: Optional[WindowEntity] = None
            if is_window_action:
                ctx_win = None
                if getattr(snapshot, "foreground_window", None):
                    ctx_win = WindowEntity(
                        hwnd=snapshot.foreground_window,
                        title=snapshot.foreground_title or "",
                        pid=snapshot.foreground_pid or 0,
                    )
                win_res: WindowResolution = self.window_resolver.resolve(
                    query=clean,
                    origin_window=active_origin,
                    context_last_window=ctx_win,
                )
                if win_res.is_ambiguous:
                    self.task_manager.transition_status(task.id, TaskStatus.WAITING_CLARIFICATION)
                    return ExecutionResult(
                        type="clarify",
                        success=False,
                        message=win_res.reason,
                        task=task,
                        candidates=[w.to_dict() for w in win_res.candidates],
                        prompt=f"Which window did you mean for '{clean}'?",
                    )
                elif win_res.is_resolved:
                    resolved_window = win_res.window

            # Compile into WorkflowProposal
            proposal: WorkflowProposal = self.workflow_compiler.compile(utterance)

            # Inject resolved window HWND/PID into step arguments if present
            if resolved_window:
                for step in proposal.steps:
                    if "window" in step.tool or step.tool in ("focus_window", "close_window", "move_window", "snap_window_left", "snap_window_right", "maximize_window", "minimize_window", "restore_window", "move_window_to_monitor"):
                        step.arguments["hwnd"] = resolved_window.hwnd
                        step.arguments["pid"] = resolved_window.pid

            # Check if compiler blocked the request
            if proposal.status == "BLOCKED":
                reasons = "; ".join(proposal.blocked_reasons)
                self.task_manager.block_task(task.id, reason=reasons)
                return ExecutionResult(
                    type="blocked",
                    success=False,
                    message=f"Action blocked by policy: {reasons}",
                    task=task,
                )

            # Successfully parsed and compiled -> transition to READY
            self.task_manager.transition_status(task.id, TaskStatus.READY)

            # Evaluate Proposal through ActionGate Safety Arbiter
            first_step = proposal.steps[0] if proposal.steps else None
            tool_name = first_step.tool if first_step else "unknown"
            args = first_step.arguments if first_step else {}
            action = ProposedAction(
                action_type=tool_name,
                raw_query=clean,
                target=clean,
                entity_id=clean,
                tool=tool_name,
                arguments=args,
                confidence=1.0,
                status="resolved" if proposal.status == "READY" else proposal.status.lower(),
                requires_confirmation=proposal.requires_confirmation,
                policy_allowed=proposal.status != "BLOCKED",
            )
            gate_decision: ActionGateResult = self.action_gate.evaluate(action)

            if gate_decision.status == ActionGateOutcome.BLOCK:
                self.task_manager.block_task(task.id, reason=gate_decision.reason)
                return ExecutionResult(
                    type="blocked",
                    success=False,
                    message=f"Blocked: {gate_decision.reason}",
                    task=task,
                )

            if gate_decision.status == ActionGateOutcome.CLARIFY:
                self.task_manager.transition_status(task.id, TaskStatus.WAITING_CLARIFICATION)
                return ExecutionResult(
                    type="clarify",
                    success=False,
                    message=gate_decision.reason,
                    task=task,
                    candidates=gate_decision.candidates,
                    prompt="Clarification needed",
                )

            if gate_decision.status == ActionGateOutcome.CONFIRM:
                self.task_manager.transition_status(task.id, TaskStatus.WAITING_CONFIRMATION)
                return ExecutionResult(
                    type="confirm",
                    success=False,
                    message=gate_decision.reason,
                    task=task,
                    confirmation_token=gate_decision.confirmation_token,
                    risk=gate_decision.risk,
                    prompt=f"Confirm action: {gate_decision.reason}",
                )

            # ALLOW: Safe execution path
            self.task_manager.transition_status(task.id, TaskStatus.RUNNING)

            # Execute steps
            if len(proposal.steps) == 1:
                step = proposal.steps[0]
                cap_res = self.task_manager.execute_capability(
                    task_id=task.id,
                    capability_id=step.tool,
                    arguments=step.arguments,
                    registry=self.capability_registry,
                )
            else:
                step_results = []
                all_ok = True
                last_msg = ""
                for step in proposal.steps:
                    s_res = self.task_manager.execute_capability(
                        task_id=task.id,
                        capability_id=step.tool,
                        arguments=step.arguments,
                        registry=self.capability_registry,
                    )
                    step_results.append(s_res)
                    last_msg = s_res.message
                    if not s_res.success:
                        all_ok = False
                        break
                cap_res = CapabilityResult(
                    success=all_ok,
                    capability="workflow",
                    message=f"Workflow executed {len(step_results)} step(s): {last_msg}",
                    data={"steps": [s.to_dict() for s in step_results]},
                )

            if cap_res.success:
                self._complete_task(task, cap_res)
                # Determine display card type
                res_type = "list_result" if isinstance(cap_res.data, dict) and any(isinstance(v, list) for v in cap_res.data.values()) else "capability_result"
                return ExecutionResult(
                    type=res_type,
                    success=True,
                    message=cap_res.message,
                    task=task,
                    capability_result=cap_res,
                    data=cap_res.data,
                )
            else:
                self._fail_task(task, cap_res.message, capability=cap_res.capability)
                return ExecutionResult(
                    type="error",
                    success=False,
                    message=cap_res.message,
                    task=task,
                    capability_result=cap_res,
                )

        except Exception as err:
            logger.exception("Unexpected error processing request '%s': %s", clean, err)
            self._fail_task(task, str(err))
            return ExecutionResult(
                type="error",
                success=False,
                message=f"An error occurred while executing the request: {err}",
                task=task,
            )

    def shutdown(self) -> None:
        """Gracefully terminate background workers, flush databases, and release locks."""
        logger.info("Initiating graceful shutdown of AstraApplication...")
        try:
            if hasattr(self, "single_instance") and self.single_instance:
                self.single_instance.release()
            logger.info("AstraApplication shutdown complete.")
        except Exception as err:
            logger.error("Error during AstraApplication shutdown: %s", err)
