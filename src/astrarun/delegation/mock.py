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

        # Check if this task involves projectile motion / trajectory
        is_projectile = any("projectile" in t.content.lower() or "trajectory" in t.content.lower() for t in session.turns) or ("projectile" in msg_lower or "trajectory" in msg_lower)

        # Final review request or clean execution
        if "approved" in msg_lower or "final review" in msg_lower or ("exit code: 0" in msg_lower and "[stderr]" not in msg_lower):
            return (
                "I have reviewed the execution output and created artifacts. "
                "The implementation looks correct, satisfies all requirements, and all tests pass! "
                "The solution is APPROVED."
            )

        # Error feedback from execution failure
        if ("exit code:" in msg_lower and "exit code: 0" not in msg_lower) or "error" in msg_lower or "traceback" in msg_lower:
            if is_projectile:
                return (
                    "I see the issue with calibration. Here is the corrected and self-contained code that computes the projectile trajectory, outputs trajectory.csv, and renders trajectory_plot.png:\n\n"
                    "```python\n"
                    "# filename: main.py\n"
                    "import os\n"
                    "import sys\n"
                    "import math\n"
                    "import csv\n"
                    "import struct\n"
                    "import zlib\n"
                    "from pathlib import Path\n"
                    "\n"
                    "def make_png(filename, points):\n"
                    "    w, h = 640, 480\n"
                    "    raw = bytearray()\n"
                    "    for _ in range(h):\n"
                    "        raw.append(0)\n"
                    "        raw.extend(b'\\xff\\xff\\xff' * w)\n"
                    "    max_x = max(p[1] for p in points) or 1.0\n"
                    "    max_y = max(p[2] for p in points) or 1.0\n"
                    "    stride = 1 + w * 3\n"
                    "    for _, x, y in points:\n"
                    "        px = int(50 + (x / max_x) * 540)\n"
                    "        py = int(430 - (y / max_y) * 380)\n"
                    "        if 0 <= px < w and 0 <= py < h:\n"
                    "            for dy in (-1, 0, 1):\n"
                    "                for dx in (-1, 0, 1):\n"
                    "                    nx, ny = px + dx, py + dy\n"
                    "                    if 0 <= nx < w and 0 <= ny < h:\n"
                    "                        idx = ny * stride + 1 + nx * 3\n"
                    "                        raw[idx] = 0; raw[idx+1] = 0; raw[idx+2] = 255\n"
                    "    def chunk(tag, data):\n"
                    "        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)\n"
                    "    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)\n"
                    "    idat = zlib.compress(bytes(raw))\n"
                    "    png_bytes = b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')\n"
                    "    with open(filename, 'wb') as f:\n"
                    "        f.write(png_bytes)\n"
                    "\n"
                    "def simulate():\n"
                    "    out_dir = os.environ.get('ASTRARUN_OUTPUT_DIR', '.')\n"
                    "    desktop_test_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'Astra Delegate Test')\n"
                    "    desktop_dir = os.path.join(os.path.expanduser('~'), 'Desktop')\n"
                    "    cur_dir = '.'\n"
                    "    v0, angle, g = 50.0, 45.0, 9.81\n"
                    "    rad = math.radians(angle)\n"
                    "    t = 0.0\n"
                    "    points = []\n"
                    "    while t <= 10.0:\n"
                    "        x = v0 * math.cos(rad) * t\n"
                    "        y = v0 * math.sin(rad) * t - 0.5 * g * t * t\n"
                    "        if y < 0 and t > 0:\n"
                    "            break\n"
                    "        points.append((t, x, max(0.0, y)))\n"
                    "        t += 0.05\n"
                    "\n"
                    "    for d in (cur_dir, out_dir, desktop_test_dir, desktop_dir):\n"
                    "        try:\n"
                    "            os.makedirs(d, exist_ok=True)\n"
                    "            with open(os.path.join(d, 'trajectory.csv'), 'w', newline='', encoding='utf-8') as f:\n"
                    "                writer = csv.writer(f)\n"
                    "                writer.writerow(['time', 'x', 'y'])\n"
                    "                for pt in points:\n"
                    "                    writer.writerow([round(pt[0], 2), round(pt[1], 2), round(pt[2], 2)])\n"
                    "            make_png(os.path.join(d, 'trajectory_plot.png'), points)\n"
                    "        except Exception:\n"
                    "            pass\n"
                    "\n"
                    "    print(f'Projectile simulation completed successfully with {len(points)} steps.')\n"
                    "\n"
                    "if __name__ == '__main__':\n"
                    "    simulate()\n"
                    "```\n\n"
                    "Please run this updated code and check the output."
                )
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

        # Initial turn (Turn 1):
        if is_projectile:
            return (
                "Here is the initial simulation code:\n\n"
                "```python\n"
                "# filename: main.py\n"
                "import os\n"
                "import csv\n"
                "\n"
                "def simulate():\n"
                "    # Initial uncalibrated draft\n"
                "    raise ValueError('Initial turn simulation requires calibration!')\n"
                "\n"
                "if __name__ == '__main__':\n"
                "    simulate()\n"
                "```\n\n"
                "Please execute this and report back the results."
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
