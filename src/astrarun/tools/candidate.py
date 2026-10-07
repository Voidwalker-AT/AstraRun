"""CandidateTool schema, DependencyRequest, and CodeProvenance for AstraRun 1.0.

Provides strongly typed representations for dynamic ephemeral tools generated
by Astra's cognitive engines to solve novel user tasks.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RevisionRecord:
    """Immutable audit record for a single synthesis or repair revision."""
    revision_number: int
    generation_request_id: str = ""
    sandbox_execution_id: str = ""
    request_id: str = ""  # Backward compatibility alias
    prompt_hash: str = ""
    response_hash: str = ""
    source_hash: str = ""
    entrypoint_hash: str = ""
    tree_hash: str = ""
    ast_safe: bool = True
    ast_violations: List[str] = field(default_factory=list)
    staged_hash: str = ""
    executed_hash: str = ""
    exit_code: Optional[int] = None
    stdout_summary: str = ""
    stderr_summary: str = ""
    artifacts_created: List[str] = field(default_factory=list)
    verification_status: str = "UNVERIFIED"
    parent_revision: Optional[int] = None
    repair_reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.generation_request_id and not self.request_id:
            self.request_id = self.generation_request_id
        elif self.request_id and not self.generation_request_id:
            self.generation_request_id = self.request_id
        if not self.entrypoint_hash and self.source_hash:
            self.entrypoint_hash = self.source_hash

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RevisionRecord:
        return cls(**data)


@dataclass
class CodeProvenance:
    """Rigorous audit provenance for model-generated source artifacts across revisions."""
    task_id: str
    model: str
    model_version: str = "1.5b-instruct"
    generation_request_id: str = ""
    sandbox_execution_id: str = ""
    successful_execution_id: str = ""
    prompt_hash: str = ""
    source_hash: str = ""
    entrypoint_hash: str = ""
    tree_hash: str = ""
    revision: int = 1
    parent_revision: Optional[int] = None
    reason_for_revision: str = "initial_synthesis"
    stdout_summary: str = ""
    stderr_summary: str = ""
    artifact_hashes: Dict[str, str] = field(default_factory=dict)
    verification_result: str = "UNVERIFIED"
    final_revision: int = 1
    final_source_hash: str = ""
    revisions: List[RevisionRecord] = field(default_factory=list)

    def record_revision(self, rev: RevisionRecord) -> None:
        """Append an immutable revision record to history."""
        self.revisions.append(rev)
        self.revision = rev.revision_number
        self.parent_revision = rev.parent_revision
        self.source_hash = rev.source_hash
        self.entrypoint_hash = rev.entrypoint_hash or rev.source_hash
        self.tree_hash = rev.tree_hash
        self.final_revision = rev.revision_number
        self.final_source_hash = rev.source_hash
        if rev.generation_request_id:
            self.generation_request_id = rev.generation_request_id
        if rev.sandbox_execution_id:
            self.sandbox_execution_id = rev.sandbox_execution_id
        if rev.exit_code == 0 and rev.verification_status in ("PASSED", "VERIFIED", "SUCCESS"):
            # Section G: successful_execution_id must identify the SANDBOX EXECUTION
            self.successful_execution_id = rev.sandbox_execution_id or rev.request_id

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["revisions"] = [r.to_dict() if isinstance(r, RevisionRecord) else r for r in self.revisions]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CodeProvenance:
        revs_raw = data.get("revisions", [])
        revs = [RevisionRecord.from_dict(r) if isinstance(r, dict) else r for r in revs_raw]
        cleaned = dict(data)
        cleaned["revisions"] = revs
        return cls(**cleaned)


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
    satisfies the user's objective. Supports single-file and multi-file projects.
    """
    goal: str = ""
    executable_code: str = ""
    test_verification_block: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    external_dependencies: List[DependencyRequest] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    expected_side_effects: List[str] = field(default_factory=list)
    sandbox_profile: str = "EPHEMERAL_TOOL"
    tool_id: str = field(default_factory=lambda: f"dyn_tool_{uuid.uuid4().hex[:8]}")
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Architectural Spine Extensions
    purpose: str = ""
    language: str = "python"
    source_files: Dict[str, str] = field(default_factory=dict)  # {"main.py": "...", "utils.py": "..."}
    entrypoint: str = "main.py"
    filesystem_scope: str = "WORKSPACE"
    network_requirement: str = "NONE"  # NONE, LOOPBACK, APPROVED_ENDPOINTS
    risk_class: str = "LOW"             # LOW, MEDIUM, HIGH, CRITICAL
    timeout: float = 30.0
    memory_limit_mb: float = 512.0
    verification_plan: List[str] = field(default_factory=list)
    generator_model: str = "qwen2.5-coder"
    provenance: Optional[CodeProvenance] = None

    @staticmethod
    def _clean_code_fences(code: str) -> str:
        s = code.strip()
        if s.startswith("```"):
            lines = s.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return s

    def __post_init__(self) -> None:
        if not self.purpose:
            self.purpose = self.goal
        if not self.goal:
            self.goal = self.purpose
        if not self.source_files and self.executable_code:
            self.source_files = {self.entrypoint: self.executable_code}
        elif self.source_files and not self.executable_code:
            self.executable_code = self.source_files.get(self.entrypoint, "")

        if self.executable_code and self.executable_code.strip().startswith("```"):
            cleaned = self._clean_code_fences(self.executable_code)
            self.executable_code = cleaned
            if self.entrypoint in self.source_files:
                self.source_files[self.entrypoint] = cleaned

        for k, v in list(self.source_files.items()):
            if v and v.strip().startswith("```"):
                self.source_files[k] = self._clean_code_fences(v)

    def derive_repaired(self, new_code: str, reason: str = "structured_repair") -> CandidateTool:
        """Derive a new CandidateTool instance with updated source code for the entrypoint."""
        cleaned_code = self._clean_code_fences(new_code)
        new_sources = dict(self.source_files)
        new_sources[self.entrypoint] = cleaned_code
        return CandidateTool(
            goal=self.goal,
            executable_code=cleaned_code,
            test_verification_block=self.test_verification_block,
            inputs=self.inputs,
            outputs=self.outputs,
            external_dependencies=self.external_dependencies,
            required_permissions=self.required_permissions,
            expected_side_effects=self.expected_side_effects,
            sandbox_profile=self.sandbox_profile,
            tool_id=self.tool_id,
            task_id=self.task_id,
            created_at=self.created_at,
            metadata=self.metadata,
            purpose=self.purpose,
            language=self.language,
            source_files=new_sources,
            entrypoint=self.entrypoint,
            filesystem_scope=self.filesystem_scope,
            network_requirement=self.network_requirement,
            risk_class=self.risk_class,
            timeout=self.timeout,
            memory_limit_mb=self.memory_limit_mb,
            verification_plan=self.verification_plan,
            generator_model=self.generator_model,
            provenance=self.provenance,
        )

    @property
    def is_multi_file(self) -> bool:
        return len(self.source_files) > 1

    def compute_entrypoint_hash(self) -> str:
        """Compute SHA256 of the primary entrypoint source code."""
        code = self.source_files.get(self.entrypoint, self.executable_code)
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    def compute_tree_hash(self) -> str:
        """Compute SHA256 tree hash of all source files."""
        hasher = hashlib.sha256()
        for path in sorted(self.source_files.keys()):
            hasher.update(path.encode("utf-8"))
            hasher.update(self.source_files[path].encode("utf-8"))
        return hasher.hexdigest()

    def compute_source_hash(self) -> str:
        """
        Compute authoritative source hash.
        For single-file tools, matches the staged entrypoint file content SHA-256 exactly.
        For multi-file projects, returns the deterministic tree hash.
        """
        if self.is_multi_file:
            return self.compute_tree_hash()
        return self.compute_entrypoint_hash()

    def full_script(self, include_test: bool = True) -> str:
        """Compose the full executable Python script including test/verification."""
        main_code = self.source_files.get(self.entrypoint, self.executable_code)
        parts = [
            "# AstraRun 1.0 Governed Candidate Tool",
            f"# Tool ID: {self.tool_id}",
            f"# Goal: {self.goal}",
            "",
            main_code.strip(),
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
        if self.provenance:
            d["provenance"] = self.provenance.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CandidateTool:
        deps = [DependencyRequest.from_dict(d) for d in data.get("external_dependencies", [])]
        prov_data = data.get("provenance")
        prov = CodeProvenance.from_dict(prov_data) if prov_data else None

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
            task_id=data.get("task_id", f"task_{uuid.uuid4().hex[:8]}"),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
            purpose=data.get("purpose", ""),
            language=data.get("language", "python"),
            source_files=data.get("source_files", {}),
            entrypoint=data.get("entrypoint", "main.py"),
            filesystem_scope=data.get("filesystem_scope", "WORKSPACE"),
            network_requirement=data.get("network_requirement", "NONE"),
            risk_class=data.get("risk_class", "LOW"),
            timeout=float(data.get("timeout", 30.0)),
            memory_limit_mb=float(data.get("memory_limit_mb", 512.0)),
            verification_plan=data.get("verification_plan", []),
            generator_model=data.get("generator_model", "qwen2.5-coder"),
            provenance=prov,
        )
