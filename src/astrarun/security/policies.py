"""Deterministic security policy engines for AstraRun 1.0."""

from __future__ import annotations

import ast
import ctypes
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

from astrarun.core.logging import get_logger
from astrarun.security.models import ActionRequest, ActionGateVerdict, Operation, RiskLevel

logger = get_logger("astrarun.security.policies")


# =============================================================================
# 1. Path Security Policy Engine
# =============================================================================

def get_long_path_name(path: str) -> str:
    """Resolve Windows 8.3 short paths (e.g. PROGRA~1) to canonical long names."""
    if os.name != "nt":
        return path
    try:
        buf = ctypes.create_unicode_buffer(1024)
        res = ctypes.windll.kernel32.GetLongPathNameW(str(path), buf, 1024)
        if res > 0 and res < 1024:
            return buf.value
    except Exception:
        pass
    return path


class PathPolicy:
    """
    Operation-aware path authorization and boundary enforcement.
    Normalizes case, traversal, junctions, symlinks, 8.3 names, and environment variables.
    """

    DEFAULT_SYSTEM_ROOTS = [
        r"C:\Windows",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\ProgramData\Microsoft\Windows",
        r"C:\Recovery",
        r"C:\Boot",
    ]

    SENSITIVE_FILES = [
        r"drivers\etc\hosts",
        r"system32\config\sam",
        r"system32\config\system",
        r"system32\config\security",
        r".ssh\id_rsa",
        r".ssh\id_ed25519",
    ]

    def __init__(
        self,
        allowed_workspace_roots: Optional[List[str]] = None,
        disallowed_system_roots: Optional[List[str]] = None,
    ) -> None:
        from astrarun.core.paths import AstraPaths
        raw_workspaces = allowed_workspace_roots or [
            r"E:\Workspace",
            str(AstraPaths.data_dir()),
            str(AstraPaths.sandbox_dir()),
        ]
        self.allowed_workspaces = [self.normalize_path(p) for p in raw_workspaces]
        
        system_roots = list(disallowed_system_roots or self.DEFAULT_SYSTEM_ROOTS)
        sys_root_env = os.environ.get("SystemRoot")
        if sys_root_env and sys_root_env not in system_roots:
            system_roots.append(sys_root_env)
        sys_drive_env = os.environ.get("SystemDrive")
        if sys_drive_env:
            system_roots.append(f"{sys_drive_env}\\Windows")

        self.disallowed_system_roots = [self.normalize_path(p) for p in system_roots if p]

    @classmethod
    def normalize_path(cls, raw_path: str | Path) -> str:
        """
        Normalize Windows path handling:
        1. Environment variable expansion (%SystemRoot%, %USERPROFILE%)
        2. Resolve relative navigation (..)
        3. 8.3 short name expansion
        4. Symlink/junction resolution
        5. Case folding (Windows filesystem is case-insensitive)
        """
        if not raw_path:
            return ""
        
        # 1. Expand environment variables
        expanded = os.path.expandvars(str(raw_path).strip())
        
        # 2. Canonicalize separators
        cleaned = expanded.replace("/", "\\")
        
        # Handle UNC prefix if present
        is_unc = cleaned.startswith(r"\\")
        
        # 3. Resolve path and 8.3 aliases
        try:
            resolved = Path(cleaned).resolve()
            long_path = get_long_path_name(str(resolved))
        except Exception:
            long_path = cleaned

        # 4. Canonical case folding for comparison
        return long_path.lower().rstrip("\\")

    def is_in_system_location(self, normalized_path: str) -> bool:
        """Check if normalized path targets or resides inside a protected Windows system path."""
        for sys_root in self.disallowed_system_roots:
            if normalized_path == sys_root or normalized_path.startswith(sys_root + "\\"):
                return True
        for sens in self.SENSITIVE_FILES:
            if sens in normalized_path:
                return True
        return False

    def is_in_allowed_workspace(self, normalized_path: str) -> bool:
        """Check if normalized path resides inside an authorized workspace."""
        for ws in self.allowed_workspaces:
            if normalized_path == ws or normalized_path.startswith(ws + "\\"):
                return True
        return False

    def evaluate(self, request: ActionRequest) -> Tuple[ActionGateVerdict, str, RiskLevel]:
        """
        Evaluate path policy for an ActionRequest.
        """
        raw_target = request.target or request.parameters.get("path") or request.parameters.get("target") or ""
        if not raw_target:
            return ActionGateVerdict.ALLOW, "No path target specified", RiskLevel.LOW

        norm_target = self.normalize_path(raw_target)

        # 1. Check for system location violation
        if self.is_in_system_location(norm_target):
            if request.operation in (Operation.MODIFY, Operation.CREATE, Operation.DELETE, Operation.PRIVILEGED_MODIFY):
                return (
                    ActionGateVerdict.DENY,
                    f"Forbidden mutation targeting protected system directory: {raw_target}",
                    RiskLevel.CRITICAL,
                )
            elif request.operation == Operation.READ:
                # Sensitive system credentials / registry hives
                for sens in self.SENSITIVE_FILES:
                    if sens in norm_target:
                        return (
                            ActionGateVerdict.DENY,
                            f"Access denied to sensitive system file: {raw_target}",
                            RiskLevel.CRITICAL,
                        )
                # Generic read of system directory (e.g. inspect windows binary)
                return ActionGateVerdict.ALLOW, "Read-only system query", RiskLevel.LOW

        # 2. Deletions always require confirmation
        if request.operation == Operation.DELETE:
            if self.is_in_allowed_workspace(norm_target):
                return (
                    ActionGateVerdict.REQUIRE_CONFIRMATION,
                    f"File deletion within workspace requires explicit confirmation: {raw_target}",
                    RiskLevel.HIGH,
                )
            else:
                return (
                    ActionGateVerdict.REQUIRE_CONFIRMATION,
                    f"File deletion outside authorized workspace requires confirmation: {raw_target}",
                    RiskLevel.CRITICAL,
                )

        # 3. Workspace scope boundary enforcement for mutations
        if request.operation in (Operation.CREATE, Operation.MODIFY):
            if request.authorization_scope:
                norm_scope = self.normalize_path(request.authorization_scope)
                if not (norm_target == norm_scope or norm_target.startswith(norm_scope + "\\")):
                    return (
                        ActionGateVerdict.REQUIRE_CONFIRMATION,
                        f"Mutation target {raw_target} is outside authorized task scope {request.authorization_scope}",
                        RiskLevel.HIGH,
                    )
            elif not self.is_in_allowed_workspace(norm_target):
                # Outside any known workspace
                return (
                    ActionGateVerdict.REQUIRE_CONFIRMATION,
                    f"Target path {raw_target} is outside primary workspace boundaries",
                    RiskLevel.MEDIUM,
                )

        return ActionGateVerdict.ALLOW, "Path policy validated", RiskLevel.LOW


