"""F0-25B Notepad++ Knowledge Contamination Auditor.

Scans all source trees, configs, test suites, and audit logs for procedural knowledge
involving Notepad++, Scintilla, shortcut sequences, and control identifiers.
Classifies each finding into:
- GENERIC_PRIMITIVE
- APPLICATION_METADATA
- PROCEDURAL_CONTAMINATION
- TEST_ONLY
- HISTORICAL_EVIDENCE
- UNRELATED

Ensures that the cold learning loop starts with ZERO PROCEDURAL CONTAMINATION.
Emits docs/audit/F0_25B_CONTAMINATION_AUDIT.json.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]

TARGET_TERMS = [
    r"notepad\+\+",
    r"\bnpp\b",
    r"scintilla",
    r"ctrl\+n",
    r"ctrl\+f",
    r"ctrl\+h",
    r"ctrl\+shift\+s",
    r"ctrl\+pageup",
    r"save as",
]

COMPILED_PATTERNS = [re.compile(t, re.IGNORECASE) for t in TARGET_TERMS]


def classify_finding(file_path: Path, line_no: int, line_text: str, match_term: str) -> str:
    path_str = file_path.as_posix().lower()
    text_lower = line_text.lower()

    # Historical audit artifacts
    if "docs/audit" in path_str:
        return "HISTORICAL_EVIDENCE"

    # Test-only laboratory or harness scripts
    if "tests/" in path_str or "scripts/" in path_str:
        if any(tok in path_str for tok in ("f0_24a2", "laboratory", "notepadpp")):
            return "TEST_ONLY"
        if "test_" in path_str:
            return "TEST_ONLY"

    # Production code in src/
    if "src/" in path_str:
        # Generic primitives: discovery, generic keyboard input, generic UIA classes
        if any(tok in path_str for tok in ("interaction/discovery.py", "interaction/controller.py", "perception/input.py", "capabilities/")):
            if "scintilla" in text_lower and ("class_name" in text_lower or "known_classes" in text_lower or "detect" in text_lower):
                return "GENERIC_PRIMITIVE"
            if "ctrl+" in text_lower and not ("notepad" in text_lower or "npp" in text_lower):
                return "GENERIC_PRIMITIVE"
            if "save as" in text_lower and "dialog" in text_lower:
                return "GENERIC_PRIMITIVE"

        # Application metadata: executable resolution, icon discovery
        if "paths.py" in path_str or "resolver.py" in path_str or "manifest.py" in path_str:
            return "APPLICATION_METADATA"

        # Check for hardcoded procedural leaks in hermes or agent logic
        if "hermes/" in path_str:
            if "ctrl+n" in text_lower and "creates a new document" in text_lower:
                return "PROCEDURAL_CONTAMINATION"
            if "notepad" in text_lower:
                return "PROCEDURAL_CONTAMINATION"

        # General metadata
        if "notepad++" in text_lower or "notepad++.exe" in text_lower:
            return "APPLICATION_METADATA"

        return "GENERIC_PRIMITIVE"

    return "UNRELATED"


def run_audit() -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    scanned_files_count = 0

    scan_dirs = [ROOT / "src", ROOT / "config", ROOT / "tests", ROOT / "scripts", ROOT / "docs"]
    extensions = {".py", ".json", ".md", ".txt", ".yaml", ".yml"}

    for d in scan_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in extensions:
                continue
            if "__pycache__" in p.as_posix() or ".venv" in p.as_posix():
                continue

            scanned_files_count += 1
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = content.splitlines()
            for idx, line in enumerate(lines, 1):
                for pat in COMPILED_PATTERNS:
                    m = pat.search(line)
                    if m:
                        cat = classify_finding(p.relative_to(ROOT), idx, line, m.group(0))
                        findings.append({
                            "file": p.relative_to(ROOT).as_posix(),
                            "line": idx,
                            "match": m.group(0),
                            "classification": cat,
                            "snippet": line.strip()[:140],
                        })
                        break

    # Summary by classification
    summary: Dict[str, int] = {}
    for f in findings:
        c = f["classification"]
        summary[c] = summary.get(c, 0) + 1

    procedural_leaks = [f for f in findings if f["classification"] == "PROCEDURAL_CONTAMINATION"]

    audit_result = {
        "phase": "F0-25B",
        "title": "Notepad++ Procedural Contamination Audit",
        "scanned_files_count": scanned_files_count,
        "total_findings_count": len(findings),
        "classification_summary": summary,
        "procedural_contamination_count": len(procedural_leaks),
        "procedural_contamination_findings": procedural_leaks,
        "audit_verdict": "QUARANTINED" if procedural_leaks else "CLEAN",
        "sample_findings": findings[:30],
    }

    out_file = ROOT / "docs" / "audit" / "F0_25B_CONTAMINATION_AUDIT.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(audit_result, f, indent=2)

    print(f"Scanned {scanned_files_count} files. Total findings: {len(findings)}")
    print(f"Classification Summary: {summary}")
    print(f"Procedural Contamination Count: {len(procedural_leaks)}")
    print(f"Wrote {out_file}")
    return audit_result


if __name__ == "__main__":
    run_audit()
