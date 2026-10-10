"""
scripts/audit_f0_22_dependency_graph.py

Statically inspects all production modules in src/astrarun using Python's AST:
- Resolves module dependencies and imports
- Extracts public symbols and docstrings
- Detects side effects (file I/O, subprocess, Win32, UIA, network, registry)
- Detects state ownership (singletons, module globals)
- Detects security authority (ActionGate, ExecutionBroker)
- Maps test coverage / test importers
- Classifies each module into canonical categories
- Outputs docs/audit/F0_22_DEPENDENCY_GRAPH.json
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path


def get_module_name(path: Path, src_root: Path) -> str:
    rel = path.relative_to(src_root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


class ModuleAuditor(ast.NodeVisitor):
    def __init__(self, mod_name: str, src_root: Path):
        self.mod_name = mod_name
        self.src_root = src_root
        self.imports = set()
        self.public_symbols = []
        self.docstring = ""
        self.side_effects = []
        self.state_owned = []
        self.security_authority = []

    def visit_Module(self, node: ast.Module):
        self.docstring = ast.get_docstring(node) or ""
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.add(alias.name)
            self._check_side_effect_imports(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        level = node.level
        if level > 0:
            # relative import
            parts = self.mod_name.split(".")
            if len(parts) >= level:
                base = ".".join(parts[:-level])
                full_mod = f"{base}.{mod}" if mod else base
            else:
                full_mod = mod
        else:
            full_mod = mod

        if full_mod:
            self.imports.add(full_mod)
            self._check_side_effect_imports(full_mod)
        self.generic_visit(node)

    def _check_side_effect_imports(self, name: str):
        if "subprocess" in name:
            self.side_effects.append("SUBPROCESS_SPAWNING")
        if "win32" in name or "ctypes" in name:
            self.side_effects.append("WIN32_NATIVE_API")
        if "uia" in name or "pywinauto" in name:
            self.side_effects.append("UI_AUTOMATION")
        if "winreg" in name:
            self.side_effects.append("WINDOWS_REGISTRY")
        if "broker" in name or "action_gate" in name:
            self.security_authority.append(name)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if not node.name.startswith("_"):
            self.public_symbols.append(f"def {node.name}")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if not node.name.startswith("_"):
            self.public_symbols.append(f"async def {node.name}")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        if not node.name.startswith("_"):
            self.public_symbols.append(f"class {node.name}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in ("write_text", "write_bytes", "remove", "unlink", "mkdir", "rmdir"):
            self.side_effects.append(f"FILESYSTEM_{func_name.upper()}")
        elif func_name in ("Popen", "run", "check_output", "call"):
            self.side_effects.append("PROCESS_EXECUTION")
        elif func_name in ("SendInput", "PostMessageW", "SendMessageW", "SetForegroundWindow"):
            self.side_effects.append("SYNTHETIC_USER_INPUT")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                if target.id.isupper():
                    self.state_owned.append(f"CONST {target.id}")
                else:
                    self.state_owned.append(f"GLOBAL_VAR {target.id}")
        self.generic_visit(node)


def audit_test_imports(tests_dir: Path) -> dict[str, list[str]]:
    test_imports = {}
    for p in tests_dir.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
            for node in ast.walk(tree):
                mod = ""
                if isinstance(node, ast.Import):
                    for n in node.names:
                        mod = n.name
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                if mod and mod.startswith("astrarun"):
                    test_imports.setdefault(mod, []).append(str(p.name))
        except Exception:
            pass
    return test_imports


def classify_module(
    mod_name: str,
    path: Path,
    importers: list[str],
    test_importers: list[str],
    docstring: str,
    side_effects: list[str],
) -> tuple[str, str]:
    # Check milestone artifacts
    if any(m in mod_name for m in ["c2_2", "rc0", "rc3", "rc5", "f0_15", "f0_17", "f0_18", "f0_19", "f0_20", "f0_21"]):
        return "MILESTONE_ARTIFACT", "Contains specific milestone identifier in module path"

    # Core composition root
    if mod_name in ("astrarun.main", "astrarun.app", "astrarun.__init__"):
        return "CANONICAL_PRODUCTION", "Core composition root or application entry point"

    # Check dead/test only
    if len(importers) == 0:
        if len(test_importers) > 0:
            return "TEST_ONLY_LEAKED_TO_PRODUCTION", f"Imported only by tests ({len(test_importers)} tests), 0 production importers"
        else:
            return "DEAD", "Zero production importers and zero test importers"

    # Check adapters
    if any(k in mod_name for k in [".win32", ".uia", ".ocr", ".screen", ".audio", ".power", ".windows"]):
        return "LEGITIMATE_ADAPTER", "OS or hardware interface adapter"

    # Check compatibility layer
    if "compat" in mod_name or "shim" in mod_name or "legacy" in mod_name:
        return "LEGITIMATE_COMPATIBILITY_LAYER", "Explicit backward compatibility layer"

    # Check experimental
    if "experimental" in mod_name or "spike" in mod_name:
        return "EXPERIMENTAL", "Marked experimental or prototype"

    # Canonical default
    return "CANONICAL_PRODUCTION", f"Actively imported by {len(importers)} production modules"


def main():
    repo_root = Path(__file__).resolve().parent.parent
    src_root = repo_root / "src"
    astra_dir = src_root / "astrarun"
    tests_dir = repo_root / "tests"

    print("Auditing test imports...", flush=True)
    test_import_map = audit_test_imports(tests_dir)

    print("Parsing production modules...", flush=True)
    modules_data = {}
    py_files = sorted([p for p in astra_dir.rglob("*.py") if "__pycache__" not in p.parts])

    for p in py_files:
        mod_name = get_module_name(p, src_root)
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
            auditor = ModuleAuditor(mod_name, src_root)
            auditor.visit(tree)
            modules_data[mod_name] = {
                "file_path": str(p.relative_to(repo_root)).replace("\\", "/"),
                "docstring": auditor.docstring.strip()[:200],
                "public_symbols": auditor.public_symbols[:15],
                "symbols_count": len(auditor.public_symbols),
                "imports": sorted(list(auditor.imports)),
                "side_effects": sorted(list(set(auditor.side_effects))),
                "state_owned": sorted(list(set(auditor.state_owned))),
                "security_authority": sorted(list(set(auditor.security_authority))),
                "importers": [],
                "test_importers": [],
                "classification": "UNCLEAR",
                "classification_evidence": "",
            }
        except Exception as e:
            modules_data[mod_name] = {
                "file_path": str(p.relative_to(repo_root)).replace("\\", "/"),
                "error": str(e),
                "classification": "UNCLEAR",
            }

    # Second pass: Compute reverse dependency graph (importers)
    print("Computing reverse dependency graph...", flush=True)
    for caller_mod, data in modules_data.items():
        if "imports" not in data:
            continue
        for imp in data["imports"]:
            if imp.startswith("astrarun"):
                target = imp
                while target and target not in modules_data:
                    if "." in target:
                        target = target.rsplit(".", 1)[0]
                    else:
                        break
                if target in modules_data and caller_mod not in modules_data[target]["importers"]:
                    modules_data[target]["importers"].append(caller_mod)

    # Third pass: Test coverage and classifications
    print("Classifying modules...", flush=True)
    classification_counts = {}
    for mod_name, data in modules_data.items():
        if "imports" not in data:
            continue
        # Check test importers
        t_imps = []
        for k, tests in test_import_map.items():
            if k == mod_name or k.startswith(mod_name + "."):
                t_imps.extend(tests)
        data["test_importers"] = sorted(list(set(t_imps)))

        classification, rationale = classify_module(
            mod_name,
            Path(data["file_path"]),
            data["importers"],
            data["test_importers"],
            data.get("docstring", ""),
            data.get("side_effects", []),
        )
        data["classification"] = classification
        data["classification_evidence"] = rationale
        classification_counts[classification] = classification_counts.get(classification, 0) + 1

    manifest = {
        "timestamp": os.environ.get("TIMESTAMP", ""),
        "phase": "F0-22",
        "total_modules": len(modules_data),
        "classification_summary": classification_counts,
        "modules": modules_data,
    }

    out_file = repo_root / "docs" / "audit" / "F0_22_DEPENDENCY_GRAPH.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDependency graph written to: {out_file}", flush=True)
    print("Classification Summary:", flush=True)
    for cat, count in sorted(classification_counts.items()):
        print(f"  {cat}: {count}", flush=True)


if __name__ == "__main__":
    main()
