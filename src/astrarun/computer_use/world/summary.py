"""Compact WorldStateSummary adapter over DesktopObserver for AstraRun 1.0."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from astrarun.computer_use.world.desktop_state import DesktopWorldState
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.world.summary")


@dataclass
class WorldStateSummary:
    """
    Compact desktop world state summary tailored for the TurnReasoner prompt.
    
    Invariant: Does NOT dump raw screenshots or full UIA accessibility trees into prompts.
    Provides only high-level workstation context: foreground app, visible windows, active dialogs.
    """
    foreground_window: Optional[str] = None
    foreground_app: Optional[str] = None
    foreground_pid: Optional[int] = None
    foreground_hwnd: Optional[int] = None
    visible_windows: List[Dict[str, Any]] = field(default_factory=list)
    active_dialogs: List[Dict[str, Any]] = field(default_factory=list)
    task_owned_resources: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_prompt_str(self) -> str:
        """Render a concise markdown/text summary for injection into the reasoner prompt."""
        lines = []
        if self.foreground_app or self.foreground_window:
            lines.append(f"- Foreground Application: {self.foreground_app or 'Unknown'} ('{self.foreground_window or ''}') [PID: {self.foreground_pid}]")
        if self.visible_windows:
            win_titles = [f"'{w.get('title', '')}' ({w.get('app', '')})" for w in self.visible_windows[:5]]
            lines.append(f"- Visible Windows ({len(self.visible_windows)} total): " + ", ".join(win_titles))
        if self.active_dialogs:
            dialog_descs = [f"'{d.get('title', '')}' ({d.get('type', '')})" for d in self.active_dialogs]
            lines.append(f"- Active Modal Dialogs: " + ", ".join(dialog_descs))
        if self.task_owned_resources:
            lines.append(f"- Task Resources Owned: {len(self.task_owned_resources)} active tracked handles")
        return "\n".join(lines) if lines else "No desktop context available."


class WorldStateAdapter:
    """Compatibility adapter deriving a compact WorldStateSummary from DesktopObserver."""

    @staticmethod
    def summarize(state: DesktopWorldState) -> WorldStateSummary:
        """Extract a compact summary from an observed DesktopWorldState."""
        fg_win = None
        fg_app = None
        fg_pid = None
        fg_hwnd = state.foreground_hwnd

        # Find foreground window observation
        for win in state.windows:
            if win.hwnd == fg_hwnd or win.is_foreground:
                fg_win = win.title
                fg_app = win.application_identity or win.app_name
                fg_pid = win.pid
                break

        # Visible windows (exclude empty/hidden/minimized)
        visible = []
        for win in state.windows:
            if win.is_visible and not win.is_minimized and win.title:
                visible.append({
                    "hwnd": win.hwnd,
                    "title": win.title,
                    "app": win.application_identity or win.app_name,
                    "pid": win.pid,
                    "is_dialog": win.is_dialog,
                })

        # Dialogs
        dialogs = []
        for d in state.dialogs:
            dialogs.append({
                "hwnd": d.hwnd,
                "title": d.title,
                "type": d.dialog_type,
                "buttons": list(d.buttons),
            })

        # Task owned resources
        owned = list(state.astra_resources)

        return WorldStateSummary(
            foreground_window=fg_win,
            foreground_app=fg_app,
            foreground_pid=fg_pid,
            foreground_hwnd=fg_hwnd,
            visible_windows=visible,
            active_dialogs=dialogs,
            task_owned_resources=owned,
            timestamp=state.timestamp,
        )

    @classmethod
    def get_current_summary(cls, task_id: Optional[str] = None) -> WorldStateSummary:
        """Query DesktopObserver and return a fresh compact WorldStateSummary."""
        try:
            from astrarun.computer_use.observation.observer import DesktopObserver
            obs = DesktopObserver.get_instance()
            state = obs.observe(task_id=task_id, include_uia=False, include_dialogs=True)
            return cls.summarize(state)
        except Exception as exc:
            logger.debug("Failed to acquire live desktop state: %s", exc)
            return WorldStateSummary()
