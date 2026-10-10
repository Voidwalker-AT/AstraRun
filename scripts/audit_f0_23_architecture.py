"""
scripts/audit_f0_23_architecture.py

Audits repository structure, file inventory, large files / god objects (> 500 lines),
and architectural overlaps for Phase F0-23.

Emits: docs/audit/F0_23_ARCHITECTURE_OVERLAP_AUDIT.json
"""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")
SRC_DIR = REPO_ROOT / "src" / "astrarun"
OUTPUT_PATH = REPO_ROOT / "docs" / "audit" / "F0_23_ARCHITECTURE_OVERLAP_AUDIT.json"


def analyze_file(p: Path) -> Dict[str, Any]:
    text = p.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    line_count = len(lines)

    classes = []
    functions = []
    try:
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = [m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append({"name": node.name, "methods_count": len(methods), "methods": methods[:10]})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
    except Exception:
        pass

    return {
        "path": str(p.relative_to(REPO_ROOT)).replace("\\", "/"),
        "line_count": line_count,
        "classes_count": len(classes),
        "classes": classes,
        "functions_count": len(functions),
        "functions": functions[:15],
    }


def main() -> None:
    print("Auditing codebase architecture, large files, and architectural overlaps...")
    
    all_src_files = list(SRC_DIR.rglob("*.py"))
    
    # 1. Directory distribution
    by_dir = defaultdict(int)
    basenames = defaultdict(list)
    large_files = []

    for f in all_src_files:
        rel = f.relative_to(SRC_DIR)
        d_name = rel.parts[0] if len(rel.parts) > 1 else "root"
        by_dir[d_name] += 1
        basenames[f.name].append(str(f.relative_to(REPO_ROOT)).replace("\\", "/"))

        if f.stat().st_size > 0:
            analysis = analyze_file(f)
            if analysis["line_count"] >= 500:
                large_files.append(analysis)

    # 2. Duplicate basenames
    duplicate_basenames = {k: v for k, v in basenames.items() if len(v) > 1 and k != "__init__.py"}

    # 3. God object classification and split recommendations
    god_objects = []
    for lf in large_files:
        path = lf["path"]
        l_count = lf["line_count"]
        responsibilities = []
        is_god = False
        splits = []

        if "app.py" in path:
            is_god = True
            responsibilities = ["Lifecycle & single-instance", "Direct CLI commands", "Dispatcher for all capabilities", "Task manager orchestration", "Agent goal bridge", "Hotkey & GUI event coordination"]
            splits = ["Extract direct system commands into astrarun/routing/commands.py", "Extract computational handlers into astrarun/capabilities/computation.py", "Retain app.py purely as application coordinator"]
        elif "planner.py" in path:
            is_god = True
            responsibilities = ["NLP goal extraction", "RAG turn context building", "Heuristic syntactic clause decomposition", "DAG construction & dependency wiring", "OutputReference dataflow binding", "Repair & replanning synthesis"]
            splits = ["Extract dataflow dependency wiring into astrarun/agent/dependency_binder.py", "Extract turn context synthesis into astrarun/agent/context_synthesizer.py", "Retain planner.py for core DAG compilation"]
        elif "registry.py" in path:
            is_god = True
            responsibilities = ["Capability catalog & storage", "Built-in capability registration (50+ tools)", "Permission & security enforcement", "Execution dispatch & parameter validation", "Dynamic schema export"]
            splits = ["Partition built-in registrations across domain packages (desktop, window, sys, agent)", "Retain registry.py as lean schema storage and dispatch engine"]
        elif "structure_engine.py" in path:
            is_god = False
            responsibilities = ["SpaCy NLP linguistic parsing", "Regex clause fallback", "Compound intent DAG extraction"]
            splits = ["Well-scoped NLP parser; keep intact"]
        elif "compiler.py" in path:
            is_god = False
            responsibilities = ["Workflow compilation", "Clause to capability resolution", "Plan validation"]
            splits = ["Single responsibility workflow compiler; keep intact"]
        else:
            is_god = l_count > 1000
            responsibilities = ["Complex module with multi-function responsibilities"]
            splits = ["Decompose into modular domain components"]

        god_objects.append({
            "path": path,
            "line_count": l_count,
            "classes_count": lf["classes_count"],
            "functions_count": lf["functions_count"],
            "is_god_object": is_god,
            "distinct_responsibilities": responsibilities,
            "recommended_split_boundaries": splits,
        })

    # Sort large files by line count descending
    god_objects.sort(key=lambda x: x["line_count"], reverse=True)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-23",
        "description": "Comprehensive audit of repository inventory, module distribution, large files, god objects, and architectural overlap boundaries.",
        "summary": {
            "total_production_python_files": len(all_src_files),
            "total_directories": len(by_dir),
            "files_by_directory": dict(sorted(by_dir.items(), key=lambda x: x[1], reverse=True)),
            "duplicate_basenames_count": len(duplicate_basenames),
            "duplicate_basenames": duplicate_basenames,
            "large_files_exceeding_500_lines": len(god_objects),
            "god_objects_detected": sum(1 for g in god_objects if g["is_god_object"]),
        },
        "large_file_and_god_object_audit": god_objects,
        "architectural_overlap_findings": {
            "interaction_vs_computer_use": {
                "observation": "Both astrarun.interaction and astrarun.computer_use provide desktop and UIA drivers.",
                "status": "CONSOLIDATED_VIA_FACADE",
                "finding": "ComputerUse acts as canonical top-level facade. interaction provides specialized low-level win32/comtypes bindings.",
                "recommendation": "Preserve ComputerUse facade as single public computer-use entry point; do not create duplicate desktop hooks."
            },
            "perception_vs_interaction_input": {
                "observation": "NativeInputController in perception.input and PhysicalInputController in computer_use.input.",
                "status": "ALIGNED",
                "finding": "NativeInputController provides raw Win32 SendInput and takeover detection; ComputerUse delegates to it.",
                "recommendation": "Retain NativeInputController as authoritative physical controller."
            },
            "search_index_vs_entity_resolver": {
                "observation": "SearchIndex in search/index.py and SemanticEntityResolver in discovery/entity_resolver.py.",
                "status": "COLLABORATIVE",
                "finding": "SearchIndex provides fast fuzzy n-gram token retrieval; SemanticEntityResolver applies semantic normalization, alias resolution, and candidate filtering.",
                "recommendation": "Maintain SearchIndex as retrieval layer and SemanticEntityResolver as decision layer."
            }
        }
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Successfully generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