# =============================================================================
# 2. Command Security Policy Engine
# =============================================================================

class CommandPolicy:
    """
    Deterministic structural inspection of shell commands before execution.
    Intercepts destructive operations, format commands, forced git resets, and obfuscations.
    """

    # Unconditional BLOCK patterns
    BLOCKED_PATTERNS = [
        (r"\bformat\s+[a-zA-Z]:", "Disk format command is strictly forbidden"),
        (r"\bdiskpart\b", "Diskpart utility execution is strictly forbidden"),
        (r"\brmdir\s+/[sS]\s+/[qQ]\s+[a-zA-Z]:\\", "Root recursive directory deletion is strictly forbidden"),
        (r"\bdel\s+/[fF]\s+/[qQ]\s+/[sS]\s+[a-zA-Z]:\\", "Root recursive file deletion is strictly forbidden"),
        (r"\breg\s+delete\s+[\"']?HKLM", "Destructive machine registry deletion is strictly forbidden"),
        (r"\b(mkfs|dd\s+if=)", "Direct disk block manipulation is strictly forbidden"),
        (r"\b(del|rm|rmdir|Remove-Item|erase)\b.*(?:windows|system32|drivers\\etc\\hosts|\bsam\b|\bid_rsa\b)", "Destructive command targeting system directory or credentials is strictly forbidden"),
    ]

    # Mandatory CONFIRMATION patterns
    CONFIRM_PATTERNS = [
        (r"\bgit\s+reset\s+--hard\b", "git reset --hard discards uncommitted work", RiskLevel.HIGH),
        (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean removes untracked files", RiskLevel.HIGH),
        (r"\bgit\s+push\s+.*--force\b", "git force push can overwrite remote history", RiskLevel.CRITICAL),
        (r"\bgit\s+push\s+.*-f\b", "git force push can overwrite remote history", RiskLevel.CRITICAL),
        (r"\brm\s+-rf\b", "Recursive removal (rm -rf) requires confirmation", RiskLevel.HIGH),
        (r"\bdel\s+/[fF]\s+/[qQ]\b", "Forced quiet deletion (del /f /q) requires confirmation", RiskLevel.HIGH),
        (r"\bRemove-Item\b.*-Recurse.*-Force", "Recursive forced PowerShell removal requires confirmation", RiskLevel.HIGH),
        (r"\bClear-Content\b.*-Force", "Forced content clearing requires confirmation", RiskLevel.HIGH),
        (r"\b(drop\s+table|drop\s+database)\b", "Destructive SQL operation requires confirmation", RiskLevel.CRITICAL),
        (r"powershell.*-(e|enc|encodedcommand)\s+[A-Za-z0-9+/=]{10,}", "Encoded PowerShell script requires confirmation", RiskLevel.CRITICAL),
    ]

    def evaluate_command_string(self, cmd_line: str) -> Tuple[ActionGateVerdict, str, RiskLevel]:
        """
        Inspect a raw shell command string against structural safety policies.
        """
        if not cmd_line or not cmd_line.strip():
            return ActionGateVerdict.ALLOW, "Empty command", RiskLevel.LOW

        cleaned = cmd_line.strip()

        # 1. Evaluate hard-blocked patterns
        for pattern, reason in self.BLOCKED_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                return ActionGateVerdict.DENY, f"ActionGate Hard Policy Violation: {reason}", RiskLevel.CRITICAL

        # 2. Evaluate mandatory confirmation patterns
        for pattern, reason, risk in self.CONFIRM_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                return ActionGateVerdict.REQUIRE_CONFIRMATION, f"High-risk command requires confirmation: {reason}", risk

        # 3. Structural token inspection
        try:
            tokens = shlex.split(cleaned, posix=False)
        except Exception:
            tokens = cleaned.split()

        if tokens:
            executable = Path(tokens[0].strip('"\';')).name.lower()
            if executable in ("powershell.exe", "pwsh.exe", "cmd.exe"):
                # Inspect arguments to shell interpreters
                arg_str = " ".join(tokens[1:])
                for pattern, reason, risk in self.CONFIRM_PATTERNS:
                    if re.search(pattern, arg_str, re.IGNORECASE):
                        return ActionGateVerdict.REQUIRE_CONFIRMATION, f"Sub-shell command requires confirmation: {reason}", risk

        return ActionGateVerdict.ALLOW, "Command policy approved", RiskLevel.LOW


# =============================================================================
# 3. AST Python Code Inspection Engine
# =============================================================================

class ASTCodePolicy:
    """
    Syntactic AST inspector analyzing dynamic Python code before execution.
    Acts as a defense-in-depth gate detecting dangerous primitives and unauthorized imports.
    Delegates to canonical ASTInspector to ensure zero semantic policy divergence.
    """

    def __init__(self, inspector: Optional[Any] = None) -> None:
        from astrarun.tools.ast_inspector import ASTInspector
        self.inspector = inspector or ASTInspector()

    def evaluate_code(self, code_str: str) -> Tuple[ActionGateVerdict, str, RiskLevel]:
        """
        Inspect Python script AST for dangerous operations or obfuscated primitives.
        """
        if not code_str or not code_str.strip():
            return ActionGateVerdict.ALLOW, "Empty script", RiskLevel.LOW

        res = self.inspector.inspect(code_str)
        if not res.is_safe:
            violation_summary = "; ".join(res.violations[:3])
            return ActionGateVerdict.DENY, f"AST security violation: {violation_summary}", RiskLevel.CRITICAL

        # Additional defense-in-depth: check for obfuscated large base64 payload strings
        try:
            tree = ast.parse(code_str)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    val = node.value
                    if len(val) > 40 and re.fullmatch(r"[A-Za-z0-9+/=]+", val):
                        if any(term in code_str for term in ["b64decode", "decode", "frombase64"]):
                            return (
                                ActionGateVerdict.REQUIRE_CONFIRMATION,
                                "Synthesized script contains large base64-encoded payload",
                                RiskLevel.HIGH,
                            )
        except Exception:
            pass

        return ActionGateVerdict.ALLOW, "AST code safety check passed", RiskLevel.LOW
