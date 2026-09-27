"""Deterministic Entity Resolution Engine for AstraRun v0.6.

Resolves abstract user queries and predicted semantic intents into concrete,
deterministic workstation targets (projects, files, applications, folders, ports,
and processes).

Enforces strict safety boundaries, contextual references, and disambiguation logic:
- If ambiguous matches exist, returns status='ambiguous' with candidates list.
- If a target violates workstation safety policy, returns status='blocked'.
- Differentiates read-only inspection (allowed on port 80) from process termination.
- Integrates with ProjectRegistry and WorkstationContextEngine.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.discovery.apps import AppDiscoveryCache
from astrarun.discovery.folders import FolderResolver
from astrarun.projects.registry import ProjectMetadata, ProjectRegistry

logger = get_logger("astrarun.routing.entity_resolver")

# System processes strictly forbidden from being manipulated or terminated
PROTECTED_PROCESSES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe",
    "explorer.exe", "dwm.exe", "spoolsv.exe", "fontdrvhost.exe"
}

# System port range restricted from automated modification/termination
PROTECTED_PORT_MAX = 1023

# Dangerous shell/system commands forbidden by hard policy
BLOCKED_PATTERNS = [
    re.compile(r"\brmdir\s+/[sq]\b", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
    re.compile(r"\bdel\s+(?:/f\s+|/s\s+|/q\s+)*[a-z]:\\(?:windows|system32)", re.IGNORECASE),
    re.compile(r"\breg\s+delete\s+hklm", re.IGNORECASE),
    re.compile(r"\bdrop\s+database\b", re.IGNORECASE),
    re.compile(r"\bdiskpart\b", re.IGNORECASE),
    re.compile(r"\bwipe\s+disk\b", re.IGNORECASE),
    re.compile(r"(?:\$\{[^}]+\}|%[A-Z0-9_]+%)", re.IGNORECASE),  # Environment variable expansion
    re.compile(r"\.\.[/\\]"),  # Directory traversal
    re.compile(r"https?://[^\s]+\.(?:exe|bat|cmd|msi|ps1|vbs)\b", re.IGNORECASE),  # Malicious download
    re.compile(r"[;&|]\s*(?:format|del|rmdir|powershell|cmd|whoami|rm\s+-rf)", re.IGNORECASE),  # Shell injection
    re.compile(r"[`$]\("),  # Command substitution
]


@dataclass
class ProposedAction:
    """Descriptor of a proposed action produced by the Entity Resolution Engine."""
    action_type: str
    raw_query: str
    target: str | None = None
    entity_id: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    status: str = "unresolved"  # "resolved" | "ambiguous" | "unresolved" | "blocked"
    candidate_matches: list[dict[str, Any]] = field(default_factory=list)
    requires_confirmation: bool = False
    policy_allowed: bool = True
    block_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def is_executable(self) -> bool:
        """Indicates if the action is fully resolved and cleared by safety policy."""
        return self.status == "resolved" and self.policy_allowed and self.target is not None


class EntityResolutionEngine:
    """
    Deterministic resolution engine mapping intents and query text to workstation entities.
    """

    def __init__(
        self,
        workspace_json_path: Path | str = r"E:\Workspace\workspace.json",
        app_cache: Optional[AppDiscoveryCache] = None,
        folder_cache: Optional[FolderResolver] = None,
        project_registry: Optional[ProjectRegistry] = None,
        context_engine: Optional[Any] = None,
    ) -> None:
        self.workspace_json_path = Path(workspace_json_path)
        self.app_cache = app_cache or AppDiscoveryCache()
        self.folder_cache = folder_cache or FolderResolver()
        self.project_registry = project_registry or ProjectRegistry(workspace_json_path=self.workspace_json_path)
        self.context_engine = context_engine
        self._projects_cache: list[dict[str, Any]] = []
        self._load_projects()

    def _load_projects(self) -> None:
        """Load workspace projects catalog from workspace.json for cache compatibility."""
        if self.workspace_json_path.exists():
            try:
                with open(self.workspace_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._projects_cache = data.get("projects", [])
                    logger.debug("Loaded %d projects from workspace.json", len(self._projects_cache))
            except Exception as err:
                logger.warning("Failed to load workspace.json: %s", err)
                self._projects_cache = []

    def check_hard_policy(self, query: str) -> Tuple[bool, Optional[str]]:
        """Verify query against hard security and safety invariants."""
        clean = query.strip()
        for pat in BLOCKED_PATTERNS:
            if pat.search(clean):
                return False, f"Matched dangerous command pattern: {pat.pattern}"
        if "system32" in clean.lower() and any(w in clean.lower() for w in ("del", "delete", "rm", "remove", "wipe", "format")):
            return False, "Prohibited operation on System32 directory"
        if any(w in clean.lower() for w in ("kill system", "terminate system", "kill lsass", "terminate lsass", "stop csrss", "terminate svchost", "terminate wininit", "kill registry")):
            return False, "Target is a protected Windows system process"
        port_m = re.search(r"\b(?:kill|terminate|stop|end)\s+(?:whatever\s+is\s+using\s+|process\s+on\s+)?port\s+(\d+)\b", clean, re.IGNORECASE)
        if port_m and int(port_m.group(1)) <= PROTECTED_PORT_MAX:
            return False, f"Port {port_m.group(1)} is a protected system port (<= {PROTECTED_PORT_MAX})"
        return True, None

    def resolve(self, intent: str, query: str, context: Optional[dict[str, Any]] = None) -> ProposedAction:
        """
        Deterministically resolve query for a given intent.
        
        Returns ProposedAction with resolution status, candidates, tool selection, and policy clearance.
        """
        t0 = time.perf_counter()
        clean_query = query.strip()

        # Step 0: Global Hard Policy Pre-Check
        allowed, reason = self.check_hard_policy(clean_query)
        if not allowed:
            lat = (time.perf_counter() - t0) * 1000.0
            return ProposedAction(
                action_type=intent,
                raw_query=clean_query,
                target=None,
                confidence=0.0,
                status="blocked",
                policy_allowed=False,
                block_reason=reason,
                latency_ms=lat,
            )

        if intent in ("open_project", "semantic_project"):
            act = self._resolve_project(clean_query, context)
        elif intent in ("open_app", "semantic_app"):
            act = self._resolve_app(clean_query)
        elif intent in ("open_folder", "semantic_folder"):
            act = self._resolve_folder(clean_query)
        elif intent in ("open_url", "semantic_browser"):
            act = self._resolve_url(clean_query)
        elif intent in ("process_action", "semantic_process", "inspect_port", "inspect_process"):
            act = self._resolve_process(clean_query, context)
        elif intent in ("system_action", "semantic_system"):
            act = self._resolve_system(clean_query)
        else:
            act = ProposedAction(
                action_type=intent,
                raw_query=clean_query,
                status="unresolved",
                confidence=0.0,
            )

        act.latency_ms = (time.perf_counter() - t0) * 1000.0
        return act

    def _resolve_project(self, query: str, context: Optional[dict[str, Any]] = None) -> ProposedAction:
        """Resolve project entity from workspace catalog or structured context."""
        clean_lower = query.lower()

        # Determine requested tool variant: VS Code vs Folder vs Default
        wants_vscode = any(w in clean_lower for w in ("in vscode", "in vs code", "in code", "vscode", "vs code"))
        wants_folder = any(w in clean_lower for w in ("folder", "in explorer", "directory", "files"))
        
        if wants_vscode:
            preferred_tool = "open_project_in_vscode"
        elif wants_folder:
            preferred_tool = "open_project_folder"
        else:
            preferred_tool = "open_project"

        # 1. Check Contextual Entity Resolution (e.g. "my most recent project", "last project")
        ctx_engine = self.context_engine
        if not ctx_engine and context and "context_engine" in context:
            ctx_engine = context["context_engine"]

        if ctx_engine:
            ref = ctx_engine.resolve_contextual_entity(query, expected_type="project")
            if ref and ref.entity_id.startswith("project:"):
                pid = ref.entity_id.replace("project:", "")
                p_meta = self.project_registry.get_project(pid)
                if p_meta:
                    return ProposedAction(
                        action_type="open_project",
                        raw_query=query,
                        target=p_meta.relative_path,
                        entity_id=ref.entity_id,
                        tool=preferred_tool,
                        arguments={"project_id": pid},
                        confidence=1.0,
                        status="resolved",
                        candidate_matches=[{"id": pid, "name": p_meta.name, "path": p_meta.relative_path, "score": 1.0}],
                        metadata={"project_id": pid, "project_name": p_meta.name, "contextual": True},
                    )

        # 2. Extract Project Terms
        clean_terms = query.strip()
        clean_terms = re.sub(r"^(?:open\s+(?:the\s+)?folder\s+for\s+(?:my\s+)?|folder\s+for\s+(?:my\s+)?|vscode\s+for\s+|launch\s+vscode\s+)", "", clean_terms, flags=re.IGNORECASE)
        clean_terms = re.sub(r"^(?:open|launch|start|explore|browse|cd|work on|continue working on|switch to|reopen)\s+(?:my|the)?\s*", "", clean_terms, flags=re.IGNORECASE)
        clean_terms = re.sub(r"^(?:project|workspace)\s+", "", clean_terms, flags=re.IGNORECASE)
        clean_terms = re.sub(r"\s+(?:in\s+vscode|in\s+vs\s+code|in\s+code|in\s+explorer)$", "", clean_terms, flags=re.IGNORECASE)
        clean_terms = re.sub(r"\s+(?:project\s+folder|folder|directory|workspace|project)$", "", clean_terms, flags=re.IGNORECASE)
        terms = clean_terms.strip().lower()

        # Check for generic ambiguous terms
        if terms in ("", "project", "workspace", "my project", "the project", "dev", "test", "dev project", "test project"):
            all_cands = [{"id": p.id, "name": p.name, "path": p.relative_path, "score": 0.50} for p in self.project_registry.list_projects()[:5]]
            return ProposedAction(
                action_type="open_project",
                raw_query=query,
                target=None,
                confidence=0.50,
                status="ambiguous",
                candidate_matches=all_cands,
                metadata={"disambiguation_required": True},
            )

        # Check project registry search
        reg_results = self.project_registry.find_project(terms)
        candidates = []
        for p_meta, score in reg_results:
            candidates.append({
                "id": p_meta.id,
                "name": p_meta.name,
                "path": p_meta.relative_path,
                "score": score,
            })

        # Also check local _projects_cache for compatibility
        for p in self._projects_cache:
            p_id = p.get("id", "").lower()
            p_name = p.get("name", "").lower()
            p_path = p.get("path", "")
            tags = [t.lower() for t in p.get("tags", [])]

            score = 0.0
            if terms == p_id or terms == p_name:
                score = 1.0
            elif terms in p_id or terms in p_name:
                score = 0.85
            elif any(terms == t for t in tags):
                score = 0.75
            elif any(terms in t for t in tags):
                score = 0.60
            elif terms in p_path.lower():
                score = 0.70

            if score >= 0.60 and not any(c["id"] == p.get("id") for c in candidates):
                candidates.append({
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "path": p.get("path"),
                    "score": score,
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)

        if not candidates:
            return ProposedAction(
                action_type="open_project",
                raw_query=query,
                status="unresolved",
                confidence=0.0,
            )

        # Disambiguation check (scores within 0.15)
        if len(candidates) > 1 and (candidates[0]["score"] - candidates[1]["score"] < 0.15):
            return ProposedAction(
                action_type="open_project",
                raw_query=query,
                target=None,
                confidence=candidates[0]["score"],
                status="ambiguous",
                candidate_matches=candidates[:5],
                metadata={"disambiguation_required": True},
            )

        best = candidates[0]
        return ProposedAction(
            action_type="open_project",
            raw_query=query,
            target=best["path"],
            entity_id=f"project:{best['id']}",
            tool=preferred_tool,
            arguments={"project_id": best["id"]},
            confidence=best["score"],
            status="resolved",
            candidate_matches=[best],
            metadata={"project_id": best["id"], "project_name": best["name"]},
        )

    def _resolve_app(self, query: str) -> ProposedAction:
        """Resolve installed desktop application."""
        clean = query.strip()
        clean = re.sub(r"^(?:open|launch|start|run|app)\s+", "", clean, flags=re.IGNORECASE).strip().lower()
        terms = clean

        # Known application aliases
        alias_expansions = {
            "notepad": "notepad",
            "calculator": "calc",
            "calc": "calc",
            "vs code": "code",
            "vscode": "code",
            "code": "code",
            "command prompt": "cmd",
            "cmd": "cmd",
            "file explorer": "explorer",
            "explorer": "explorer",
            "terminal": "wt",
            "windows terminal": "wt",
            "powershell": "powershell",
            "pwsh": "pwsh",
            "vivaldi": "vivaldi",
        }
        if terms in alias_expansions:
            resolved_key = alias_expansions[terms]
            app_obj = self.app_cache.get(resolved_key)
            if app_obj:
                return ProposedAction(
                    action_type="open_app",
                    raw_query=query,
                    target=str(app_obj.path),
                    entity_id=f"app:{resolved_key}",
                    tool="open_app",
                    arguments={"app": resolved_key, "path": str(app_obj.path)},
                    confidence=1.0,
                    status="resolved",
                    candidate_matches=[{"alias": resolved_key, "name": app_obj.name, "path": str(app_obj.path), "score": 1.0}],
                    metadata={"app_name": app_obj.name},
                )

        apps = self.app_cache.apps
        candidates = []

        for alias, app in apps.items():
            a_alias = alias.lower()
            a_name = app.name.lower()
            score = 0.0

            if terms == a_alias or terms == a_name:
                score = 1.0
            elif terms in a_name or terms in a_alias:
                score = 0.80

            if score >= 0.70:
                candidates.append({
                    "alias": alias,
                    "name": app.name,
                    "path": str(app.path),
                    "score": score,
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)

        if not candidates:
            return ProposedAction(
                action_type="open_app",
                raw_query=query,
                status="unresolved",
                confidence=0.0,
            )

        if len(candidates) > 1 and (candidates[0]["score"] - candidates[1]["score"] < 0.10):
            return ProposedAction(
                action_type="open_app",
                raw_query=query,
                target=None,
                confidence=candidates[0]["score"],
                status="ambiguous",
                candidate_matches=candidates[:5],
            )

        best = candidates[0]
        return ProposedAction(
            action_type="open_app",
            raw_query=query,
            target=best["path"],
            entity_id=f"app:{best['alias']}",
            tool="open_app",
            arguments={"app": best["alias"], "path": best["path"]},
            confidence=best["score"],
            status="resolved",
            candidate_matches=[best],
            metadata={"app_name": best["name"]},
        )

    def _resolve_folder(self, query: str) -> ProposedAction:
        """Resolve local folder in File Explorer."""
        clean = query.strip()
        clean = re.sub(r"^(?:open|browse|explore|show|folder|dir)\s+", "", clean, flags=re.IGNORECASE).strip().lower()
        clean = re.sub(r"\s+(?:folder|directory|dir)$", "", clean, flags=re.IGNORECASE).strip()
        terms = clean

        folders = self.folder_cache.folders
        candidates = []

        for alias, f_info in folders.items():
            f_alias = alias.lower()
            score = 0.0
            if terms == f_alias or terms in f_alias:
                score = 1.0 if terms == f_alias else 0.80
                candidates.append({
                    "alias": alias,
                    "path": str(f_info.path),
                    "score": score,
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)

        if not candidates:
            return ProposedAction(
                action_type="open_folder",
                raw_query=query,
                status="unresolved",
                confidence=0.0,
            )

        best = candidates[0]
        return ProposedAction(
            action_type="open_folder",
            raw_query=query,
            target=best["path"],
            entity_id=f"folder:{best['alias']}",
            tool="open_folder",
            arguments={"folder": best["alias"]},
            confidence=best["score"],
            status="resolved",
            candidate_matches=[best],
        )

    def _resolve_url(self, query: str) -> ProposedAction:
        """Resolve website URL navigation."""
        terms = re.sub(r"^(?:open|navigate to|browse|go to|url)\s+", "", query, flags=re.IGNORECASE).strip()

        url_aliases = {
            "github": "https://github.com",
            "youtube": "https://youtube.com",
            "google": "https://google.com",
            "reddit": "https://reddit.com",
        }
        if terms.lower() in url_aliases:
            target = url_aliases[terms.lower()]
            return ProposedAction(
                action_type="open_url",
                raw_query=query,
                target=target,
                entity_id=f"url:{target}",
                tool="open_url",
                arguments={"url": target},
                confidence=1.0,
                status="resolved",
            )

        url_match = re.search(r"https?://[^\s]+", terms)
        if url_match:
            target = url_match.group(0)
            return ProposedAction(
                action_type="open_url",
                raw_query=query,
                target=target,
                entity_id=f"url:{target}",
                tool="open_url",
                arguments={"url": target},
                confidence=1.0,
                status="resolved",
            )

        domain_match = re.search(r"\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)", terms)
        if domain_match:
            domain = domain_match.group(1)
            target = f"https://{domain}"
            return ProposedAction(
                action_type="open_url",
                raw_query=query,
                target=target,
                entity_id=f"url:{target}",
                tool="open_url",
                arguments={"url": target},
                confidence=0.90,
                status="resolved",
            )

        return ProposedAction(
            action_type="open_url",
            raw_query=query,
            status="unresolved",
            confidence=0.0,
        )

    def _resolve_process(self, query: str, context: Optional[dict[str, Any]] = None) -> ProposedAction:
        """
        Resolve process and port management actions.
        Differentiates read-only inspection (ALLOWED on all ports) from process termination.
        """
        clean_lower = query.lower()

        # Distinguish read-only inspection from modification/termination
        is_inspection = any(w in clean_lower for w in (
            "inspect", "what is", "who is", "show", "check", "view", "what's", "status", "details"
        )) and not any(w in clean_lower for w in ("kill", "stop", "terminate", "end"))

        # 1. Port match: e.g. "port 3000", "kill port 8080", "inspect port 80"
        port_match = re.search(r"(?:port\s*[:=]?\s*|:\s*)(\d{1,5})\b", query, re.IGNORECASE)
        if port_match:
            port = int(port_match.group(1))

            # READ-ONLY PORT INSPECTION: Allowed on all ports (including port 80)
            if is_inspection:
                return ProposedAction(
                    action_type="inspect_port",
                    raw_query=query,
                    target=f"port:{port}",
                    entity_id=f"port:{port}",
                    tool="inspect_port",
                    arguments={"port": port},
                    confidence=0.95,
                    status="resolved",
                    requires_confirmation=False,
                    policy_allowed=True,
                    metadata={"port": port, "read_only": True},
                )

            # TERMINATION / DESTRUCTIVE ACTION ON PORT
            if port <= PROTECTED_PORT_MAX:
                return ProposedAction(
                    action_type="process_action",
                    raw_query=query,
                    target=str(port),
                    entity_id=f"port:{port}",
                    confidence=1.0,
                    status="blocked",
                    policy_allowed=False,
                    block_reason=f"Port {port} is a protected system port (<= {PROTECTED_PORT_MAX})",
                )

            return ProposedAction(
                action_type="process_action",
                raw_query=query,
                target=f"port:{port}",
                entity_id=f"port:{port}",
                tool="terminate_process",
                arguments={"port": port},
                confidence=0.95,
                status="resolved",
                requires_confirmation=True,
                policy_allowed=True,
                metadata={"port": port, "action": "kill_port"},
            )

        # 2. Check Contextual Pronoun Resolution (e.g. "stop that process", "kill it")
        ctx_engine = self.context_engine
        if not ctx_engine and context and "context_engine" in context:
            ctx_engine = context["context_engine"]

        if ctx_engine:
            ref = ctx_engine.resolve_contextual_entity(query, expected_type="process")
            if ref and ref.entity_id.startswith("process:"):
                pid_str = ref.entity_id.replace("process:", "")
                try:
                    pid_val = int(pid_str)
                    return ProposedAction(
                        action_type="process_action",
                        raw_query=query,
                        target=f"process:{pid_val}",
                        entity_id=ref.entity_id,
                        tool="terminate_process",
                        arguments={
                            "pid": pid_val,
                            "expected_create_time": ref.metadata.get("create_time", 0.0),
                            "expected_name": ref.metadata.get("process_name", ""),
                        },
                        confidence=1.0,
                        status="resolved",
                        requires_confirmation=True,
                        policy_allowed=True,
                        metadata={"pid": pid_val, "contextual": True},
                    )
                except ValueError:
                    pass

        # 3. Process by Name or PID: e.g. "kill node", "inspect python", "kill 14236"
        proc_match = re.search(
            r"(?:kill|terminate|stop|restart|inspect|show|check|view\s+metadata\s+for|process\s+details\s+for|process\s+details)\s+(?:process\s+)?([a-zA-Z0-9_\-\.]+)",
            query,
            re.IGNORECASE,
        )
        if proc_match:
            proc_target = proc_match.group(1).lower()

            # Check if target is a numeric PID
            if proc_target.isdigit():
                pid_val = int(proc_target)
                if is_inspection:
                    return ProposedAction(
                        action_type="inspect_process",
                        raw_query=query,
                        target=f"process:{pid_val}",
                        entity_id=f"process:{pid_val}",
                        tool="inspect_process",
                        arguments={"pid": pid_val},
                        confidence=0.95,
                        status="resolved",
                        requires_confirmation=False,
                        policy_allowed=True,
                    )
                else:
                    return ProposedAction(
                        action_type="process_action",
                        raw_query=query,
                        target=f"process:{pid_val}",
                        entity_id=f"process:{pid_val}",
                        tool="terminate_process",
                        arguments={"pid": pid_val},
                        confidence=0.90,
                        status="resolved",
                        requires_confirmation=True,
                        policy_allowed=True,
                    )

            # Target is a process name (e.g. 'lsass', 'node', 'python')
            if proc_target in PROTECTED_PROCESSES or f"{proc_target}.exe" in PROTECTED_PROCESSES:
                if is_inspection:
                    return ProposedAction(
                        action_type="inspect_process",
                        raw_query=query,
                        target=f"process:{proc_target}",
                        entity_id=f"process:{proc_target}",
                        tool="inspect_process",
                        arguments={"name": proc_target},
                        confidence=0.90,
                        status="resolved",
                        requires_confirmation=False,
                        policy_allowed=True,
                        metadata={"protected": True, "read_only": True},
                    )
                else:
                    return ProposedAction(
                        action_type="process_action",
                        raw_query=query,
                        target=proc_target,
                        confidence=1.0,
                        status="blocked",
                        policy_allowed=False,
                        block_reason=f"Process '{proc_target}' is a protected Windows system process",
                    )

            if is_inspection:
                return ProposedAction(
                    action_type="inspect_process",
                    raw_query=query,
                    target=f"process:{proc_target}",
                    entity_id=f"process:{proc_target}",
                    tool="inspect_process",
                    arguments={"name": proc_target},
                    confidence=0.85,
                    status="resolved",
                    requires_confirmation=False,
                    policy_allowed=True,
                )
            else:
                # Generic process name termination without PID -> AMBIGUOUS / CLARIFY (Section 24)
                return ProposedAction(
                    action_type="process_action",
                    raw_query=query,
                    target=None,
                    confidence=0.75,
                    status="ambiguous",
                    requires_confirmation=True,
                    candidate_matches=[{"name": proc_target, "action": "terminate_process"}],
                    metadata={"disambiguation_required": True, "process_name": proc_target},
                )

        return ProposedAction(
            action_type="process_action",
            raw_query=query,
            status="unresolved",
            confidence=0.0,
        )

    def _resolve_system(self, query: str) -> ProposedAction:
        """Resolve system actions (power, volume, locking)."""
        lower = query.lower()
        if any(w in lower for w in ("shutdown", "turn off", "power off")):
            return ProposedAction(
                action_type="system_action",
                raw_query=query,
                target="system:shutdown",
                entity_id="system:shutdown",
                confidence=0.95,
                status="resolved",
                requires_confirmation=True,
                metadata={"action": "shutdown"},
            )
        if any(w in lower for w in ("restart", "reboot")):
            return ProposedAction(
                action_type="system_action",
                raw_query=query,
                target="system:restart",
                entity_id="system:restart",
                confidence=0.95,
                status="resolved",
                requires_confirmation=True,
                metadata={"action": "restart"},
            )
        if "lock" in lower:
            return ProposedAction(
                action_type="system_action",
                raw_query=query,
                target="system:lock",
                entity_id="system:lock",
                confidence=0.95,
                status="resolved",
                requires_confirmation=False,
                metadata={"action": "lock"},
            )

        return ProposedAction(
            action_type="system_action",
            raw_query=query,
            status="unresolved",
            confidence=0.0,
        )
