"""Deterministic Entity Resolution Engine for AstraRun v0.5.

Resolves abstract user queries and predicted semantic intents into concrete,
deterministic workstation targets (projects, files, applications, folders, ports,
and processes).

Enforces strict safety boundaries and disambiguation logic:
- If ambiguous matches exist, returns status='ambiguous' with candidates list.
- If a target violates workstation safety policy, returns status='blocked'.
- ZERO PRODUCTION EXECUTION AUTHORITY: This engine generates ProposedAction
  descriptors for inspection, UI disambiguation, and benchmarking. It never executes.
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

logger = get_logger("astrarun.routing.entity_resolver")

# System processes strictly forbidden from being manipulated or terminated
PROTECTED_PROCESSES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe",
    "explorer.exe", "dwm.exe", "spoolsv.exe", "fontdrvhost.exe"
}

# System port range restricted from automated intervention
PROTECTED_PORT_MAX = 1023

# Dangerous shell/system commands forbidden by hard policy
BLOCKED_PATTERNS = [
    re.compile(r"\brmdir\s+/[sq]\b", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
    re.compile(r"\bdel\s+(?:/f\s+|/s\s+|/q\s+)*[a-z]:\\(?:windows|system32)", re.IGNORECASE),
    re.compile(r"\breg\s+delete\s+hklm", re.IGNORECASE),
    re.compile(r"\bdrop\s+database\b", re.IGNORECASE),
    re.compile(r"\bdiskpart\b", re.IGNORECASE),
]


@dataclass
class ProposedAction:
    """Descriptor of a proposed action produced by the Entity Resolution Engine."""
    action_type: str
    raw_query: str
    target: str | None = None
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
    ) -> None:
        self.workspace_json_path = Path(workspace_json_path)
        self.app_cache = app_cache or AppDiscoveryCache()
        self.folder_cache = folder_cache or FolderResolver()
        self._projects_cache: list[dict[str, Any]] = []
        self._load_projects()

    def _load_projects(self) -> None:
        """Load workspace projects catalog (read-only) from workspace.json."""
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
        if "system32" in clean.lower() and any(w in clean.lower() for w in ("del", "delete", "rm", "remove", "wipe")):
            return False, "Prohibited operation on System32 directory"
        return True, None

    def resolve(self, intent: str, query: str, context: Optional[dict[str, Any]] = None) -> ProposedAction:
        """
        Deterministically resolve query for a given intent.
        
        Returns ProposedAction with resolution status, candidates, and policy clearance.
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

        if intent == "open_project":
            act = self._resolve_project(clean_query)
        elif intent == "open_app":
            act = self._resolve_app(clean_query)
        elif intent == "open_folder":
            act = self._resolve_folder(clean_query)
        elif intent == "open_url":
            act = self._resolve_url(clean_query)
        elif intent == "process_action":
            act = self._resolve_process(clean_query)
        elif intent == "system_action":
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

    def _resolve_project(self, query: str) -> ProposedAction:
        """Resolve project entity from workspace catalog."""
        # Strip common prefixes
        terms = re.sub(
            r"^(?:open|launch|start|cd|work on|continue working on|project)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip().lower()

        candidates = []
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

            if score >= 0.60:
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

        # Disambiguation check
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
            confidence=best["score"],
            status="resolved",
            candidate_matches=[best],
            metadata={"project_id": best["id"], "project_name": best["name"]},
        )

    def _resolve_app(self, query: str) -> ProposedAction:
        """Resolve installed desktop application."""
        terms = re.sub(
            r"^(?:open|launch|start|run|app)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip().lower()

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
                    "path": str(app.executable_path),
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
            confidence=best["score"],
            status="resolved",
            candidate_matches=[best],
            metadata={"app_name": best["name"]},
        )

    def _resolve_folder(self, query: str) -> ProposedAction:
        """Resolve local folder in File Explorer."""
        terms = re.sub(
            r"^(?:open|browse|explore|show|folder|dir)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip().lower()

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
            confidence=best["score"],
            status="resolved",
            candidate_matches=[best],
        )

    def _resolve_url(self, query: str) -> ProposedAction:
        """Resolve website URL navigation."""
        terms = re.sub(
            r"^(?:open|navigate to|browse|go to|url)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()

        # Check for explicit scheme or domain pattern
        url_match = re.search(r"https?://[^\s]+", terms)
        if url_match:
            target = url_match.group(0)
            return ProposedAction(
                action_type="open_url",
                raw_query=query,
                target=target,
                confidence=1.0,
                status="resolved",
            )

        domain_match = re.search(r"\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)", terms)
        if domain_match:
            domain = domain_match.group(1)
            return ProposedAction(
                action_type="open_url",
                raw_query=query,
                target=f"https://{domain}",
                confidence=0.90,
                status="resolved",
            )

        return ProposedAction(
            action_type="open_url",
            raw_query=query,
            status="unresolved",
            confidence=0.0,
        )

    def _resolve_process(self, query: str) -> ProposedAction:
        """Resolve process management or port termination action."""
        # 1. Port match: e.g. "port 3000", "kill port 8080", ":5000"
        port_match = re.search(r"(?:port\s*[:=]?\s*|:\s*)(\d{1,5})\b", query, re.IGNORECASE)
        if port_match:
            port = int(port_match.group(1))
            if port <= PROTECTED_PORT_MAX:
                return ProposedAction(
                    action_type="process_action",
                    raw_query=query,
                    target=str(port),
                    confidence=1.0,
                    status="blocked",
                    policy_allowed=False,
                    block_reason=f"Port {port} is a protected system port (<= {PROTECTED_PORT_MAX})",
                )
            return ProposedAction(
                action_type="process_action",
                raw_query=query,
                target=f"port:{port}",
                confidence=0.95,
                status="resolved",
                requires_confirmation=True,
                metadata={"port": port, "action": "kill_port"},
            )

        # 2. Process termination match: e.g. "kill node", "stop python"
        proc_match = re.search(
            r"(?:kill|terminate|stop|restart)\s+(?:process\s+)?([a-zA-Z0-9_\-\.]+)",
            query,
            re.IGNORECASE,
        )
        if proc_match:
            proc_name = proc_match.group(1).lower()
            if proc_name in PROTECTED_PROCESSES or f"{proc_name}.exe" in PROTECTED_PROCESSES:
                return ProposedAction(
                    action_type="process_action",
                    raw_query=query,
                    target=proc_name,
                    confidence=1.0,
                    status="blocked",
                    policy_allowed=False,
                    block_reason=f"Process '{proc_name}' is a protected Windows system process",
                )
            return ProposedAction(
                action_type="process_action",
                raw_query=query,
                target=f"process:{proc_name}",
                confidence=0.85,
                status="resolved",
                requires_confirmation=True,
                metadata={"process_name": proc_name, "action": "kill_process"},
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
