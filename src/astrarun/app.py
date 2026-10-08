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

from astrarun.capabilities.models import CapabilityCategory, CapabilityErrorCode, CapabilityResult, WindowEntity
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.store import ObservationStore
from astrarun.config.loader import AppConfig, load_config
from astrarun.context.engine import WorkstationContextEngine
from astrarun.core.logging import get_logger, setup_logging
from astrarun.core.models import ActionGateOutcome, ActionGateResult, Decision, RoutingContext, ToolRisk
from astrarun.discovery.apps import AppDiscoveryCache
from astrarun.discovery.folders import FolderResolver
from astrarun.hotkeys.manager import HotkeyManager
from astrarun.interaction.keyboard import parse_shortcut
from astrarun.learning.aliases import AliasManager
from astrarun.learning.engine import LearningEngine
from astrarun.learning.memory import MemoryStore
from astrarun.learning.persistence import LearningPersistence
from astrarun.learning.skills import SkillManager
from astrarun.nlp.engine import NLPEngine
import threading

from astrarun.machine.model import MachineModel
from astrarun.machine.query_engine import MachineQueryEngine
from astrarun.nlp.ir import ParsedClause, ParsedRequest
from astrarun.nlp.structure_engine import NeuralStructureEngine
from astrarun.nlp.models import NLPEntityType, StructuredUtterance, UserRequest
from astrarun.policy.action_gate import ActionGate
from astrarun.projects.registry import ProjectRegistry
from astrarun.routing.decision_fusion import DecisionFusionEngine, FusedExecutionPlan
from astrarun.routing.deterministic import DeterministicRouter
from astrarun.routing.entity_resolver import EntityResolutionEngine, ProposedAction
from astrarun.routing.laya import LayaRouter
from astrarun.routing.laya_sandwich import LayaSandwichRouter
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
from astrarun.workflows.context import WorkflowContext
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
            if self.mutex_handle:
                kernel32.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
            existing_pid = None
            try:
                from astrarun.core.paths import AstraPaths
                state_file = AstraPaths.state_file_path()
                if state_file.exists():
                    with open(state_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        existing_pid = data.get("pid")
            except Exception:
                pass
            logger.warning(
                "Another instance of AstraRun is already running (Mutex '%s' held%s).",
                self.mutex_name,
                f", existing PID={existing_pid}" if existing_pid else "",
            )
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

    def __init__(self, config_dir: Optional[str | Path] = None):
        from astrarun.core.paths import AstraPaths
        resolved_config_dir = Path(config_dir) if config_dir else AstraPaths.config_dir()
        logger.info("Initializing AstraApplication composition root (config_dir=%s)...", resolved_config_dir)
        self.config_dir = resolved_config_dir

        # 1. Config & Logging
        self.config: AppConfig = load_config(resolved_config_dir)
        self.settings = self.config.settings
        logger.info("[STARTUP_STAGE] CONFIG_LOADED")

        from astrarun.core.paths import AstraPaths
        data_dir = AstraPaths.data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)

        # 2. Telemetry & Usage
        self.usage_store = UsageStore(str(data_dir / "usage.json"))
        telem_cfg = self.settings.get("telemetry", {})
        self.telemetry = RoutingEventCollector(
            event_file=telem_cfg.get("file", str(data_dir / "routing_events.jsonl")),
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
        self.project_registry = ProjectRegistry()
        self.context_engine = WorkstationContextEngine(
            persistence_file=str(data_dir / "context_state.json"),
            project_registry=self.project_registry,
        )
        logger.info("[STARTUP_STAGE] CONTEXT_ENGINE_INITIALIZED")

        # 5. Observation Store & Capability Registry
        self.observation_store = ObservationStore()
        self.capability_registry = CapabilityRegistry(observation_store=self.observation_store)
        self._builtin_capability_ids = {c.id for c in self.capability_registry.list_capabilities()}
        logger.info("[STARTUP_STAGE] CAPABILITY_REGISTRY_INITIALIZED (count=%d)", len(self.capability_registry.list_capabilities()))

        # 6. Task Runtime & Event Bus
        self.task_event_bus = TaskEventBus()
        self.task_ledger = TaskLedger(str(data_dir / "astra_history.db"))
        self.task_manager = TaskManager(
            ledger=self.task_ledger,
            event_bus=self.task_event_bus,
        )
        from astrarun.tasks.runtime import TaskRuntime
        self.task_runtime = TaskRuntime(
            app=self,
            event_bus=self.task_event_bus,
            ledger=self.task_ledger,
        )
        logger.info("[STARTUP_STAGE] TASK_LEDGER_INITIALIZED")

        # 7. Semantic Memory & Learning Subsystem
        learning_cfg = self.settings.get("learning", {})
        self.learning_persistence = LearningPersistence(str(data_dir / "astra_learning.db"))
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
        logger.info("[STARTUP_STAGE] LEARNING_DB_INITIALIZED")

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
        from astrarun.security.execution_broker import ExecutionBroker
        self.execution_broker = ExecutionBroker(
            action_gate=self.action_gate,
            capability_registry=self.capability_registry,
        )
        self.task_manager.execution_broker = self.execution_broker

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

        # 10. Neural NLP Sandwich & Decision Fusion (v0.10.3)
        self.laya_router = LayaRouter(config=self.settings.get("laya", {}))
        self.laya_sandwich = LayaSandwichRouter(laya_router=self.laya_router)
        self.neural_structure_engine = NeuralStructureEngine()
        self.decision_fusion = DecisionFusionEngine()

        # 11. Autonomous Agent Execution Engine (v0.11)
        from astrarun.agent.loop import AgentExecutionEngine
        self.agent_engine = AgentExecutionEngine(
            registry=self.capability_registry,
            execution_broker=self.execution_broker,
        )

        # 12. Machine Model & Authoritative Workstation Query Engine (v1.0)
        self.machine_model = MachineModel.get_instance()
        self.machine_query_engine = MachineQueryEngine(machine_model=self.machine_model)

        # 13. Production Cognitive, Memory, Perception & Browser Facades
        from astrarun.cognition.service import ModelService
        from astrarun.memory.service import MemoryService
        from astrarun.perception.service import PerceptionService
        from astrarun.browser.service import BrowserService

        self.model_service = ModelService.get_instance()
        self.memory_service = MemoryService.get_instance()
        self.perception_service = PerceptionService.get_instance()
        self.browser_service = BrowserService.get_instance()

        # Single instance lock & local Named Pipe IPC
        from astrarun.core.single_instance import AstraSingleInstance
        self.single_instance = AstraSingleInstance()

        # Track active origin window captured prior to launcher summon
        self.origin_window: Optional[WindowEntity] = None

        # Orphan resource recovery from prior crashed sessions (Milestone F0-15)
        try:
            from astrarun.tasks.resource_ledger import AstraResourceLedger
            self.resource_ledger = AstraResourceLedger.get_instance(self.task_ledger.db_path if hasattr(self, "task_ledger") else None)
            recovered = self.resource_ledger.recover_orphaned_resources()
            if recovered:
                logger.info("Recovered %d orphaned resource(s) from prior session.", len(recovered))
        except Exception as e:
            logger.warning("Could not execute orphan resource recovery: %s", e)

        logger.info("AstraApplication composition root ready. Registered capabilities: %d", len(self.capability_registry.list_capabilities()))

    def get_interrupted_task_prompt(self) -> Optional[Dict[str, Any]]:
        """Surface prompt if interrupted recoverable tasks exist from prior session."""
        if not self.interrupted_tasks:
            return None
        latest = self.interrupted_tasks[0]
        return {
            "title": "Interrupted task found",
            "message": f"Task '{latest['request_text']}' was interrupted when Astra closed.\nWould you like to resume it?",
            "task_id": latest["task_id"],
            "options": [
                {"id": "resume", "label": "Resume"},
                {"id": "inspect", "label": "Inspect"},
                {"id": "discard", "label": "Discard"},
            ],
        }

    def _prewarm_neural_models_async(self) -> None:
        """Asynchronously pre-warm the spaCy linguistic engine in a background daemon thread."""
        if "pytest" in sys.modules:
            return
        def _prewarm():
            try:
                self.neural_structure_engine.get_nlp()
            except Exception as err:
                logger.debug("Asynchronous neural pre-warm completed with status: %s", err)
        t = threading.Thread(target=_prewarm, name="NeuralPrewarmWorker", daemon=True)
        t.start()

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

    def show_task_center(self) -> None:
        """Summon TaskCenterWindow from any component."""
        if hasattr(self, "launcher") and self.launcher:
            self.launcher.open_task_center()

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

    def _execute_through_broker(
        self,
        capability_id: str,
        parameters: Dict[str, Any],
        task_id: Optional[str] = None,
        is_observe: bool = False,
        source: str = "ui_interaction",
    ) -> CapabilityResult:
        """Route capability execution through authoritative ExecutionBroker and ActionGate."""
        from astrarun.security.execution_broker import ActionCategory, ActionProposal
        category = ActionCategory.OBSERVE if is_observe else ActionCategory.ACT
        prop = ActionProposal(
            category=category,
            capability_id=capability_id,
            parameters=parameters,
            task_id=task_id,
            source=source,
        )
        broker_res = self.execution_broker.execute(prop)
        err_code = CapabilityErrorCode.NONE
        if broker_res.requires_confirmation:
            err_code = CapabilityErrorCode.PERMISSION_DENIED
        elif broker_res.blocked:
            err_code = CapabilityErrorCode.PERMISSION_DENIED

        return CapabilityResult(
            capability=capability_id,
            success=broker_res.success,
            message=broker_res.message,
            data=broker_res.data,
            error_code=err_code,
            latency_ms=broker_res.duration_ms,
        )

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

        words = clean.split()
        from astrarun.routing.deterministic import has_compound_indicators
        has_compound = has_compound_indicators(clean)

        active_origin = origin_window or self.origin_window
        if active_origin is None and dry_run:
            active_origin = WindowEntity(
                hwnd=1001,
                title="Active Mock Window",
                pid=9999,
                app_id="mock_app",
            )
        elif isinstance(active_origin, int):
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

        if lower_q in ("hotkey", "hotkey status", "hotkey diagnostics", "diagnostics hotkey", "check hotkey"):
            hk_diag = self.hotkey_manager.get_diagnostics() if hasattr(self, "hotkey_manager") and self.hotkey_manager else {
                "is_registered": True,
                "modifiers": ["Alt"],
                "key": "Space",
                "trigger_count": 0,
            }
            return ExecutionResult(
                type="capability_result",
                success=True,
                message=f"Hotkey Status: {'Registered' if hk_diag.get('is_registered') else 'Unregistered'} ({'+'.join(hk_diag.get('modifiers', []))}+{hk_diag.get('key', '')})",
                data=hk_diag,
            )

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
        # 1.25 AUTONOMOUS WORKSTATION AGENT GOALS (v0.11 / v0.11.1)
        # -------------------------------------------------------------
        from astrarun.agent.models import AgentTaskStatus
        import re

        is_agent_goal = False
        if re.search(r"\bbattery\s+report\b", clean, re.IGNORECASE) or re.search(r"\b(?:scan|check|show|connect|disconnect).*wifi\b|\bwifi\b", clean, re.IGNORECASE):
            is_agent_goal = True
        elif has_compound and any(w in lower_q for w in ("save", "report", "reverse", "summary", "find", "metrics")):
            is_agent_goal = True
        elif hasattr(self, "agent_engine") and self.agent_engine and hasattr(self, "_builtin_capability_ids"):
            # Check if indexer has a high-confidence match for dynamic / plug-in capabilities (e.g. reverse_text)
            top_cand = self.agent_engine.planner.indexer.retrieve(clean, top_k=1, min_score=0.7)
            if top_cand and top_cand[0].capability_id not in self._builtin_capability_ids:
                is_agent_goal = True

        if is_agent_goal:
            agent_task = self.agent_engine.execute_goal(clean)
            if agent_task.status == AgentTaskStatus.COMPLETED:
                last_step = agent_task.plan.steps[-1] if agent_task.plan.steps else None
                res_data = last_step.result.data if (last_step and last_step.result) else {}
                msg = last_step.result.message if (last_step and last_step.result) else "Task completed successfully."
                return ExecutionResult(
                    type="capability_result",
                    success=True,
                    message=msg,
                    data=res_data,
                    capability_result=last_step.result if last_step else None,
                )
            elif agent_task.status == AgentTaskStatus.FAILED and "Invalid plan" in (agent_task.error or ""):
                # If plan was invalid or unresolvable by agent runtime, fall through to rich interactive pipeline
                pass
            else:
                return ExecutionResult(
                    type="error",
                    success=False,
                    message=agent_task.error or "Agent goal execution failed.",
                )


        # -------------------------------------------------------------
        # 1.5 UI INTERACTION & CONTROL GROUNDING (v0.10)
        # -------------------------------------------------------------
        shortcut_obj = None
        if not has_compound and lower_q.startswith("press "):
            shortcut_obj = parse_shortcut(lower_q[6:])
        elif not has_compound and "+" in lower_q and len(words) == 1:
            shortcut_obj = parse_shortcut(lower_q)

        if shortcut_obj:
            target_hwnd = active_origin.hwnd if active_origin else None
            task = self.task_manager.create_task(request_text=clean, source="user_shortcut")
            self.task_manager.transition_status(task.id, TaskStatus.RUNNING)
            cap_res = self._execute_through_broker(
                "press_keyboard_shortcut",
                {"shortcut": shortcut_obj.canonical_string, "hwnd": target_hwnd},
                task_id=task.id,
            )
            if cap_res.success:
                self._complete_task(task, cap_res)
                return ExecutionResult(type="capability_result", success=True, message=cap_res.message, task=task, capability_result=cap_res)
            else:
                self._fail_task(task, cap_res.message, capability="press_keyboard_shortcut")
                return ExecutionResult(type="error", success=False, message=cap_res.message, task=task, capability_result=cap_res)

        if not has_compound and lower_q in ("copy", "copy this", "copy selection"):
            target_hwnd = active_origin.hwnd if active_origin else None
            cap_res = self._execute_through_broker("press_keyboard_shortcut", {"shortcut": "Ctrl+C", "hwnd": target_hwnd})
            return ExecutionResult(type="capability_result", success=cap_res.success, message=cap_res.message, capability_result=cap_res)
        if not has_compound and lower_q in ("paste", "paste here", "paste text"):
            target_hwnd = active_origin.hwnd if active_origin else None
            cap_res = self._execute_through_broker("press_keyboard_shortcut", {"shortcut": "Ctrl+V", "hwnd": target_hwnd})
            return ExecutionResult(type="capability_result", success=cap_res.success, message=cap_res.message, capability_result=cap_res)
        if not has_compound and lower_q in ("select all", "select all text"):
            target_hwnd = active_origin.hwnd if active_origin else None
            cap_res = self._execute_through_broker("press_keyboard_shortcut", {"shortcut": "Ctrl+A", "hwnd": target_hwnd})
            return ExecutionResult(type="capability_result", success=cap_res.success, message=cap_res.message, capability_result=cap_res)

        if not has_compound and lower_q in ("inspect ui", "inspect window ui", "what buttons are in this window?", "what controls are in this window?", "show controls", "list buttons"):
            target_hwnd = active_origin.hwnd if active_origin else None
            cap_res = self._execute_through_broker("inspect_window_ui", {"hwnd": target_hwnd}, is_observe=True)
            return ExecutionResult(type="capability_result", success=cap_res.success, message=cap_res.message, capability_result=cap_res, data=cap_res.data)

        if not has_compound and lower_q.startswith("click "):
            target = clean[6:].strip()
            target_hwnd = active_origin.hwnd if active_origin else None
            task = self.task_manager.create_task(request_text=clean, source="user_interaction")
            self.task_manager.transition_status(task.id, TaskStatus.RUNNING)

            cap_res = self._execute_through_broker(
                "click_ui_element",
                {"target": target, "hwnd": target_hwnd, "force": False},
                task_id=task.id,
            )
            if cap_res.error_code == CapabilityErrorCode.PERMISSION_DENIED:
                self.task_manager.transition_status(task.id, TaskStatus.WAITING_CONFIRMATION)
                return ExecutionResult(
                    type="confirm",
                    success=False,
                    message=cap_res.message,
                    task=task,
                    prompt=f"Confirm destructive click: {cap_res.message}",
                )
            if cap_res.error_code == CapabilityErrorCode.AMBIGUOUS:
                self.task_manager.transition_status(task.id, TaskStatus.WAITING_CLARIFICATION)
                return ExecutionResult(
                    type="clarify",
                    success=False,
                    message=cap_res.message,
                    task=task,
                    candidates=cap_res.data.get("candidates", []),
                    prompt="Which control did you mean?",
                )
            if cap_res.success:
                self._complete_task(task, cap_res)
                return ExecutionResult(type="capability_result", success=True, message=cap_res.message, task=task, capability_result=cap_res)
            else:
                self._fail_task(task, cap_res.message, capability="click_ui_element")
                return ExecutionResult(type="error", success=False, message=cap_res.message, task=task, capability_result=cap_res)

        if not has_compound and lower_q.startswith("type "):
            type_args = clean[5:].strip()
            target_hwnd = active_origin.hwnd if active_origin else None
            task = self.task_manager.create_task(request_text=clean, source="user_interaction")
            self.task_manager.transition_status(task.id, TaskStatus.RUNNING)

            if " into " in type_args:
                val, target_field = type_args.split(" into ", 1)
                val = val.strip().strip('"\'')
                cap_res = self._execute_through_broker(
                    "set_ui_element_value",
                    {"target": target_field.strip(), "value": val, "hwnd": target_hwnd},
                    task_id=task.id,
                )
            else:
                val = type_args.strip().strip('"\'')
                cap_res = self._execute_through_broker(
                    "type_text",
                    {"text": val, "hwnd": target_hwnd},
                    task_id=task.id,
                )

            if cap_res.success:
                self._complete_task(task, cap_res)
                return ExecutionResult(type="capability_result", success=True, message=cap_res.message, task=task, capability_result=cap_res)
            else:
                self._fail_task(task, cap_res.message, capability="type_text")
                return ExecutionResult(type="error", success=False, message=cap_res.message, task=task, capability_result=cap_res)

        if not has_compound and lower_q.startswith("toggle "):
            target = clean[7:].strip()
            target_hwnd = active_origin.hwnd if active_origin else None
            task = self.task_manager.create_task(request_text=clean, source="user_interaction")
            self.task_manager.transition_status(task.id, TaskStatus.RUNNING)
            cap_res = self._execute_through_broker(
                "toggle_ui_element",
                {"target": target, "hwnd": target_hwnd},
                task_id=task.id,
            )
            if cap_res.success:
                self._complete_task(task, cap_res)
                return ExecutionResult(type="capability_result", success=True, message=cap_res.message, task=task, capability_result=cap_res)
            else:
                self._fail_task(task, cap_res.message, capability="toggle_ui_element")
                return ExecutionResult(type="error", success=False, message=cap_res.message, task=task, capability_result=cap_res)

        if not has_compound and lower_q.startswith("focus ") and not any(w in lower_q for w in ("window", "code", "notepad", "vivaldi", "terminal", "calc")):
            target = clean[6:].strip()
            target_hwnd = active_origin.hwnd if active_origin else None
            task = self.task_manager.create_task(request_text=clean, source="user_interaction")
            self.task_manager.transition_status(task.id, TaskStatus.RUNNING)
            cap_res = self._execute_through_broker(
                "focus_ui_element",
                {"target": target, "hwnd": target_hwnd},
                task_id=task.id,
            )
            if cap_res.success:
                self._complete_task(task, cap_res)
                return ExecutionResult(type="capability_result", success=True, message=cap_res.message, task=task, capability_result=cap_res)
            else:
                self._fail_task(task, cap_res.message, capability="focus_ui_element")
                return ExecutionResult(type="error", success=False, message=cap_res.message, task=task, capability_result=cap_res)

        if not has_compound and (lower_q.startswith("select tab ") or (lower_q.startswith("select ") and "tab" in lower_q)):
            target = clean[11:].strip() if lower_q.startswith("select tab ") else clean[7:].replace("tab", "").strip()
            target_hwnd = active_origin.hwnd if active_origin else None
            task = self.task_manager.create_task(request_text=clean, source="user_interaction")
            self.task_manager.transition_status(task.id, TaskStatus.RUNNING)
            cap_res = self._execute_through_broker(
                "select_ui_element",
                {"target": target, "hwnd": target_hwnd},
                task_id=task.id,
            )
            if cap_res.success:
                self._complete_task(task, cap_res)
                return ExecutionResult(type="capability_result", success=True, message=cap_res.message, task=task, capability_result=cap_res)
            else:
                self._fail_task(task, cap_res.message, capability="select_ui_element")
                return ExecutionResult(type="error", success=False, message=cap_res.message, task=task, capability_result=cap_res)



        # -------------------------------------------------------------
        # 2. FAST PATH: Instant Deterministic Routing (< 3ms)
        # -------------------------------------------------------------
        # Check if the query is a simple prefix or single-word app launch (rejecting compound requests)
        words = clean.split()
        has_compound = any(c in f" {clean.lower()} " for c in (" and ", " then ", " with ", " & ", ";", ", then ", ", and "))
        is_simple_verb = not has_compound and words[0].lower() in ("open", "launch", "start", "show", "go", "run") and len(words) <= 3
        is_single_term = not has_compound and len(words) == 1 and not re.search(r"[:#\d]", clean)

        if is_simple_verb or is_single_term:
            decision = self.deterministic_router.route(clean, self.routing_context)
            if decision.is_resolved and decision.tool != "unknown":
                logger.info("Fast path triggered: '%s' -> %s", clean, decision.tool)
                task = self.task_manager.create_task(request_text=clean, source="user_fast_path")
                self.task_manager.transition_status(task.id, TaskStatus.RUNNING)

                # Dispatch tool (map 'open_app' to 'open_application')
                tool_name = "open_application" if decision.tool == "open_app" else decision.tool
                if dry_run:
                    if tool_name == "open_application":
                        cap_res = CapabilityResult.ok(
                            capability="open_application",
                            message=f"Application '{decision.args.get('app', '')}' launched successfully (dry run).",
                            data=decision.args,
                        )
                    else:
                        cap_res = CapabilityResult.ok(
                            capability=tool_name,
                            message=f"Simulated execution of '{tool_name}' (dry run).",
                            data={"dry_run": True, **decision.args},
                        )
                else:
                    from astrarun.security.execution_broker import ActionCategory, ActionProposal
                    proposal = ActionProposal(
                        category=ActionCategory.ACT,
                        capability_id=tool_name,
                        parameters=decision.args,
                        task_id=task.id,
                        source="fast_path",
                    )
                    broker_res = self.execution_broker.execute(proposal)
                    if broker_res.requires_confirmation:
                        self.task_manager.transition_status(task.id, TaskStatus.WAITING_CONFIRMATION)
                        return ExecutionResult(
                            type="confirm",
                            success=False,
                            message=broker_res.message,
                            task=task,
                            prompt=broker_res.message,
                        )
                    if broker_res.blocked:
                        self._fail_task(task, broker_res.message, capability=tool_name)
                        return ExecutionResult(
                            type="error",
                            success=False,
                            message=broker_res.message,
                            task=task,
                        )
                    cap_res = CapabilityResult(
                        capability=tool_name,
                        success=broker_res.success,
                        message=broker_res.message,
                        data=broker_res.data,
                    )

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
        # 2.5 MACHINE MODEL FAST PATH: Authoritative Workstation Facts (< 3ms)
        # -------------------------------------------------------------
        if self.machine_query_engine.is_machine_query(clean):
            mq_answer = self.machine_query_engine.answer_query(clean)
            if mq_answer.get("answer"):
                logger.info("Machine query path triggered: '%s' -> %s", clean, mq_answer.get("matched_topic"))
                task = self.task_manager.create_task(request_text=clean, source="user_machine_query")
                self.task_manager.transition_status(task.id, TaskStatus.RUNNING)
                cap_res = CapabilityResult.ok(
                    capability="machine_query",
                    message=mq_answer["answer"],
                    data=mq_answer,
                )
                self._complete_task(task, cap_res)
                return ExecutionResult(
                    type="machine_query",
                    success=True,
                    message=mq_answer["answer"],
                    task=task,
                    capability_result=cap_res,
                )

        # -------------------------------------------------------------
        # 3. RICH PATH: Neural NLP Sandwich, Task Creation, Safety Gating
        # -------------------------------------------------------------
        task = self.task_manager.create_task(request_text=clean, source="user_launcher")
        self.task_manager.transition_status(task.id, TaskStatus.PARSING)

        try:
            # Stage 1: Laya A Semantic Pre-Gate
            pre_gate = self.laya_sandwich.evaluate_pre_gate(clean)

            # Stage 2: Neural NLP Structure Engine (spaCy + byte-exact spans)
            parsed_req = self.neural_structure_engine.parse(clean)

            # Stage 3: Laya B Semantic Verifier
            verifier = self.laya_sandwich.evaluate_verifier(clean, parsed_req)

            # Stage 4: Decision Fusion
            fused_plan = self.decision_fusion.fuse(
                query=clean,
                fast_path_decision=None,
                pre_gate=pre_gate,
                parsed_request=parsed_req,
                verifier=verifier,
            )

            # Handle verifier rejection
            if fused_plan.action_type == "rejected":
                reason = fused_plan.rejection_reason or "Plan failed semantic safety verification."
                self.task_manager.block_task(task.id, reason=reason)
                return ExecutionResult(
                    type="blocked",
                    success=False,
                    message=f"Action rejected by verifier: {reason}",
                    task=task,
                )

            # Handle clarification prompt
            if fused_plan.action_type == "clarify":
                self.task_manager.transition_status(task.id, TaskStatus.WAITING_CLARIFICATION)
                return ExecutionResult(
                    type="clarify",
                    success=False,
                    message=fused_plan.clarification_prompt or "Clarification required.",
                    task=task,
                    prompt=fused_plan.clarification_prompt or "Which action did you mean?",
                )

            # Parse query into StructuredUtterance IR (from Neural NLP or NLPEngine fallback)
            snapshot = self.context_engine.get_snapshot()
            if parsed_req.clauses and not parsed_req.has_negation:
                utterance: StructuredUtterance = parsed_req.to_structured_utterance()
            else:
                utterance = self.nlp_engine.parse(
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

            wf_context = WorkflowContext(origin_window=active_origin)
            step_results = []
            all_ok = True
            last_msg = ""
            failed_step = None

            if len(proposal.steps) == 1:
                step = proposal.steps[0]
                wf_context.bind_step_arguments(step)
                if dry_run:
                    if step.tool == "open_application":
                        cap_res = CapabilityResult.ok(
                            capability="open_application",
                            message=f"Application '{step.arguments.get('app', '')}' launched successfully (dry run).",
                            data=step.arguments,
                        )
                    elif step.tool == "focus_application":
                        app_name = step.arguments.get("app", "app")
                        cap_res = CapabilityResult.ok(
                            capability="focus_application",
                            message=f"Focused application '{app_name}' (dry run).",
                            data={"hwnd": 1001, "title": f"{app_name.title()} Window", "pid": 1000},
                            context_updates=[{"type": "application_focused", "app": app_name, "hwnd": 1001}],
                        )
                    elif step.tool == "wait_for_window":
                        cap_res = CapabilityResult.ok(
                            capability="wait_for_window",
                            message=f"Target window for '{step.arguments.get('app', '')}' is ready (dry run).",
                            data={"hwnd": 1001, "title": f"{step.arguments.get('app', 'App').title()} Window", "pid": 1000},
                            context_updates=[{"type": "window_ready", "hwnd": 1001}],
                        )
                    elif step.tool == "resolve_editable_element":
                        cap_res = CapabilityResult.ok(
                            capability="resolve_editable_element",
                            message="Resolved editable element in window (dry run).",
                            data={"element": {"name": "Text Editor", "control_type": "Document", "class_name": "Edit"}, "hwnd": step.arguments.get("hwnd", 1001)},
                            context_updates=[{"type": "element_resolved", "hwnd": step.arguments.get("hwnd", 1001)}],
                        )
                    elif step.tool == "type_text":
                        t_len = len(step.arguments.get("text", ""))
                        cap_res = CapabilityResult.ok(
                            capability="type_text",
                            message=f"Entered {t_len} characters.",
                            data={"characters_typed": t_len},
                        )
                    else:
                        cap_res = CapabilityResult.ok(
                            capability=step.tool,
                            message=f"Simulated execution of '{step.tool}' (dry run).",
                            data={"dry_run": True, **step.arguments},
                        )
                else:
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
                failed_step = None

                for step in proposal.steps:
                    # Bind target HWND, window, and editable element from preceding steps
                    wf_context.bind_step_arguments(step)

                    # Simulated dry run support for headless verification
                    if dry_run:
                        if step.tool == "open_application":
                            s_res = CapabilityResult.ok(
                                capability="open_application",
                                message=f"Application '{step.arguments.get('app', '')}' launched successfully (dry run).",
                                data=step.arguments,
                            )
                        elif step.tool == "wait_for_window":
                            s_res = CapabilityResult.ok(
                                capability="wait_for_window",
                                message=f"Target window for '{step.arguments.get('app', '')}' is ready (dry run).",
                                data={"hwnd": 1001, "title": f"{step.arguments.get('app', 'App').title()} Window", "pid": 1000},
                                context_updates=[{"type": "window_ready", "hwnd": 1001}],
                            )
                        elif step.tool == "resolve_editable_element":
                            s_res = CapabilityResult.ok(
                                capability="resolve_editable_element",
                                message="Resolved editable element in window (dry run).",
                                data={"element": {"name": "Text Editor", "control_type": "Document", "class_name": "Edit"}, "hwnd": step.arguments.get("hwnd", 1001)},
                                context_updates=[{"type": "element_resolved", "hwnd": step.arguments.get("hwnd", 1001)}],
                            )
                        elif step.tool == "type_text":
                            t_len = len(step.arguments.get("text", ""))
                            s_res = CapabilityResult.ok(
                                capability="type_text",
                                message=f"Entered {t_len} characters.",
                                data={"characters_typed": t_len},
                            )
                        elif step.tool == "focus_application":
                            app_name = step.arguments.get("app", "app")
                            s_res = CapabilityResult.ok(
                                capability="focus_application",
                                message=f"Focused application '{app_name}' (dry run).",
                                data={"hwnd": 1001, "title": f"{app_name.title()} Window", "pid": 1000},
                                context_updates=[{"type": "application_focused", "app": app_name, "hwnd": 1001}],
                            )
                        else:
                            s_res = CapabilityResult.ok(
                                capability=step.tool,
                                message=f"Simulated execution of '{step.tool}' (dry run).",
                                data={"dry_run": True, **step.arguments},
                            )
                    else:
                        s_res = self.task_manager.execute_capability(
                            task_id=task.id,
                            capability_id=step.tool,
                            arguments=step.arguments,
                            registry=self.capability_registry,
                        )

                    step_results.append(s_res)
                    wf_context.record_step_result(step, s_res)
                    last_msg = s_res.message
                    if not s_res.success:
                        all_ok = False
                        failed_step = step
                        break

                if all_ok:
                    cap_res = CapabilityResult(
                        success=True,
                        capability="workflow",
                        message=f"Workflow executed {len(step_results)} step(s): {last_msg}",
                        data={"steps": [s.to_dict() for s in step_results]},
                    )
                else:
                    num_succeeded = sum(1 for s in step_results if s.success)
                    fail_tool = failed_step.tool if failed_step else "unknown"
                    if num_succeeded > 0:
                        self.task_manager.transition_status(task.id, TaskStatus.PARTIALLY_COMPLETED)
                        err_msg = f"Workflow partially completed ({num_succeeded}/{len(proposal.steps)} steps succeeded): {last_msg}"
                    else:
                        self._fail_task(task, last_msg, capability=fail_tool)
                        err_msg = last_msg

                    cap_res = CapabilityResult(
                        success=False,
                        capability=fail_tool,
                        message=err_msg,
                        data={"steps": [s.to_dict() for s in step_results]},
                        error_code=s_res.error_code if s_res else CapabilityErrorCode.EXECUTION_FAILED,
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
                if len(proposal.steps) == 1:
                    self._fail_task(task, cap_res.message, capability=cap_res.capability)
                return ExecutionResult(
                    type="error",
                    success=False,
                    message=cap_res.message,
                    task=task,
                    capability_result=cap_res,
                    data=cap_res.data,
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
            if hasattr(self, "laya_router") and self.laya_router:
                if hasattr(self.laya_router, "shutdown"):
                    self.laya_router.shutdown()
            if hasattr(self, "browser_service") and self.browser_service:
                try:
                    self.browser_service.close()
                except Exception:
                    pass
            if hasattr(self, "single_instance") and self.single_instance:
                self.single_instance.release()
            from astrarun.core.crash import record_clean_shutdown
            record_clean_shutdown(reason="app_shutdown")
            logger.info("AstraApplication shutdown complete.")
        except Exception as err:
            logger.error("Error during AstraApplication shutdown: %s", err)
