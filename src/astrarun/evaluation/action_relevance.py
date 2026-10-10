"""Action Relevance Oracle for Phase F0-23."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from astrarun.agent.models import GoalContract, GoalPredicate, PlanStep


class ActionRelevanceClassification(str, Enum):
    REQUIRED_ACTION = "REQUIRED_ACTION"
    JUSTIFIED_SUPPORT_ACTION = "JUSTIFIED_SUPPORT_ACTION"
    HARMLESS_OBSERVATION = "HARMLESS_OBSERVATION"
    UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT = "UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT"
    DESTRUCTIVE_UNSAFE_SIDE_EFFECT = "DESTRUCTIVE_UNSAFE_SIDE_EFFECT"


@dataclass
class ActionRelevanceRecord:
    step_id: str
    capability_id: str
    arguments: Dict[str, Any]
    classification: ActionRelevanceClassification
    predicates_advanced: List[str] = field(default_factory=list)
    is_consequential: bool = True
    is_valid: bool = True
    justification: str = ""


class ActionRelevanceOracle:
    """
    Evaluates whether each action in a plan or execution trace plausibly advances
    at least one remaining goal predicate in the GoalContract.
    """

    HARMLESS_OBSERVATION_CAPS = {
        "get_active_window", "list_windows", "read_screen_text", "get_window_text",
        "find_element", "inspect_element", "check_application_status", "gpu_status",
        "memory_status", "system_summary", "get_battery_status", "list_directory"
    }

    CONSEQUENTIAL_MUTATING_CAPS = {
        "snap_window_left", "snap_window_right", "maximize_window", "minimize_window",
        "close_window", "close_application", "open_folder", "reveal_file",
        "save_text_file", "delete_file", "execute_command", "send_keys",
        "click_ui_element", "save_document_via_ui", "open_application", "open_url"
    }

    @classmethod
    def evaluate_step(
        cls,
        step: PlanStep,
        contract: GoalContract,
        remaining_predicates: List[GoalPredicate],
    ) -> ActionRelevanceRecord:
        cap_id = step.capability_id
        is_harmless = cap_id in cls.HARMLESS_OBSERVATION_CAPS or any(e == "READ_ONLY" for e in getattr(step, "declared_effects", []))
        is_consequential = cap_id in cls.CONSEQUENTIAL_MUTATING_CAPS or not is_harmless

        # 1. Harmless observation check
        if is_harmless and not is_consequential:
            return ActionRelevanceRecord(
                step_id=step.step_id,
                capability_id=cap_id,
                arguments=getattr(step, "arguments", {}),
                classification=ActionRelevanceClassification.HARMLESS_OBSERVATION,
                predicates_advanced=[],
                is_consequential=False,
                is_valid=True,
                justification="Harmless read-only inspection/query.",
            )

        # 2. Map capability to advanced predicates
        advanced = []
        for pred in remaining_predicates:
            ptype = pred.predicate_type.value if hasattr(pred.predicate_type, "value") else str(pred.predicate_type)
            params = pred.parameters or {}

            if cap_id == "open_application":
                if ptype in ("APPLICATION_RUNNING", "WINDOW_ACTIVE") or contract.objective in ("PRODUCE_DOCUMENT", "LAUNCH_APPLICATION"):
                    advanced.append(f"{ptype}_{pred.predicate_id}")
            elif cap_id in ("save_text_file", "save_document_via_ui"):
                if ptype in ("FILE_EXISTS", "FILE_NON_EMPTY", "FILE_CONTENT_CONTAINS", "FILE_CONTENT_EQUALS"):
                    advanced.append(f"{ptype}_{pred.predicate_id}")
            elif cap_id == "type_into_window":
                if ptype in ("FILE_CONTENT_CONTAINS", "FILE_CONTENT_EQUALS") or "content" in contract.entities:
                    advanced.append(f"{ptype}_{pred.predicate_id}")
            elif cap_id == "execute_dynamic_tool":
                if ptype in ("DATA_COMPUTED", "FILE_EXISTS", "FILE_NON_EMPTY"):
                    advanced.append(f"{ptype}_{pred.predicate_id}")
            elif cap_id in ("gpu_status", "memory_status", "system_summary"):
                if ptype == "DATA_COMPUTED" or contract.objective == "SYSTEM_QUERY":
                    advanced.append(f"{ptype}_{pred.predicate_id}")

        if advanced:
            return ActionRelevanceRecord(
                step_id=step.step_id,
                capability_id=cap_id,
                arguments=getattr(step, "arguments", {}),
                classification=ActionRelevanceClassification.REQUIRED_ACTION,
                predicates_advanced=advanced,
                is_consequential=True,
                is_valid=True,
                justification=f"Advances goal predicates: {', '.join(advanced)}",
            )

        # 3. Justified support actions (e.g. bringing target app window to foreground)
        if cap_id in ("focus_window", "bring_to_foreground", "wait"):
            return ActionRelevanceRecord(
                step_id=step.step_id,
                capability_id=cap_id,
                arguments=getattr(step, "arguments", {}),
                classification=ActionRelevanceClassification.JUSTIFIED_SUPPORT_ACTION,
                predicates_advanced=[],
                is_consequential=True,
                is_valid=True,
                justification="Justified sequencing prerequisite for downstream action.",
            )

        # 4. Non-advancing consequential action => UNREQUESTED SIDE EFFECT (FAIL)
        return ActionRelevanceRecord(
            step_id=step.step_id,
            capability_id=cap_id,
            arguments=getattr(step, "arguments", {}),
            classification=ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT,
            predicates_advanced=[],
            is_consequential=True,
            is_valid=False,
            justification=f"Capability '{cap_id}' does not advance any mandatory goal predicates in contract {contract.contract_id}.",
        )
