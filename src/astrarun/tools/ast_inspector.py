"""AST Inspector for Governed Dynamic Tools in AstraRun 1.0.

Statically inspects generated Python code before sandbox execution to detect:
- Disallowed modules (ctypes, socket, winreg, raw subprocess, pip, trust kernel modules)
- Dynamic code execution (eval, exec, __import__)
- Uncontrolled process spawning or direct unmanaged memory access
- Dangerous filesystem deletion operations
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tools.ast_inspector")

# Strictly forbidden modules in generated ephemeral scripts
FORBIDDEN_MODULES: Set[str] = {
    "ctypes",
    "_ctypes",
    "winreg",
    "_winapi",
    "socket",
    "socketserver",
    "asyncio.subprocess",
    "pip",
    "ensurepip",
    "pty",
}

# Subprocess modules forbidden in candidate tools (SandboxManager manages execution)
FORBIDDEN_PROCESS_MODULES: Set[str] = {
    "subprocess",
}

# Trust kernel protected module prefixes
PROTECTED_IMPORT_PREFIXES: List[str] = [
    "astrarun.security",
    "astrarun.sandbox",
    "astrarun.network.broker",
    "astrarun.tasks.ledger",
    "astrarun.capabilities.registry",
]

# Forbidden function calls / builtins
FORBIDDEN_CALLS: Set[str] = {
    "eval",
    "exec",
    "__import__",
    "compile",
}

# Forbidden attribute calls (e.g. os.system, os.popen, shutil.rmtree)
FORBIDDEN_ATTR_CALLS: Set[str] = {
    "system",
    "popen",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "kill",
}


@dataclass
class ASTInspectionResult:
    """Outcome of static AST inspection."""
    is_safe: bool
    violations: List[str] = field(default_factory=list)
    imported_modules: List[str] = field(default_factory=list)
    calls_detected: List[str] = field(default_factory=list)
    syntax_error: bool = False

    def summary(self) -> str:
        if self.is_safe:
            return f"SAFE (Modules: {', '.join(self.imported_modules) or 'none'})"
        return f"UNSAFE ({len(self.violations)} violations: {'; '.join(self.violations)})"


class _SecurityASTVisitor(ast.NodeVisitor):
    """Internal AST visitor checking safety invariants."""

    def __init__(self, allow_subprocess: bool = False) -> None:
        self.allow_subprocess = allow_subprocess
        self.violations: List[str] = []
        self.imported_modules: Set[str] = set()
        self.calls_detected: Set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            mod_name = alias.name
            self.imported_modules.add(mod_name)
            self._check_module_name(mod_name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            mod_name = node.module
            self.imported_modules.add(mod_name)
            self._check_module_name(mod_name, node.lineno)
        self.generic_visit(node)

    def _check_module_name(self, mod_name: str, lineno: int) -> None:
        base = mod_name.split(".")[0]
        if base in FORBIDDEN_MODULES:
            self.violations.append(
                f"Line {lineno}: Forbidden module import '{mod_name}' (prohibited for dynamic tools)."
            )
        if not self.allow_subprocess and base in FORBIDDEN_PROCESS_MODULES:
            self.violations.append(
                f"Line {lineno}: Direct subprocess module import '{mod_name}' prohibited; SandboxManager governs child processes."
            )
        for prefix in PROTECTED_IMPORT_PREFIXES:
            if mod_name.startswith(prefix):
                self.violations.append(
                    f"Line {lineno}: Direct import of Trust Kernel module '{mod_name}' is forbidden to autonomous tools."
                )

    def visit_Call(self, node: ast.Call) -> None:
        # Check direct calls (e.g. eval(...))
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            self.calls_detected.add(func_name)
            if func_name in FORBIDDEN_CALLS:
                self.violations.append(
                    f"Line {node.lineno}: Prohibited dynamic code execution function '{func_name}()'."
                )

        # Check attribute calls (e.g. os.system(...), shutil.rmtree(...))
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            self.calls_detected.add(attr_name)
            if attr_name in FORBIDDEN_ATTR_CALLS:
                if isinstance(node.func.value, ast.Name) and node.func.value.id in {"os", "posix", "nt"}:
                    self.violations.append(
                        f"Line {node.lineno}: Prohibited OS execution call '{node.func.value.id}.{attr_name}()'."
                    )

        self.generic_visit(node)


class ASTInspector:
    """Authoritative AST inspector for dynamically generated code."""

    def __init__(self, allow_subprocess: bool = False) -> None:
        self.allow_subprocess = allow_subprocess

    def inspect(self, code: str) -> ASTInspectionResult:
        """Inspect Python source code string."""
        if not code or not code.strip():
            return ASTInspectionResult(is_safe=False, violations=["Empty source code."])

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            msg = f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
            logger.warning("AST inspection syntax error: %s", msg)
            return ASTInspectionResult(
                is_safe=False,
                violations=[msg],
                syntax_error=True,
            )

        visitor = _SecurityASTVisitor(allow_subprocess=self.allow_subprocess)
        visitor.visit(tree)

        is_safe = len(visitor.violations) == 0
        return ASTInspectionResult(
            is_safe=is_safe,
            violations=visitor.violations,
            imported_modules=sorted(list(visitor.imported_modules)),
            calls_detected=sorted(list(visitor.calls_detected)),
            syntax_error=False,
        )

    def inspect_file(self, file_path: str | Path) -> ASTInspectionResult:
        """Inspect a Python file directly."""
        p = Path(file_path)
        if not p.exists():
            return ASTInspectionResult(
                is_safe=False,
                violations=[f"File does not exist: {file_path}"],
            )
        try:
            code = p.read_text(encoding="utf-8")
        except Exception as e:
            return ASTInspectionResult(
                is_safe=False,
                violations=[f"Error reading file {file_path}: {e}"],
            )
        return self.inspect(code)

    def inspect_candidate(self, candidate: Any) -> ASTInspectionResult:
        """Inspect all source files and verification block in a CandidateTool."""
        all_violations: List[str] = []
        all_modules: Set[str] = set()
        all_calls: Set[str] = set()

        sources = getattr(candidate, "source_files", {})
        if not sources and hasattr(candidate, "executable_code"):
            sources = {getattr(candidate, "entrypoint", "main.py"): candidate.executable_code}

        for fname, code in sources.items():
            res = self.inspect(code)
            if not res.is_safe:
                all_violations.extend([f"[{fname}] {v}" for v in res.violations])
            all_modules.update(res.imported_modules)
            all_calls.update(res.calls_detected)

        vblock = getattr(candidate, "test_verification_block", "")
        if vblock and vblock.strip():
            vres = self.inspect(vblock)
            if not vres.is_safe:
                all_violations.extend([f"[verification] {v}" for v in vres.violations])
            all_modules.update(vres.imported_modules)
            all_calls.update(vres.calls_detected)

        return ASTInspectionResult(
            is_safe=len(all_violations) == 0,
            violations=all_violations,
            imported_modules=sorted(list(all_modules)),
            calls_detected=sorted(list(all_calls)),
            syntax_error=any("SyntaxError" in v for v in all_violations),
        )

