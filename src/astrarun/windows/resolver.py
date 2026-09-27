"""Window entity resolution with ambiguity gating and origin-window grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from astrarun.capabilities.models import WindowEntity
from astrarun.core.logging import get_logger
from astrarun.windows.discovery import foreground_window, list_windows
from astrarun.windows.policy import is_astrarun_window

logger = get_logger("astrarun.windows.resolver")


@dataclass
class WindowResolution:
    """Result of resolving a natural window reference."""
    status: str  # "RESOLVED", "AMBIGUOUS", "NOT_FOUND", "PROTECTED"
    window: Optional[WindowEntity] = None
    candidates: list[WindowEntity] = None
    reason: str = ""

    def __post_init__(self):
        if self.candidates is None:
            self.candidates = []

    @property
    def is_resolved(self) -> bool:
        return self.status == "RESOLVED" and self.window is not None

    @property
    def is_ambiguous(self) -> bool:
        return self.status == "AMBIGUOUS"


class WindowResolver:
    """
    Resolves natural language queries to concrete, revalidated WindowEntity instances.
    Safely handles pronouns, origin window preservation, and multi-window ambiguity.
    """

    PRONOUN_TERMS = {
        "this",
        "this window",
        "current",
        "current window",
        "active",
        "active window",
        "foreground",
        "foreground window",
        "origin",
        "it",
    }

    # Common app alias normalizations
    APP_ALIASES = {
        "vscode": ["code", "visual studio code"],
        "vs code": ["code", "visual studio code"],
        "code": ["code", "visual studio code"],
        "browser": ["vivaldi", "chrome", "msedge", "firefox", "brave"],
        "terminal": ["windowsterminal", "cmd", "powershell", "pwsh"],
        "console": ["windowsterminal", "cmd", "powershell", "pwsh"],
        "shell": ["windowsterminal", "cmd", "powershell", "pwsh"],
    }

    def resolve(
        self,
        query: str,
        origin_window: Optional[WindowEntity] = None,
        context_last_window: Optional[WindowEntity] = None,
        windows_override: Optional[list[dict | WindowEntity]] = None,
    ) -> WindowResolution:
        """
        Resolve a window reference query to a concrete WindowEntity.
        """
        clean = query.strip().lower()

        # 1. Contextual / Pronoun Reference ("this window", "current window", "it") or implicit window action
        has_pronoun = (
            clean in self.PRONOUN_TERMS
            or any(term in clean for term in ("this window", "current window", "active window", "foreground window", "this app"))
            or any(w in clean.split() for w in ("this", "current", "active", "it"))
        )

        # Check if query is an implicit window action targeting the active/origin window
        # (e.g. "snap left", "snap right", "maximize window", "snap to top left", "minimize", "restore", "close window")
        words = [w for w in clean.split() if w not in ("to", "the", "a", "an")]
        layout_action_tokens = {
            "snap", "move", "maximize", "minimize", "restore", "close", "focus",
            "tile", "window", "windows", "left", "right", "top", "bottom", "up",
            "down", "half", "corner", "here", "it", "this"
        }
        is_implicit_window_cmd = bool(words) and all(w in layout_action_tokens for w in words)

        if has_pronoun or is_implicit_window_cmd:
            if origin_window and not is_astrarun_window(origin_window.hwnd):
                logger.debug("Resolved pronoun/implicit window in '%s' to origin_window: %s", clean, origin_window.title)
                return WindowResolution(
                    status="RESOLVED",
                    window=origin_window,
                    reason=f"Resolved to origin window '{origin_window.title}'",
                )

            # Fallback to current foreground window (if not AstraRun)
            if windows_override is None:
                fg_res = foreground_window()
                if fg_res.success and fg_res.data:
                    win_dict = fg_res.data
                    hwnd = win_dict.get("hwnd", 0)
                    if not is_astrarun_window(hwnd):
                        win = WindowEntity(
                            hwnd=hwnd,
                            title=win_dict.get("title", ""),
                            pid=win_dict.get("pid", 0),
                            app_id=win_dict.get("app_id", ""),
                            bounds=win_dict.get("bounds", (0, 0, 0, 0)),
                            state=win_dict.get("state", "normal"),
                            visible=True,
                        )
                        return WindowResolution(
                            status="RESOLVED",
                            window=win,
                            reason=f"Resolved to foreground window '{win.title}'",
                        )

            if context_last_window and not is_astrarun_window(context_last_window.hwnd):
                return WindowResolution(
                    status="RESOLVED",
                    window=context_last_window,
                    reason=f"Resolved to previous context window '{context_last_window.title}'",
                )

            return WindowResolution(
                status="NOT_FOUND",
                reason="No active origin or foreground window available to resolve.",
            )

        # 2. "that window" (Anaphoric conversational reference)
        if clean in ("that", "that window") or clean.endswith(" that") or clean.endswith(" that window") or " that " in clean:
            if context_last_window and not is_astrarun_window(context_last_window.hwnd):
                return WindowResolution(
                    status="RESOLVED",
                    window=context_last_window,
                    reason=f"Resolved to context window '{context_last_window.title}'",
                )
            return WindowResolution(
                status="NOT_FOUND",
                reason="No previous window reference in active conversation.",
            )

        # 3. Direct Window Listing & Substring / App Matching
        if windows_override is not None:
            raw_windows = []
            for item in windows_override:
                if isinstance(item, WindowEntity):
                    raw_windows.append({
                        "hwnd": item.hwnd,
                        "title": item.title,
                        "pid": item.pid,
                        "app_id": item.app_id,
                        "bounds": item.bounds,
                        "state": item.state,
                        "visible": item.visible,
                    })
                elif isinstance(item, dict):
                    raw_windows.append(item)
        else:
            list_res = list_windows(limit=60)
            if not list_res.success:
                return WindowResolution(status="NOT_FOUND", reason="Could not enumerate desktop windows.")
            raw_windows = list_res.data.get("windows", [])
        candidates: list[WindowEntity] = []

        # Expand query aliases and strip action prefix verbs
        stripped_clean = re.sub(
            r"^(find|focus|open|switch\s+to|bring\s+up|locate|show|the|my|window|app)\s+",
            "",
            clean,
        ).strip()
        search_terms = [clean]
        if stripped_clean and stripped_clean != clean:
            search_terms.append(stripped_clean)

        for alias, targets in self.APP_ALIASES.items():
            if alias in clean or (stripped_clean and alias in stripped_clean):
                search_terms.extend(targets)

        STOP_WORDS = {
            "window", "app", "the", "find", "show", "focus", "switch",
            "to", "a", "an", "please", "my", "snap", "minimize",
            "maximize", "restore", "close"
        }
        words = [wd for wd in re.split(r"\s+", clean) if wd and wd not in STOP_WORDS]

        for w_dict in raw_windows:
            hwnd = w_dict.get("hwnd", 0)
            if is_astrarun_window(hwnd):
                continue

            title = w_dict.get("title", "").lower()
            app_id = w_dict.get("app_id", "").lower()

            entity = WindowEntity(
                hwnd=hwnd,
                title=w_dict.get("title", ""),
                pid=w_dict.get("pid", 0),
                app_id=w_dict.get("app_id", ""),
                bounds=w_dict.get("bounds", (0, 0, 0, 0)),
                state=w_dict.get("state", "normal"),
                visible=True,
            )

            # Check if any search term matches title or app_id
            matched = False
            for term in search_terms:
                if term in app_id or term in title:
                    matched = True
                    break

            # Multi-word compound match (e.g. "astrarun vscode")
            if words and all(w in title or w in app_id for w in words):
                matched = True

            if matched:
                candidates.append(entity)

        if not candidates:
            return WindowResolution(
                status="NOT_FOUND",
                reason=f"No open window matching '{query}' found.",
            )

        if len(candidates) == 1:
            return WindowResolution(
                status="RESOLVED",
                window=candidates[0],
                candidates=candidates,
                reason=f"Resolved uniquely to '{candidates[0].title}'",
            )

        # Multiple windows match -> Ambiguity Gating
        # Check if one candidate title has an exact match with the query
        exact_title_matches = [c for c in candidates if clean == c.title.lower()]
        if len(exact_title_matches) == 1:
            return WindowResolution(
                status="RESOLVED",
                window=exact_title_matches[0],
                candidates=candidates,
                reason=f"Resolved via exact title match to '{exact_title_matches[0].title}'",
            )

        logger.info("Ambiguous window match for '%s': found %d candidates", query, len(candidates))
        return WindowResolution(
            status="AMBIGUOUS",
            candidates=candidates,
            reason=f"Multiple windows ({len(candidates)}) match '{query}'. Disambiguation required.",
        )
