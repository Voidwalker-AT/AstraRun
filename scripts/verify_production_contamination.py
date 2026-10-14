r"""Audit script for F0-25F.3 Stage 8: Production Benchmark & Path Contamination.

Searches all files in src/ for forbidden tokens:
- REPAIR-02
- historical fixture prompts (e.g. 'No timestamp available')
- test tokens (factorial_result, MATHEMATICALLY_VERIFIED, 3628800, F0_25*)
- workspace paths (E:\Workspace, E:/Workspace, AstraRun-Anti)
- hardcoded dogfood/user paths (E:\AstraDogfood)

Generates: docs/audit/F0_25F3_PRODUCTION_CONTAMINATION_AUDIT.json
"""

import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"

FORBIDDEN_TOKENS = [
    "REPAIR-02",
    "factorial_result",
    "MATHEMATICALLY_VERIFIED",
    "3628800",
    "F0_25",
    "No timestamp available",
    r"E:\Workspace",
    "E:/Workspace",
    "AstraRun-Anti",
    r"E:\AstraDogfood",
]


def audit_src() -> dict:
    hits = {}
    total_files = 0

    for py_file in SRC_DIR.rglob("*.py"):
        total_files += 1
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        rel_path = str(py_file.relative_to(REPO_ROOT)).replace("\\", "/")

        for token in FORBIDDEN_TOKENS:
            if token in content:
                # Find matching lines
                lines = []
                for i, line in enumerate(content.splitlines(), 1):
                    if token in line:
                        lines.append({"line_number": i, "content": line.strip()})
                if token not in hits:
                    hits[token] = []
                hits[token].append({"file": rel_path, "matches": lines})

    is_clean = len(hits) == 0
    return {
        "phase": "F0-25F.3",
        "stage": "STAGE 8 — REMOVE BENCHMARK CONTAMINATION FROM PRODUCTION",
        "total_src_files_audited": total_files,
        "forbidden_tokens_audited": FORBIDDEN_TOKENS,
        "contamination_hits_count": sum(len(v) for v in hits.values()),
        "hits_by_token": hits,
        "verdict": "PASS" if is_clean else "FAIL",
        "verdict_rationale": "src/ is completely clean of benchmark fixtures, test tokens, and machine-specific workspace paths." if is_clean else "Contamination found in src/."
    }


def main():
    report = audit_src()
    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_PRODUCTION_CONTAMINATION_AUDIT.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Production contamination audit: {report['verdict']}.")
    print(f"Artifact written to {out_file}")


if __name__ == "__main__":
    main()
