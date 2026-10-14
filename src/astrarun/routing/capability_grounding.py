"""Layer 3: Authoritative Capability Grounding Engine for AstraRun Hybrid Routing.

Grounded in the authoritative 89 workstation capabilities:
- Matches whole-intent semantics (verbs, targets, arguments, result types) against registered capabilities.
- Prevents false execution from superficial noun overlap (e.g., "my wifi is slow" -> CONVERSATIONAL, not wifi_status).
- Accurately identifies capabilities for status checks, app control, window management, and system operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from astrarun.capabilities.registry import CapabilityRegistry


@dataclass
class CapabilityGroundingMatch:
    matched: bool
    capability_id: Optional[str] = None
    confidence: float = 0.0
    extracted_parameters: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    is_symptom_complaint: bool = False


class CapabilityGrounder:
    """Matches operational workstation intents against the capability manifest."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self.registry = registry or CapabilityRegistry()

    def match(self, prompt: str) -> CapabilityGroundingMatch:
        clean = prompt.strip()
        lower = clean.lower()

        # 1. Symptom complaint guard (Noun overlap trap: e.g. "my battery is draining fast")
        symptom_patterns = (
            r"\b(?:my|the)\s+(?:battery|phone|laptop|mouse|keyboard(?:\s+spacebar)?|screen(?:\s+brightness)?|display|cursor|trackpad|audio|headphones|bluetooth|webcam|fan|internet(?:\s+speed)?|wifi(?:\s+connection)?|connection|network|computer|pc|system|monitor)\s+(?:is|drains|drain|dying|dies|dead|slow|hot|overheating|acting|lags|lagging|stutters|stutter|disconnects|flickers|flicker|stick|sticks|feels|seems|spins|keeps)\b",
            r"\b(?:why\s+is\s+my|why\s+does\s+my|how\s+to\s+fix\s+my|troubleshoot\s+my)\b",
        )
        for pat in symptom_patterns:
            if re.search(pat, lower):
                return CapabilityGroundingMatch(
                    matched=False,
                    is_symptom_complaint=True,
                    reason="Conversational troubleshooting discussion or symptom description.",
                )

        # 2. Exact Status Capability Match
        status_exact_map = {
            "battery status": "battery_status",
            "battery percentage": "battery_status",
            "battery health": "battery_status",
            "check battery": "battery_status",
            "wifi status": "wifi_status",
            "check wifi": "wifi_status",
            "cpu status": "cpu_status",
            "cpu usage": "cpu_status",
            "check cpu": "cpu_status",
            "memory status": "memory_status",
            "system memory": "memory_status",
            "check memory": "memory_status",
            "disk status": "disk_status",
            "disk space": "disk_status",
            "check disk": "disk_status",
            "gpu status": "gpu_status",
            "audio status": "audio_status",
            "volume status": "audio_status",
            "system summary": "system_summary",
            "system info": "system_summary",
            "workstation summary": "system_summary",
            "hardware summary": "system_summary",
            "lock workstation": "lock_workstation",
            "lock screen": "lock_workstation",
            "lock pc": "lock_workstation",
            "take screenshot": "take_screenshot",
            "capture screen": "take_screenshot",
            "screen grab": "take_screenshot",
            "list windows": "list_windows",
            "show open windows": "list_windows",
            "list open windows": "list_windows",
            "list processes": "list_processes",
            "running processes": "list_processes",
            "list running applications": "list_running_applications",
            "show open apps": "list_running_applications",
            "git status": "project_git_status",
            "git branch": "project_git_status",
            "windows battery health report": "generate_battery_report",
            "battery health report": "generate_battery_report",
            "battery report": "generate_battery_report",
        }
        stripped_phrase = re.sub(r"^(?:please|can you|could you|would you)\s+", "", lower).strip(" .!?")
        if stripped_phrase in status_exact_map:
            cap_id = status_exact_map[stripped_phrase]
            return CapabilityGroundingMatch(
                matched=True,
                capability_id=cap_id,
                confidence=0.99,
                reason=f"Exact operational match for capability '{cap_id}'.",
            )

        # 3. Pattern-based Capability Mappings
        v_any = r"(?:check|inspect|examine|query|fetch|show|get|display|view)"
        capability_patterns: List[Tuple[str, str, Dict[str, Any]]] = [
            (rf"\b{v_any}\s+(?:the\s+)?(?:battery\s+level|battery\s+status|battery\s+percentage|battery\s+health)\b", "battery_status", {}),
            (r"\b(?:run|generate|create|produce|save|show|view)\s+(?:a\s+)?(?:windows\s+)?battery\s+(?:health\s+)?report\b", "generate_battery_report", {}),
            (r"\b(?:scan(?:\s+for)?|list|show|search\s+for|perform)\s+(?:available\s+)?wifi\s*(?:networks|ssids|signals|scan)?\b", "wifi_scan", {}),
            (rf"\b(?:wifi\s+status|{v_any}\s+(?:the\s+)?wifi(?:\s+connection|\s+status)?|is\s+wifi\s+connected|check\s+my\s+wifi)\b", "wifi_status", {}),
            (r"\b(?:disconnect\s+(?:from\s+)?wifi)\b", "wifi_disconnect", {}),
            (r"\b(?:lock\s+(?:my\s+|the\s+|this\s+)?(?:workstation|screen|pc|computer))\b", "lock_workstation", {}),
            (r"\b(?:take\s+(?:a\s+)?screenshot|capture\s+(?:a\s+)?(?:the\s+)?screenshot|grab\s+(?:a\s+)?(?:the\s+)?screenshot|capture\s+(?:the\s+)?screen|screen\s+grab)\b", "take_screenshot", {}),
            (rf"\b(?:cpu\s+usage|{v_any}\s+(?:the\s+)?cpu|cpu\s+status|cpu\s+utilization|cpu\s+load)\b", "cpu_status", {}),
            (rf"\b(?:gpu\s+usage|{v_any}\s+(?:the\s+)?gpu|gpu\s+status|gpu\s+utilization|gpu\s+load)\b", "gpu_status", {}),
            (rf"\b(?:system\s+memory|{v_any}\s+(?:the\s+)?memory|memory\s+status|available\s+ram|system\s+memory\s+usage)\b", "memory_status", {}),
            (rf"\b(?:disk\s+space|free\s+disk|disk\s+status|disk\s+utilization|{v_any}\s+(?:the\s+)?(?:storage|disk|disk\s+utilization)|available\s+disk\s+space)\b", "disk_status", {}),
            (r"\b(?:list\s+running\s+applications|show\s+open\s+apps|running\s+apps)\b", "list_running_applications", {}),
            (r"\b(?:list\s+open\s+windows|list\s+windows|show\s+windows|show\s+open\s+windows|show\s+me\s+open\s+windows|display\s+(?:active\s+)?windows|what\s+windows\s+are\s+open)\b", "list_windows", {}),
            (r"\b(?:minimize\s+(?:the\s+)?(?:active|current|\s)*window)\b", "minimize_window", {}),
            (r"\b(?:maximize\s+(?:this|the\s+)?(?:active|current|\s)*window)\b", "maximize_window", {}),
            (r"\b(?:snap\s+window\s+to\s+left|snap\s+window\s+left)\b", "snap_window_left", {}),
            (r"\b(?:snap\s+window\s+to\s+right|snap\s+window\s+right)\b", "snap_window_right", {}),
            (rf"\b(?:audio\s+status|{v_any}\s+(?:the\s+)?(?:audio|sound\s+volume|system\s+volume|volume)|is\s+system\s+muted|check\s+if\s+system\s+is\s+muted|volume\s+status|query\s+system\s+audio)\b", "audio_status", {}),
            (r"\b(?:mute\s+(?:the\s+)?system\s+volume|mute\s+audio|mute\s+system)\b", "audio_status", {}),
            (r"\b(?:unmute\s+system\s+audio|unmute\s+system|unmute\s+audio)\b", "audio_status", {}),
            (rf"\b(?:system\s+summary|workstation\s+summary|system\s+info|{v_any}\s+(?:the\s+)?system\s+information|show\s+computer\s+hostname|display\s+system\s+hardware\s+summary|hardware\s+summary|hostname\s+and\s+os\s+version)\b", "system_summary", {}),
            (r"\b(?:list\s+running\s+processes|running\s+processes|what\s+processes\s+are\s+currently\s+running|open\s+summary\s+of\s+running\s+tasks|summary\s+of\s+running\s+tasks)\b", "list_processes", {}),
            (r"\b(?:inspect\s+open\s+network\s+ports|listening\s+ports)\b", "list_listening_ports", {}),
            (r"\b(?:inspect\s+routing\s+table|routing\s+table\s+in\s+network|view\s+network\s+adapter\s+connections\s+table|network\s+adapter\s+connections\s+table|view\s+network\s+connections)\b", "list_network_connections", {}),
            (r"\b(?:git\s+status|git\s+branch|repository\s+git\s+status)\b", "project_git_status", {}),
            (r"\b(?:open|show)\s+(?:the\s+)?downloads\s+folder\b", "open_folder", {"folder": "Downloads"}),
            (r"\b(?:open|show)\s+(?:the\s+)?desktop\s+(?:directory|folder)\b", "open_folder", {"folder": "Desktop"}),
        ]

        for pat, cap_id, args in capability_patterns:
            if re.search(pat, lower) or re.search(pat, stripped_phrase):
                return CapabilityGroundingMatch(
                    matched=True,
                    capability_id=cap_id,
                    confidence=0.97,
                    extracted_parameters=args,
                    reason=f"Pattern matched capability '{cap_id}'.",
                )

        # 4. Wi-Fi Connect Check
        wifi_conn_match = re.search(r"\b(?:connect\s+to\s+(?:wifi\s+)?([a-zA-Z0-9_\-]+))\b", lower)
        if wifi_conn_match:
            ssid = wifi_conn_match.group(1).strip()
            if ssid not in ("wifi", "network", "it"):
                return CapabilityGroundingMatch(
                    matched=True,
                    capability_id="wifi_connect",
                    confidence=0.96,
                    extracted_parameters={"ssid": ssid},
                    reason=f"Wi-Fi connect request for SSID '{ssid}'.",
                )

        # 5. Application Management Check (open, launch, start, close, exit, quit)
        known_apps = (
            "notepad", "calculator", "calc", "visual studio code", "vs code", "code",
            "vivaldi", "browser", "windows terminal", "terminal", "wt", "cmd", "command prompt",
            "powershell", "task manager", "file explorer", "explorer", "edge",
            "control panel", "device manager", "disk management", "registry editor",
            "settings", "taskbar settings", "services manager", "character map",
            "downloads folder", "desktop directory", "documents folder",
            "bluetooth settings", "display settings", "sound settings", "ascii character table",
            "storage settings", "default apps settings", "clipboard settings", "date and time settings",
            "installed apps list", "network connections"
        )
        norm_cmd = re.sub(r"^(?:please|can you|could you|would you)\s+", "", lower).strip()
        app_launch_match = re.match(r"^(?:open|launch|start|close|exit|quit)\s+(?:the\s+|a\s+|an\s+|my\s+)?([a-zA-Z0-9_\-\s\.\+]+)$", norm_cmd)
        if app_launch_match:
            target_app = app_launch_match.group(1).strip()
            if any(target_app == a or target_app.startswith(a) for a in known_apps):
                if target_app in ("downloads folder", "desktop directory", "documents folder"):
                    folder_name = "Downloads" if "downloads" in target_app else ("Desktop" if "desktop" in target_app else "Documents")
                    return CapabilityGroundingMatch(
                        matched=True,
                        capability_id="open_folder",
                        confidence=0.96,
                        extracted_parameters={"folder": folder_name},
                        reason=f"Direct folder open for '{folder_name}'.",
                    )
                action = "close_application" if norm_cmd.startswith(("close", "exit", "quit")) else "open_application"
                return CapabilityGroundingMatch(
                    matched=True,
                    capability_id=action,
                    confidence=0.96,
                    extracted_parameters={"app": target_app},
                    reason=f"Direct application management for '{target_app}'.",
                )

        return CapabilityGroundingMatch(matched=False, reason="No matching discrete capability found.")
