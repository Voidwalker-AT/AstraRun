"""Dynamic Goal Interpreter and Plan Generator for AstraRun v0.11 agent runtime."""

from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from astrarun.agent.models import (
    Goal,
    Plan,
    PlanStatus,
    PlanStep,
    ProgressMode,
    StepDependency,
    StepState,
)
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import InteractionTier, VerifierStrategy
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.agent.planner")


class GoalPlanner:
    """
    Translates high-level natural language user goals into structured, typed DAG execution plans.
    Strictly prohibits arbitrary shell synthesis; maps exclusively to typed registered capabilities.
    """

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        from astrarun.capabilities.registry import CapabilityRegistry
        self.registry = registry or CapabilityRegistry()

    def parse_goal(self, raw_prompt: str) -> Goal:
        """Parse raw user utterance into a normalized Goal representation."""
        clean = raw_prompt.strip()
        goal = Goal(
            goal_id=f"goal_{uuid.uuid4().hex[:8]}",
            raw_prompt=clean,
        )

        # 1. Battery Report Intent
        if re.search(r"\bbattery\s+report\b", clean, re.IGNORECASE):
            goal.intent = "generate_battery_report"
            # Extract output path or folder/filename
            # Patterns: "save it in Downloads as astra-battery.html", "save to Downloads/report.html", "as astra-battery.html"
            folder_match = re.search(r"\b(?:in|to)\s+(Downloads|Documents|Desktop)\b", clean, re.IGNORECASE)
            folder = folder_match.group(1) if folder_match else "Downloads"

            file_match = re.search(r"\bas\s+([a-zA-Z0-9_\-\.]+\.(?:html|xml))\b", clean, re.IGNORECASE)
            if not file_match:
                file_match = re.search(r"\b([a-zA-Z0-9_\-]+\.(?:html|xml))\b", clean, re.IGNORECASE)
            filename = file_match.group(1) if file_match else "battery-report.html"

            target_path = f"{folder}/{filename}"
            goal.parameters = {"output_path": target_path, "folder": folder, "filename": filename}
            goal.success_criteria = [f"File exists and non-empty at {target_path}"]
            return goal

        # 2. Wi-Fi Intents
        wifi_conn_match = re.search(r"\bconnect(?:\s+to)?(?:\s+wifi)?\s+([a-zA-Z0-9_\-\*\s]+?)(?:\s+wifi)?$", clean, re.IGNORECASE)
        if wifi_conn_match and "disconnect" not in clean.lower():
            target_ssid = wifi_conn_match.group(1).strip()
            # Remove trailing 'wifi' if matched
            target_ssid = re.sub(r"\s+wifi$", "", target_ssid, flags=re.IGNORECASE).strip()
            if target_ssid and target_ssid.lower() not in ("to", "a", "the", "network"):
                goal.intent = "wifi_connect"
                goal.parameters = {"ssid": target_ssid}
                goal.success_criteria = [f"Connected to Wi-Fi SSID '{target_ssid}'"]
                return goal

        if re.search(r"\b(?:disconnect|turn off)\s+(?:from\s+)?wifi\b", clean, re.IGNORECASE):
            goal.intent = "wifi_disconnect"
            goal.success_criteria = ["Wi-Fi disconnected"]
            return goal

        if re.search(r"\b(?:scan|list|find|show)\s+(?:available\s+)?wifi\b|\bwifi\s+scan\b", clean, re.IGNORECASE):
            goal.intent = "wifi_scan"
            goal.success_criteria = ["Wi-Fi scan list returned"]
            return goal

        if re.search(r"\b(?:check|show|get)?\s*wifi\s*(?:status|state|connection)?\b", clean, re.IGNORECASE):
            goal.intent = "wifi_status"
            goal.success_criteria = ["Wi-Fi status returned"]
            return goal

        # 3. System Power & Diagnostics
        if re.search(r"\b(?:check|get|show)\s+battery(?:\s+status)?\b", clean, re.IGNORECASE):
            goal.intent = "battery_status"
            goal.success_criteria = ["Battery status returned"]
            return goal

        # 4. Fallback / Compound app and typing
        goal.intent = "composite_workflow"
        return goal

    def create_plan(self, goal: Goal) -> Plan:
        """Construct a validated execution DAG for the given Goal."""
        plan = Plan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            goal_id=goal.goal_id,
            status=PlanStatus.DRAFT,
        )

        intent = goal.intent

        # 1. Battery Report
        if intent == "generate_battery_report":
            out_path = goal.parameters.get("output_path", "Downloads/battery-report.html")
            step = PlanStep(
                step_id="step_gen_battery_report",
                capability_id="generate_battery_report",
                arguments={"output_path": out_path},
                description=f"Generate Windows battery report into {out_path}",
                interaction_tier=InteractionTier.TIER_B_STRUCTURED_CLI,
                verifier_strategy=VerifierStrategy.FILE_NON_EMPTY,
                verifier_params={"path": out_path},
                weight=1.0,
            )
            plan.steps.append(step)

        # 2. Wi-Fi Capabilities
        elif intent == "wifi_scan":
            step = PlanStep(
                step_id="step_wifi_scan",
                capability_id="wifi_scan",
                arguments={},
                description="Scan available 802.11 wireless networks",
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
                weight=1.0,
            )
            plan.steps.append(step)

        elif intent == "wifi_status":
            step = PlanStep(
                step_id="step_wifi_status",
                capability_id="wifi_status",
                arguments={},
                description="Query active Wi-Fi adapter connection state",
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
                weight=1.0,
            )
            plan.steps.append(step)

        elif intent == "wifi_connect":
            ssid = goal.parameters.get("ssid", "")
            step = PlanStep(
                step_id="step_wifi_connect",
                capability_id="wifi_connect",
                arguments={"ssid": ssid},
                description=f"Connect to Wi-Fi network '{ssid}'",
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.NETWORK_SSID,
                verifier_params={"ssid": ssid},
                weight=1.0,
            )
            plan.steps.append(step)

        elif intent == "wifi_disconnect":
            step = PlanStep(
                step_id="step_wifi_disconnect",
                capability_id="wifi_disconnect",
                arguments={},
                description="Disconnect active Wi-Fi network connection",
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
                weight=1.0,
            )
            plan.steps.append(step)

        elif intent == "battery_status":
            step = PlanStep(
                step_id="step_battery_status",
                capability_id="battery_status",
                arguments={},
                description="Query system battery and charging status",
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
                weight=1.0,
            )
            plan.steps.append(step)

        # 5. Composite / Compound Natural Language Commands
        else:
            plan = self._decompose_composite_prompt(goal)

        plan.status = PlanStatus.ACTIVE
        return plan

    def _decompose_composite_prompt(self, goal: Goal) -> Plan:
        """Decompose compound utterances into sequential DAG steps."""
        plan = Plan(plan_id=f"plan_{uuid.uuid4().hex[:8]}", goal_id=goal.goal_id)
        prompt = goal.raw_prompt

        # Check for open app and type text: "open <app> and type <text>"
        app_type_match = re.search(
            r"^(?:open|launch)\s+([a-zA-Z0-9_\-\s]+?)\s+and\s+type\s+(.+)$",
            prompt,
            re.IGNORECASE,
        )
        if app_type_match:
            app_name = app_type_match.group(1).strip()
            text_to_type = app_type_match.group(2).strip()

            step1 = PlanStep(
                step_id="step_open_app",
                capability_id="open_application",
                arguments={"app_name": app_name},
                description=f"Launch application '{app_name}'",
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.WINDOW_READY,
                verifier_params={"title": app_name},
                weight=1.0,
            )
            step2 = PlanStep(
                step_id="step_type_text",
                capability_id="type_into_window",
                arguments={"app_name": app_name, "text": text_to_type},
                description=f"Type '{text_to_type}' into '{app_name}'",
                interaction_tier=InteractionTier.TIER_C_UI_AUTOMATION,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
                dependencies=[StepDependency(step_id="step_open_app")],
                weight=1.0,
            )
            plan.steps = [step1, step2]
            return plan

        # Single app launch: "open <app>"
        open_match = re.search(r"^(?:open|launch)\s+([a-zA-Z0-9_\-\s]+)$", prompt, re.IGNORECASE)
        if open_match:
            app_name = open_match.group(1).strip()
            step = PlanStep(
                step_id="step_open_app",
                capability_id="open_application",
                arguments={"app_name": app_name},
                description=f"Launch application '{app_name}'",
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.WINDOW_READY,
                verifier_params={"title": app_name},
                weight=1.0,
            )
            plan.steps = [step]
            return plan

        # Window snapping: "snap <app> to <left|right|top|bottom>"
        snap_match = re.search(r"^(?:snap)\s+([a-zA-Z0-9_\-\s]+?)\s+to\s+(left|right|top|bottom|half-left|half-right)$", prompt, re.IGNORECASE)
        if snap_match:
            app_name = snap_match.group(1).strip()
            position = snap_match.group(2).strip().lower()
            step = PlanStep(
                step_id="step_snap_window",
                capability_id="snap_window",
                arguments={"app_name": app_name, "position": position},
                description=f"Snap '{app_name}' to {position}",
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
                weight=1.0,
            )
            plan.steps = [step]
            return plan

        # Default single step attempt mapping to general router or prompt execution
        step = PlanStep(
            step_id="step_execute_intent",
            capability_id="system_summary",
            arguments={},
            description=f"Execute workstation request: {prompt}",
            interaction_tier=InteractionTier.TIER_A_NATIVE,
            verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            weight=1.0,
        )
        plan.steps = [step]
        return plan
