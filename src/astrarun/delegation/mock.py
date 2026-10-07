"""MockDelegateProvider: Deterministic testing provider for delegated agent orchestration.

Allows complete testing of multi-turn conversation loops, proposal parsing,
runtime repair feedback, approval checking, iteration budgets, and failure handling
without requiring real network access or external accounts.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from astrarun.delegation.models import DelegateProposal, DelegateResponse, DelegateSession, ReviewStatus
from astrarun.delegation.proposal import parse_delegate_proposal
from astrarun.delegation.provider import DelegateProvider


class MockDelegateProvider(DelegateProvider):
    """Deterministic mock provider with scripted or rule-based turn behaviors."""

    def __init__(
        self,
        name: str = "mock",
        turn_responses: Optional[List[str]] = None,
        rule_based: bool = True,
        simulate_unavailable: bool = False,
        simulate_timeout: bool = False,
        simulate_error: Optional[str] = None,
    ) -> None:
        self._name = name
        self.turn_responses = turn_responses or []
        self.rule_based = rule_based
        self.simulate_unavailable = simulate_unavailable
        self.simulate_timeout = simulate_timeout
        self.simulate_error = simulate_error
        self.invocations: List[Dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return not self.simulate_unavailable

    def ask(
        self,
        session: DelegateSession,
        prompt: str,
        context: Optional[str] = None,
    ) -> DelegateResponse:
        """Start conversation or first turn."""
        return self._handle_turn(session, prompt, context)

    def continue_conversation(
        self,
        session: DelegateSession,
        message: str,
        context: Optional[str] = None,
    ) -> DelegateResponse:
        """Continue conversation in ongoing session."""
        return self._handle_turn(session, message, context)

    def _handle_turn(
        self,
        session: DelegateSession,
        message: str,
        context: Optional[str] = None,
    ) -> DelegateResponse:
        t_start = time.perf_counter()

        if self.simulate_unavailable:
            raise ConnectionError(f"MockDelegateProvider '{self._name}' is unavailable.")

        if self.simulate_timeout:
            raise TimeoutError(f"MockDelegateProvider '{self._name}' timed out after 30.0s.")

        if self.simulate_error:
            raise RuntimeError(f"MockDelegateProvider error: {self.simulate_error}")

        # Record outbound turn
        session.add_outbound_turn(message, {"context": context})

        turn_idx = len(session.turns) // 2

        # 1. Scripted responses list
        if self.turn_responses and turn_idx - 1 < len(self.turn_responses):
            raw_reply = self.turn_responses[turn_idx - 1]
        # 2. Rule-based autonomous mock
        elif self.rule_based:
            raw_reply = self._generate_rule_based_response(session, message)
        else:
            raw_reply = (
                "Here is the proposed Python code:\n```python\n# filename: solution.py\n"
                "print('Hello from MockDelegate!')\n```\nPlease run this locally."
            )

        proposal = parse_delegate_proposal(raw_reply)
        session.add_inbound_turn(raw_reply, proposal)

        latency_ms = (time.perf_counter() - t_start) * 1000.0

        resp = DelegateResponse(
            raw_content=raw_reply,
            proposal=proposal,
            turn_number=session.current_turn,
            model_name=f"mock-{self._name}-v1",
            latency_ms=latency_ms,
            provider_metadata={"session_id": session.session_id, "conversation_handle": session.conversation_handle},
        )

        self.invocations.append({
            "session_id": session.session_id,
            "turn_number": session.current_turn,
            "message": message,
            "response": raw_reply,
        })

        return resp

    def _generate_rule_based_response(self, session: DelegateSession, message: str) -> str:
        """Simulate realistic multi-turn reasoning: initial code -> repair on error -> approval on success."""
        msg_lower = message.lower()

        # Final review request or clean execution
        if "approved" in msg_lower or "final review" in msg_lower or ("exit code: 0" in msg_lower and "[stderr]" not in msg_lower):
            return (
                "I have reviewed the execution output and created artifacts. "
                "The implementation looks correct, satisfies all requirements, and all tests pass! "
                "The solution is APPROVED."
            )

        # Error feedback from execution failure
        if "exit code:" in msg_lower and "exit code: 0" not in msg_lower or "error" in msg_lower or "traceback" in msg_lower:
            return (
                "I see the issue with the previous implementation. The error indicates an issue during execution. "
                "Here is the corrected and self-contained code:\n\n"
                "```python\n"
                "# filename: main.py\n"
                "import os\n"
                "from pathlib import Path\n"
                "\n"
                "def solve():\n"
                "    print('Repaired solution executing successfully.')\n"
                "\n"
                "if __name__ == '__main__':\n"
                "    solve()\n"
                "```\n\n"
                "Please run this updated code and check the output."
            )

        # Generic Python task proposal
        return (
            "Here is the recommended Python solution:\n\n"
            "```python\n"
            "# filename: main.py\n"
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "def run():\n"
            "    print('Initial task proposal execution.')\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    run()\n"
            "```\n\n"
            "Please execute this and report back the results."
        )
