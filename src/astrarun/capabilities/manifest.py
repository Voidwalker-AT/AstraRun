"""Authoritative Capability Security Manifest for AstraRun.

Explicitly classifies all 82 production workstation capabilities into typed,
immutable CapabilitySecurityMetadata specifications. Ensures zero mutating
production capabilities rely on UNKNOWN_CONSEQUENTIAL fallbacks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from astrarun.security.models import (
    CapabilityOperationKind,
    CapabilitySecurityMetadata,
    RiskLevel,
)


AUTHORITATIVE_CAPABILITY_MANIFEST: Dict[str, CapabilitySecurityMetadata] = {
    # =========================================================================
    # APPLICATION (6)
    # =========================================================================
    "list_running_applications": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="application",
    ),
    "is_application_running": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="application",
    ),
    "find_application": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="application",
    ),
    "open_application": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.APPLICATION_LAUNCH,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="application",
    ),
    "focus_application": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="application",
    ),
    "close_application": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.APPLICATION_CLOSE,
        risk=RiskLevel.MEDIUM,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="application",
    ),

    # =========================================================================
    # FILE (8)
    # =========================================================================
    "find_file": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_READ,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "find_latest_file": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_READ,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "list_recent_files": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_READ,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "open_file": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.APPLICATION_LAUNCH,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "reveal_file": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "file_metadata": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_READ,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "save_text_file": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_CREATE,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "deliver_artifact": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_CREATE,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "render_visualization": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_CREATE,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="file",
    ),
    "open_folder": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_READ,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="file",
    ),

    # =========================================================================
    # PROCESS (8)
    # =========================================================================
    "list_processes": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="process",
    ),
    "find_process": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="process",
    ),
    "inspect_process": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="process",
    ),
    "process_resource_usage": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="process",
    ),
    "process_ports": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="process",
    ),
    "process_children": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="process",
    ),
    "process_parent": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="process",
    ),
    "terminate_process": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.PROCESS_KILL,
        risk=RiskLevel.HIGH,
        mutates_state=True,
        requires_confirmation=True,
        resource_scope="process",
    ),

    # =========================================================================
    # NETWORK (8)
    # =========================================================================
    "list_listening_ports": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.NETWORK_INSPECT,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="network",
    ),
    "inspect_port": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.NETWORK_INSPECT,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="network",
    ),
    "find_process_on_port": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.NETWORK_INSPECT,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="network",
    ),
    "list_network_connections": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.NETWORK_INSPECT,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="network",
    ),
    "open_url": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.BROWSER_NAVIGATE,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="network",
    ),
    "wifi_scan": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.NETWORK_INSPECT,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="network",
    ),
    "wifi_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.NETWORK_INSPECT,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="network",
    ),
    "wifi_connect": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.NETWORK_MUTATE,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="network",
    ),
    "wifi_disconnect": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.NETWORK_MUTATE,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="network",
    ),

    # =========================================================================
    # SYSTEM & AUDIO (11)
    # =========================================================================
    "system_summary": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="system",
    ),
    "cpu_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="system",
    ),
    "memory_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="system",
    ),
    "disk_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="system",
    ),
    "battery_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="system",
    ),
    "gpu_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="system",
    ),
    "audio_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SYSTEM_DIAGNOSTIC,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="audio",
    ),
    "lock_workstation": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.PRIVILEGED_SYSTEM,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="system",
    ),
    "shutdown_workstation": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.PRIVILEGED_SYSTEM,
        risk=RiskLevel.CRITICAL,
        mutates_state=True,
        requires_confirmation=True,
        resource_scope="system",
    ),
    "restart_workstation": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.PRIVILEGED_SYSTEM,
        risk=RiskLevel.CRITICAL,
        mutates_state=True,
        requires_confirmation=True,
        resource_scope="system",
    ),
    "generate_battery_report": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.FILE_CREATE,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="system",
    ),

    # =========================================================================
    # PROJECT (8)
    # =========================================================================
    "project_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="project",
    ),
    "project_git_status": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="project",
    ),
    "project_running_processes": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="project",
    ),
    "project_ports": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="project",
    ),
    "open_project_folder": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="project",
    ),
    "open_project_in_vscode": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.APPLICATION_LAUNCH,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="project",
    ),
    "open_project": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.APPLICATION_LAUNCH,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="project",
    ),
    "run_project_command": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.SHELL_EXEC,
        risk=RiskLevel.MEDIUM,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="project",
    ),

    # =========================================================================
    # WINDOW (17)
    # =========================================================================
    "list_windows": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "foreground_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "find_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "windows_for_application": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "wait_for_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "focus_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "minimize_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "maximize_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "restore_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "move_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "resize_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "move_window_to_monitor": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "snap_window_left": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "snap_window_right": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "close_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.APPLICATION_CLOSE,
        risk=RiskLevel.MEDIUM,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "undo_window_layout": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),
    "arrange_desktop": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="window",
    ),

    # =========================================================================
    # INTERACTION (13)
    # =========================================================================
    "inspect_window_ui": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "resolve_editable_element": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "get_clipboard_content": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "click_ui_element": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.MEDIUM,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "set_ui_element_value": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.MEDIUM,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "toggle_ui_element": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.MEDIUM,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "select_ui_element": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "focus_ui_element": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "scroll_ui_element": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "press_keyboard_shortcut": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "type_text": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "type_into_window": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "set_clipboard_content": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),
    "save_document_via_ui": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.UI_INTERACTION,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="interaction",
    ),


    # =========================================================================
    # WORKFLOW / DYNAMIC EXECUTION (2)
    # =========================================================================
    "execute_dynamic_tool": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.DYNAMIC_CODE_EXEC,
        risk=RiskLevel.MEDIUM,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="contained_workspace",
    ),
    "consult_delegate": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.DYNAMIC_CODE_EXEC,
        risk=RiskLevel.MEDIUM,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="delegation",
    ),

    # Legacy Aliases
    "open_app": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.APPLICATION_LAUNCH,
        risk=RiskLevel.LOW,
        mutates_state=True,
        requires_confirmation=False,
        resource_scope="application",
    ),
    "inspect_process_list": CapabilitySecurityMetadata(
        operation_kind=CapabilityOperationKind.OBSERVE_READ_ONLY,
        risk=RiskLevel.LOW,
        mutates_state=False,
        requires_confirmation=False,
        resource_scope="process",
    ),
}


def get_authoritative_metadata(capability_id: str) -> Optional[CapabilitySecurityMetadata]:
    """Retrieve authoritative CapabilitySecurityMetadata for a production capability."""
    return AUTHORITATIVE_CAPABILITY_MANIFEST.get(capability_id)
