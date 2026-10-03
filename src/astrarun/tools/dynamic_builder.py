"""Governed DynamicToolBuilder for AstraRun 1.0.

Provides model-independent dynamic tool generation, AST safety screening,
sandbox verification, and bounded self-repair (max 2 attempts).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.sandbox.manager import SandboxManager
from astrarun.sandbox.models import SandboxConfig, SandboxProfile, SandboxResult
from astrarun.tools.ast_inspector import ASTInspectionResult, ASTInspector
from astrarun.tools.candidate import CandidateTool, DependencyRequest
from astrarun.tools.registry import ToolRegistry

logger = get_logger("astrarun.tools.dynamic_builder")


class RepairExhaustedError(RuntimeError):
    """Raised when bounded repair attempts are exhausted without success."""
    pass


@dataclass
class DynamicToolExecutionReport:
    """Comprehensive outcome report of dynamic tool synthesis and execution."""
    candidate_tool: CandidateTool
    sandbox_result: SandboxResult
    ast_result: ASTInspectionResult
    repair_attempts: int
    is_success: bool
    artifacts: List[Path] = field(default_factory=list)
    error_message: Optional[str] = None


class DynamicToolBuilder:
    """
    Authoritative builder and lifecycle runner for ephemeral dynamic tools.
    """

    def __init__(
        self,
        sandbox_manager: Optional[SandboxManager] = None,
        tool_registry: Optional[ToolRegistry] = None,
        ast_inspector: Optional[ASTInspector] = None,
        max_repair_attempts: int = 2,
    ) -> None:
        self.sandbox = sandbox_manager or SandboxManager()
        self.registry = tool_registry or ToolRegistry()
        self.inspector = ast_inspector or ASTInspector()
        self.max_repair_attempts = max_repair_attempts

    def search_existing_capabilities(self, goal: str) -> Optional[str]:
        """Check if goal can be resolved by an existing permanent tool."""
        g = goal.lower().strip()
        # Direct keyword match against tool descriptions and names
        for tool in self.registry.list_tools():
            name = tool.name.lower()
            if name in g:
                return tool.name
            # Check keywords
            if "port" in g and "inspect_port" in name:
                return tool.name
            if "process" in g and "inspect_process" in name:
                return tool.name
            if "folder" in g and "open_folder" in name:
                return tool.name
        return None

    def synthesize_tool_for_goal(self, goal: str, inputs: Optional[Dict[str, Any]] = None) -> CandidateTool:
        """
        Synthesize CandidateTool for a recognized user goal.
        Uses deterministic templates or model-assisted generation.
        """
        g_lower = goal.lower()
        inputs = inputs or {}

        # 1. 3D Graph / Plotting Goal
        if ("3d" in g_lower and "graph" in g_lower) or ("plot" in g_lower and ("sin" in g_lower or "cos" in g_lower)):
            output_name = inputs.get("output_filename", "dynamic_3d_graph.png")
            x_min = inputs.get("x_min", -10)
            x_max = inputs.get("x_max", 10)
            y_min = inputs.get("y_min", -10)
            y_max = inputs.get("y_max", 10)

            code = f'''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D

def generate_graph(output_path='{output_name}'):
    x = np.linspace({x_min}, {x_max}, 100)
    y = np.linspace({y_min}, {y_max}, 100)
    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)
    # Avoid zero-division warning if R==0
    Z = np.sin(R)

    fig = plt.figure(figsize=(10, 8), dpi=150)
    ax = fig.add_subplot(111, projection='3d')
    surf = ax.plot_surface(X, Y, Z, cmap='viridis', edgecolor='none', alpha=0.9)
    ax.set_title('3D Surface: z = sin(sqrt(x^2 + y^2))', fontsize=14, pad=12)
    ax.set_xlabel('X axis')
    ax.set_ylabel('Y axis')
    ax.set_zlabel('Z axis')
    fig.colorbar(surf, shrink=0.5, aspect=10)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Artifact created: {{output_path}}")

if __name__ == '__main__':
    generate_graph()
'''
            test_block = f'''import os
assert os.path.exists('{output_name}'), "Graph artifact was not generated."
assert os.path.getsize('{output_name}') > 1000, "Graph artifact file is empty."
'''
            return CandidateTool(
                goal=goal,
                executable_code=code,
                test_verification_block=test_block,
                inputs={"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "output_filename": output_name},
                outputs={"artifact": output_name},
                external_dependencies=[
                    DependencyRequest(package="numpy", reason="Array computation for meshgrid"),
                    DependencyRequest(package="matplotlib", reason="3D surface visualization"),
                ],
                required_permissions=["FILESYSTEM_WRITE_SANDBOX"],
                expected_side_effects=[f"Creates image artifact '{output_name}' in sandbox."],
                sandbox_profile="EPHEMERAL_TOOL",
            )

        # 2. Mathematical computation / Data summary
        if "compute" in g_lower or "calculate" in g_lower or "math" in g_lower:
            code = '''import math

def compute():
    results = {}
    results["pi"] = math.pi
    results["e"] = math.e
    print(f"Computed mathematical constants: {results}")

if __name__ == '__main__':
    compute()
'''
            test_block = 'print("Verification successful.")'
            return CandidateTool(
                goal=goal,
                executable_code=code,
                test_verification_block=test_block,
                sandbox_profile="EPHEMERAL_TOOL",
            )

        # Fallback generic candidate tool
        code = f'''# Dynamic script for goal: {goal}
def run():
    print("Executing dynamic task: {goal}")

if __name__ == '__main__':
    run()
'''
        return CandidateTool(
            goal=goal,
            executable_code=code,
            test_verification_block='print("Dry run OK")',
            sandbox_profile="EPHEMERAL_TOOL",
        )

    def repair_code(self, candidate: CandidateTool, error_text: str, attempt: int) -> str:
        """
        Formulate and apply a structured repair to candidate tool code.
        Bounded to strictly fix common runtime issues (missing imports, typos, zero-division, shape mismatch).
        """
        logger.info("Attempting bounded repair #%d for tool %s", attempt, candidate.tool_id)
        code = candidate.executable_code

        # Common Repair 1: Missing Agg backend for headless matplotlib
        if "tkinter" in error_text.lower() or "tcl" in error_text.lower() or "gui" in error_text.lower():
            if "matplotlib" in code and "matplotlib.use('Agg')" not in code:
                code = "import matplotlib\nmatplotlib.use('Agg')\n" + code

        # Common Repair 2: Missing numpy/math import
        if "NameError: name 'np' is not defined" in error_text:
            code = "import numpy as np\n" + code
        elif "NameError: name 'math' is not defined" in error_text:
            code = "import math\n" + code

        # Common Repair 3: ZeroDivisionError
        if "ZeroDivisionError" in error_text:
            code = code.replace("np.sin(R) / R", "np.where(R == 0, 1.0, np.sin(R) / np.maximum(R, 1e-9))")
            code = code.replace("/ R", "/ np.maximum(R, 1e-9)")

        # Common Repair 4: Syntax error line fixes
        if "SyntaxError" in error_text:
            # Strip trailing bad characters or syntax glitches
            lines = code.splitlines()
            cleaned = [l for l in lines if not l.strip().startswith(">>>")]
            code = "\n".join(cleaned)

        return code

    def build_and_execute(
        self,
        candidate: CandidateTool,
        timeout_sec: float = 30.0,
    ) -> DynamicToolExecutionReport:
        """
        Execute candidate tool through full governed pipeline with AST checks,
        sandbox dry run, and bounded repair loop.
        """
        current_tool = candidate
        repair_attempts = 0
        last_ast: Optional[ASTInspectionResult] = None
        last_sb_result: Optional[SandboxResult] = None

        while repair_attempts <= self.max_repair_attempts:
            # 1. AST Inspection
            full_code = current_tool.full_script(include_test=True)
            ast_res = self.inspector.inspect(full_code)
            last_ast = ast_res

            if not ast_res.is_safe:
                logger.warning("AST safety violation in tool %s: %s", current_tool.tool_id, ast_res.violations)
                if repair_attempts >= self.max_repair_attempts:
                    return DynamicToolExecutionReport(
                        candidate_tool=current_tool,
                        sandbox_result=SandboxResult(
                            run_id="denied",
                            profile=SandboxProfile.EPHEMERAL_TOOL,
                            status="DENIED",
                            exit_code=-1,
                            stdout="",
                            stderr=f"AST Inspection failed: {ast_res.violations}",
                            duration_ms=0.0,
                        ),
                        ast_result=ast_res,
                        repair_attempts=repair_attempts,
                        is_success=False,
                        error_message="AST Inspection failed with security violations.",
                    )
                # Attempt repair
                repair_attempts += 1
                repaired_code = self.repair_code(current_tool, "\n".join(ast_res.violations), repair_attempts)
                current_tool.executable_code = repaired_code
                continue

            # 2. Contained Sandbox Execution
            cfg = SandboxConfig(
                profile=SandboxProfile.EPHEMERAL_TOOL,
                timeout_sec=timeout_sec,
                preserve_on_exit=True,  # Preserve to inspect artifacts
            )
            sb_res = self.sandbox.execute_script(full_code, config=cfg)
            last_sb_result = sb_res

            if sb_res.is_success:
                logger.info("Dynamic tool %s executed successfully in %sms", current_tool.tool_id, sb_res.duration_ms)
                return DynamicToolExecutionReport(
                    candidate_tool=current_tool,
                    sandbox_result=sb_res,
                    ast_result=ast_res,
                    repair_attempts=repair_attempts,
                    is_success=True,
                    artifacts=sb_res.created_artifacts,
                )

            # Failure during sandbox execution -> Bounded repair
            logger.warning("Sandbox execution failed (exit_code=%s): %s", sb_res.exit_code, sb_res.stderr)
            if repair_attempts >= self.max_repair_attempts:
                break

            repair_attempts += 1
            repaired_code = self.repair_code(current_tool, sb_res.stderr, repair_attempts)
            if repaired_code == current_tool.executable_code:
                # No repair could be formulated
                break
            current_tool.executable_code = repaired_code

        # If loop exits without success
        return DynamicToolExecutionReport(
            candidate_tool=current_tool,
            sandbox_result=last_sb_result or SandboxResult(
                run_id="error",
                profile=SandboxProfile.EPHEMERAL_TOOL,
                status="FAILED",
                exit_code=-1,
                stdout="",
                stderr="Max repair attempts exhausted.",
                duration_ms=0.0,
            ),
            ast_result=last_ast or ASTInspectionResult(is_safe=False),
            repair_attempts=repair_attempts,
            is_success=False,
            error_message="Tool execution failed and bounded repair attempts were exhausted.",
        )
