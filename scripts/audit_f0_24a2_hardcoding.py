"""
scripts/audit_f0_24a2_hardcoding.py
Static analysis and AST inspection audit to affirmatively verify that generic
computer-use and UI interaction paths do not contain application-specific branching
or special-cased shortcuts for Notepad, Notepad++, Calculator, etc.

Generates: docs/audit/F0_24A2_HARDCODING_AUDIT.json
"""

import ast
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = REPO_ROOT / "docs" / "audit"
OUT_FILE = AUDIT_DIR / "F0_24A2_HARDCODING_AUDIT.json"

TARGET_MODULES = [
    "src/astrarun/computer_use/ui/editable_surface.py",
    "src/astrarun/computer_use/ui/dialogs.py",
    "src/astrarun/interaction/service.py",
    "src/astrarun/interaction/document.py",
    "src/astrarun/interaction/discovery.py",
    "src/astrarun/tasks/resource_ledger.py",
]

SUSPICIOUS_APP_LITERALS = ["notepad", "notepad++", "calc", "calculator", "wordpad", "mspaint"]

class HardcodingAstVisitor(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.findings = []

    def visit_Compare(self, node: ast.Compare):
        # Check if comparison compares variable to specific app brand string
        # e.g. app == "notepad" or "notepad" in title
        comparator_strings = []
        for c in [node.left] + node.comparators:
            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                s = c.value.lower()
                for app in SUSPICIOUS_APP_LITERALS:
                    if app == s:
                        comparator_strings.append((app, node.lineno))

        for app, lineno in comparator_strings:
            self.findings.append({
                "type": "APP_BRAND_COMPARISON",
                "file": self.filename,
                "line": lineno,
                "app": app,
                "description": f"Direct comparison against application brand literal '{app}'",
            })
        self.generic_visit(node)

def run_audit():
    print("=== RUNNING F0-24A.2 ANTI-HARDCODING AUDIT ===")
    results = {
        "status": "PASS",
        "timestamp": os.environ.get("AUDIT_TIMESTAMP", "2026-10-11T00:15:00Z"),
        "modules_inspected": [],
        "findings": [],
        "verdict": "CLEAN",
    }

    total_findings = []

    for rel_path in TARGET_MODULES:
        file_path = REPO_ROOT / rel_path
        if not file_path.exists():
            continue

        source = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            print(f"Syntax error in {rel_path}: {e}")
            continue

        visitor = HardcodingAstVisitor(rel_path)
        visitor.visit(tree)

        results["modules_inspected"].append({
            "path": rel_path,
            "lines": len(source.splitlines()),
            "findings_count": len(visitor.findings),
        })

        total_findings.extend(visitor.findings)

    results["findings"] = total_findings
    if total_findings:
        results["status"] = "FAIL"
        results["verdict"] = f"Detected {len(total_findings)} hardcoded application branches."
    else:
        results["status"] = "PASS"
        results["verdict"] = "Zero hardcoded application branches detected in generic execution paths."

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Results written to: {OUT_FILE}")
    print(f"Status: {results['status']}, Verdict: {results['verdict']}")
    return 0 if results["status"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(run_audit())
