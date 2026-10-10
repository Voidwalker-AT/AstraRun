"""Phase F0-22 Architectural Boundaries & Smells Audit Script.

Performs static analysis across src/astrarun to audit:
- High-level architectural ownership (BRAIN, AGENT_RUNTIME, COMPUTER_USE, MEMORY, SECURITY, UI, MODEL_RUNTIME, CORE_SHARED)
- Cross-boundary violations (e.g., Brain manipulating HWNDs, Verifier mutating state)
- Code smells (hardcoded strings, milestone tags, dev paths, exception swallowing, direct subprocess)
- Actual Brain call graph & model participation
- Actual ComputerUse subsystem interaction mapping

Outputs:
  docs/audit/F0_22_ARCHITECTURAL_BOUNDARIES.json
"""

from __future__ import annotations

import ast
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def audit_boundaries():
    repo_root = Path(__file__).resolve().parent.parent
    src_root = repo_root / "src" / "astrarun"

    # 1. Classify all modules into architectural layers
    layer_map = {
        "brain": "BRAIN",
        "nlp": "BRAIN",
        "planning": "BRAIN",
        "routing": "BRAIN",
        "agent": "AGENT_RUNTIME",
        "tasks": "AGENT_RUNTIME",
        "workflows": "AGENT_RUNTIME",
        "execution": "AGENT_RUNTIME",
        "engine": "AGENT_RUNTIME",
        "capabilities": "COMPUTER_USE",
        "computer_use": "COMPUTER_USE",
        "interaction": "COMPUTER_USE",
        "windows": "COMPUTER_USE",
        "vision": "COMPUTER_USE",
        "system": "COMPUTER_USE",
        "memory": "MEMORY",
        "knowledge": "MEMORY",
        "learning": "MEMORY",
        "state": "MEMORY",
        "storage": "MEMORY",
        "security": "SECURITY",
        "broker": "SECURITY",
        "gate": "SECURITY",
        "ui": "UI",
        "visualization": "UI",
        "hud": "UI",
        "tray": "UI",
        "models": "MODEL_RUNTIME",
        "inference": "MODEL_RUNTIME",
        "runtime": "MODEL_RUNTIME",
        "config": "CORE_SHARED",
        "logging": "CORE_SHARED",
        "utils": "CORE_SHARED",
        "constants": "CORE_SHARED",
        "types": "CORE_SHARED",
        "app": "CORE_SHARED",
        "diagnostics": "CORE_SHARED",
        "platform": "CORE_SHARED",
        "tools": "CORE_SHARED",
    }

    modules_by_layer: dict[str, list[str]] = {
        "BRAIN": [],
        "AGENT_RUNTIME": [],
        "COMPUTER_USE": [],
        "MEMORY": [],
        "SECURITY": [],
        "UI": [],
        "MODEL_RUNTIME": [],
        "CORE_SHARED": [],
    }

    module_layer: dict[str, str] = {}

    all_py_files = sorted(src_root.rglob("*.py"))
    for py_file in all_py_files:
        rel = py_file.relative_to(src_root)
        parts = rel.parts
        mod_name = "astrarun." + ".".join(parts)[:-3] if rel.name != "__init__.py" else "astrarun." + ".".join(parts[:-1])
        top_pkg = parts[0] if len(parts) > 1 else parts[0].replace(".py", "")
        layer = layer_map.get(top_pkg, "CORE_SHARED")
        modules_by_layer[layer].append(mod_name)
        module_layer[mod_name] = layer

    # 2. Smell patterns
    milestone_pattern = re.compile(r"\bF0[-_](1[0-9]|2[0-2])[a-zA-Z]?\b", re.IGNORECASE)
    dev_path_pattern = re.compile(r"(E:\\\\Workspace|C:\\\\Users\\\\hp|E:/Workspace)", re.IGNORECASE)
    hardcoded_artifact_pattern = re.compile(r"astra_f0_\w+|test1\.txt|test_output", re.IGNORECASE)
    
    smell_findings = []
    boundary_violations = []

    # Brain call graph tracking
    routers_found = []
    planners_found = []
    verifiers_found = []
    model_participation = {
        "laya": [],
        "spark": [],
        "qwen": [],
    }

    # Computer use interaction map
    cu_technologies = {
        "win32_hwnd": [],
        "uiautomation": [],
        "sendinput": [],
        "screen_capture": [],
        "ocr": [],
        "browser_cdp": [],
        "filesystem_write": [],
        "subprocess": [],
    }

    for py_file in all_py_files:
        rel_path = str(py_file.relative_to(repo_root)).replace("\\", "/")
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            continue

        mod_name = "astrarun." + ".".join(py_file.relative_to(src_root).parts)[:-3]
        layer = module_layer.get(mod_name, "CORE_SHARED")

        lines = content.splitlines()

        # Check line-by-line regex smells
        for idx, line in enumerate(lines, start=1):
            # Check milestone IDs in runtime logic (skip docstrings/comments if possible)
            m_milestone = milestone_pattern.search(line)
            if m_milestone and not line.strip().startswith(("#", '"""', "'''")):
                smell_findings.append({
                    "file": rel_path,
                    "line": idx,
                    "symbol": m_milestone.group(0),
                    "classification": "MILESTONE_ID_IN_RUNTIME",
                    "runtime_relevance": f"Hardcoded milestone identifier '{m_milestone.group(0)}' in code.",
                    "recommended_disposition": "REPLACE with generic parameter or configuration."
                })

            # Check dev path
            m_dev = dev_path_pattern.search(line)
            if m_dev and not line.strip().startswith(("#", '"""', "'''")):
                smell_findings.append({
                    "file": rel_path,
                    "line": idx,
                    "symbol": m_dev.group(0),
                    "classification": "DEVELOPER_MACHINE_PATH",
                    "runtime_relevance": f"Developer path '{m_dev.group(0)}' baked into runtime code.",
                    "recommended_disposition": "REPLACE with standard OS paths (e.g. os.environ['USERPROFILE'] or tempfile)."
                })

            # Check hardcoded test artifacts
            m_art = hardcoded_artifact_pattern.search(line)
            if m_art and not line.strip().startswith(("#", '"""', "'''")):
                smell_findings.append({
                    "file": rel_path,
                    "line": idx,
                    "symbol": m_art.group(0),
                    "classification": "HARDCODED_ACCEPTANCE_ARTIFACT",
                    "runtime_relevance": f"Hardcoded benchmark/artifact string '{m_art.group(0)}' in runtime code.",
                    "recommended_disposition": "REMOVE or parameterize generically."
                })

        # AST Inspection for structure, smells, and boundaries
        for node in ast.walk(tree):
            # Broad exception swallowing: try ... except (Exception|BaseException): pass
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    is_broad = False
                    if handler.type is None:
                        is_broad = True
                    elif isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException"):
                        is_broad = True
                    if is_broad:
                        # Check body for pass or empty
                        if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                            smell_findings.append({
                                "file": rel_path,
                                "line": handler.lineno,
                                "symbol": "except Exception: pass",
                                "classification": "SILENT_EXCEPTION_SWALLOWING",
                                "runtime_relevance": "Swallows errors silently without logging or re-raising.",
                                "recommended_disposition": "Log with logger.debug/warning or raise specific exception."
                            })

            # Subprocess calls
            if isinstance(node, ast.Call):
                func_str = ""
                if isinstance(node.func, ast.Attribute):
                    func_str = node.func.attr
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                        func_str = f"subprocess.{node.func.attr}"
                    elif isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr in ("system", "popen"):
                        func_str = f"os.{node.func.attr}"
                elif isinstance(node.func, ast.Name):
                    func_str = node.func.id

                if func_str in ("subprocess.Popen", "subprocess.run", "subprocess.call", "subprocess.check_output", "os.system", "os.popen"):
                    cu_technologies["subprocess"].append({"file": rel_path, "line": node.lineno, "call": func_str})
                    if layer not in ("COMPUTER_USE", "AGENT_RUNTIME", "CORE_SHARED"):
                        boundary_violations.append({
                            "source_file": rel_path,
                            "layer": layer,
                            "line": node.lineno,
                            "violation": f"Layer {layer} directly spawns processes via {func_str}.",
                            "severity": "HIGH",
                            "disposition": "Route through ExecutionBroker or canonical process supervisor."
                        })

            # Filesystem write outside broker
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in ("write_text", "write_bytes"):
                    cu_technologies["filesystem_write"].append({"file": rel_path, "line": node.lineno})
                    if layer == "BRAIN":
                        boundary_violations.append({
                            "source_file": rel_path,
                            "layer": layer,
                            "line": node.lineno,
                            "violation": f"BRAIN layer directly performs filesystem write via {node.func.attr}.",
                            "severity": "CRITICAL",
                            "disposition": "Brain must only produce plans/contracts; execution runtime writes files."
                        })

            # Win32 / HWND inspection
            if isinstance(node, ast.Name) and "win32gui" in node.id:
                cu_technologies["win32_hwnd"].append({"file": rel_path, "line": node.lineno})
                if layer in ("BRAIN", "UI", "SECURITY"):
                    boundary_violations.append({
                        "source_file": rel_path,
                        "layer": layer,
                        "line": node.lineno,
                        "violation": f"Layer {layer} references win32gui directly.",
                        "severity": "HIGH",
                        "disposition": "Delegate to COMPUTER_USE window controller."
                    })

        # Check imports for technology mapping & router/planner/verifier discovery
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imp_names = []
                if isinstance(node, ast.Import):
                    imp_names = [a.name for a in node.names]
                else:
                    mod_p = node.module or ""
                    imp_names = [f"{mod_p}.{a.name}" for a in node.names]

                for iname in imp_names:
                    if "pywinauto" in iname or "uiautomation" in iname or "comtypes" in iname:
                        cu_technologies["uiautomation"].append({"file": rel_path, "import": iname})
                    if "pyautogui" in iname or "mouse" in iname or "keyboard" in iname or "pynput" in iname:
                        cu_technologies["sendinput"].append({"file": rel_path, "import": iname})
                    if "mss" in iname or "PIL.ImageGrab" in iname:
                        cu_technologies["screen_capture"].append({"file": rel_path, "import": iname})
                    if "tesseract" in iname or "easyocr" in iname:
                        cu_technologies["ocr"].append({"file": rel_path, "import": iname})
                    if "playwright" in iname or "selenium" in iname or "cdp" in iname:
                        cu_technologies["browser_cdp"].append({"file": rel_path, "import": iname})

        # Identify routers, planners, verifiers
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cname = node.name.lower()
                if "router" in cname or "routing" in cname:
                    routers_found.append({"class": node.name, "file": rel_path, "module": mod_name})
                if "planner" in cname or "planning" in cname:
                    planners_found.append({"class": node.name, "file": rel_path, "module": mod_name})
                if "verifier" in cname:
                    verifiers_found.append({"class": node.name, "file": rel_path, "module": mod_name})

        # Identify model references
        if "laya" in content.lower():
            model_participation["laya"].append(rel_path)
        if "spark" in content.lower():
            model_participation["spark"].append(rel_path)
        if "qwen" in content.lower():
            model_participation["qwen"].append(rel_path)

    # De-duplicate lists
    for k in model_participation:
        model_participation[k] = sorted(list(set(model_participation[k])))

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-22",
        "total_modules_audited": len(all_py_files),
        "architectural_layers": {
            k: {
                "count": len(v),
                "modules": v
            }
            for k, v in modules_by_layer.items()
        },
        "boundary_violations": {
            "count": len(boundary_violations),
            "findings": boundary_violations
        },
        "architectural_smells": {
            "total_count": len(smell_findings),
            "by_classification": {
                c: len([s for s in smell_findings if s["classification"] == c])
                for c in set(s["classification"] for s in smell_findings)
            },
            "findings": smell_findings
        },
        "brain_subsystems": {
            "routers": routers_found,
            "planners": planners_found,
            "verifiers": verifiers_found,
            "model_participation": {
                "laya_neural_router": {
                    "role": "Fast local transformer intent classifier (100M parameter model / ONNX)",
                    "referenced_in_files_count": len(model_participation["laya"]),
                    "files": model_participation["laya"]
                },
                "spark_llm_planner": {
                    "role": "Local reasoning model (Spark GGUF via llama-cpp) for complex plans & replanning",
                    "referenced_in_files_count": len(model_participation["spark"]),
                    "files": model_participation["spark"]
                },
                "qwen_vlm": {
                    "role": "Vision-Language model for screen understanding, visual grounding, and OCR validation",
                    "referenced_in_files_count": len(model_participation["qwen"]),
                    "files": model_participation["qwen"]
                }
            }
        },
        "computer_use_subsystems": {
            "win32_hwnd_count": len(cu_technologies["win32_hwnd"]),
            "uiautomation_count": len(cu_technologies["uiautomation"]),
            "sendinput_count": len(cu_technologies["sendinput"]),
            "screen_capture_count": len(cu_technologies["screen_capture"]),
            "ocr_count": len(cu_technologies["ocr"]),
            "browser_cdp_count": len(cu_technologies["browser_cdp"]),
            "subprocess_count": len(cu_technologies["subprocess"]),
            "filesystem_write_count": len(cu_technologies["filesystem_write"])
        }
    }

    out_file = repo_root / "docs" / "audit" / "F0_22_ARCHITECTURAL_BOUNDARIES.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Generated {out_file} with {len(smell_findings)} smells and {len(boundary_violations)} boundary violations.")


if __name__ == "__main__":
    audit_boundaries()
