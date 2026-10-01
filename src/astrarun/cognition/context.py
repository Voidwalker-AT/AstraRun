"""Context budget and token accounting interface for AstraRun cognition.

Provides pre-allocation budgeting and tracking across:
  - System prompt tokens
  - Task and goal tokens
  - History tokens (bounded rolling window)
  - Tool/capability schema tokens
  - Reserved output generation budget
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TokenBudget:
    """Pre-allocated token allocation ceiling for a cognitive request."""
    max_context_window: int = 4096
    max_output_tokens: int = 1024
    max_history_tokens: int = 1024
    max_schema_tokens: int = 1024
    reserved_system_tokens: int = 512

    @property
    def max_input_tokens(self) -> int:
        return self.max_context_window - self.max_output_tokens


@dataclass
class ContextBreakdown:
    """Detailed accounting of consumed tokens per partition."""
    system_tokens: int = 0
    task_tokens: int = 0
    history_tokens: int = 0
    tool_schema_tokens: int = 0
    total_input_tokens: int = 0
    output_budget: int = 0
    is_within_budget: bool = True
    overflow_tokens: int = 0


class ContextBudgetManager:
    """
    Computes token budgets and trims task history to ensure inference requests
    remain strictly within the model's physical context bounds.
    """

    def __init__(self, default_budget: Optional[TokenBudget] = None):
        self.budget = default_budget or TokenBudget()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Fast local token count estimation (~3.8 characters per token for English/code).
        Provides a conservative upper bound without requiring full tokenizer dependencies.
        """
        if not text:
            return 0
        return max(1, int(len(text) / 3.8) + 1)

    def analyze_budget(
        self,
        system_instruction: str,
        task_prompt: str,
        history_turns: List[Dict[str, str]],
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        requested_output_tokens: Optional[int] = None,
    ) -> ContextBreakdown:
        """Analyze and account token allocation across all context partitions."""
        sys_tokens = self.estimate_tokens(system_instruction)
        task_tokens = self.estimate_tokens(task_prompt)

        schema_str = str(tool_schemas) if tool_schemas else ""
        schema_tokens = self.estimate_tokens(schema_str)

        history_str = " ".join(t.get("content", "") for t in history_turns)
        hist_tokens = self.estimate_tokens(history_str)

        total_input = sys_tokens + task_tokens + schema_tokens + hist_tokens
        out_budget = requested_output_tokens or self.budget.max_output_tokens

        max_allowed = self.budget.max_context_window - out_budget
        is_within = total_input <= max_allowed
        overflow = max(0, total_input - max_allowed)

        return ContextBreakdown(
            system_tokens=sys_tokens,
            task_tokens=task_tokens,
            history_tokens=hist_tokens,
            tool_schema_tokens=schema_tokens,
            total_input_tokens=total_input,
            output_budget=out_budget,
            is_within_budget=is_within,
            overflow_tokens=overflow,
        )

    def prune_history_to_fit(
        self,
        system_instruction: str,
        task_prompt: str,
        history_turns: List[Dict[str, str]],
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        requested_output_tokens: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Prune history turns from oldest to newest until context fits within budget.
        Always preserves the system instruction and current task prompt.
        """
        breakdown = self.analyze_budget(
            system_instruction=system_instruction,
            task_prompt=task_prompt,
            history_turns=history_turns,
            tool_schemas=tool_schemas,
            requested_output_tokens=requested_output_tokens,
        )
        if breakdown.is_within_budget:
            return list(history_turns)

        # Truncate oldest turns
        pruned = list(history_turns)
        while pruned and not breakdown.is_within_budget:
            pruned.pop(0)  # Evict oldest turn
            breakdown = self.analyze_budget(
                system_instruction=system_instruction,
                task_prompt=task_prompt,
                history_turns=pruned,
                tool_schemas=tool_schemas,
                requested_output_tokens=requested_output_tokens,
            )

        return pruned
