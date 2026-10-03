"""CandidateTool schema and DependencyRequest specification for AstraRun 1.0.

Provides strongly typed representations for dynamic ephemeral tools generated
by Astra's cognitive engines to solve novel user tasks.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DependencyRequest:
    """Explicit model-level dependency request.

    Autonomous agents MUST NOT run arbitrary pip install commands.
    If a generated candidate tool requires a package not currently installed,
    it must declare a DependencyRequest for governance evaluation.
    """
    package: str
    version_spec: Optional[str] = None
    source: str = "pypi"  # pypi, wheel, vendored, local
    reason: str = ""
    sandbox: str = "EPHEMERAL_TOOL"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DependencyRequest:
        return cls(
            package=data.get("package", ""),
            version_spec=data.get("version_spec"),
            source=data.get("source", "pypi"),
            reason=data.get("reason", ""),
            sandbox=data.get("sandbox", "EPHEMERAL_TOOL"),
        )


@dataclass
class CandidateTool:
    """Strongly typed dynamic candidate tool specification.

    Generated when no existing permanent tool or skill in Astra's registry
    satisfies the user's objective.
    """
    goal: str
    executable_code: str
    test_verification_block: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    external_dependencies: List[DependencyRequest] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    expected_side_effects: List[str] = field(default_factory=list)
    sandbox_profile: str = "EPHEMERAL_TOOL"
    tool_id: str = field(default_factory=lambda: f"dyn_tool_{uuid.uuid4().hex[:8]}")
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def full_script(self, include_test: bool = True) -> str:
        """Compose the full executable Python script including test/verification."""
        parts = [
            "# AstraRun 1.0 Governed Candidate Tool",
            f"# Tool ID: {self.tool_id}",
            f"# Goal: {self.goal}",
            "",
            self.executable_code.strip(),
            "",
        ]
        if include_test and self.test_verification_block.strip():
            parts.extend([
                "",
                "# --- Verification Block ---",
                "if __name__ == '__main__':",
            ])
            for line in self.test_verification_block.strip().splitlines():
                parts.append(f"    {line}")
        return "\n".join(parts) + "\n"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["external_dependencies"] = [dep.to_dict() for dep in self.external_dependencies]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CandidateTool:
        deps = [DependencyRequest.from_dict(d) for d in data.get("external_dependencies", [])]
        return cls(
            goal=data.get("goal", ""),
            executable_code=data.get("executable_code", ""),
            test_verification_block=data.get("test_verification_block", ""),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            external_dependencies=deps,
            required_permissions=data.get("required_permissions", []),
            expected_side_effects=data.get("expected_side_effects", []),
            sandbox_profile=data.get("sandbox_profile", "EPHEMERAL_TOOL"),
            tool_id=data.get("tool_id", f"dyn_tool_{uuid.uuid4().hex[:8]}"),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
        )
