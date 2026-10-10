"""Phase F0-22 Test Reality Audit Script.

Audits all test files in tests/ and classifies:
- First-party AstraRun test suites vs vendored upstream benchmark repositories
- Actual test execution characteristics (UNIT, INTEGRATION, SOURCE_TREE_OS, FROZEN_PRODUCT, MOCK, FIXTURE, SIMULATION)
- Name overstatements (e.g., tests claiming "end_to_end" or "frozen" while using mocks or internal python calls)
- Evidence classification correction

Outputs:
  docs/audit/F0_22_TEST_REALITY_AUDIT.json
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path


def audit_test_reality():
    repo_root = Path(__file__).resolve().parent.parent
    tests_root = repo_root / "tests"

    all_test_files = sorted(tests_root.rglob("test_*.py"))
    
    first_party_tests = []
    vendored_tests = []

    for tpath in all_test_files:
        rel = str(tpath.relative_to(tests_root)).replace("\\", "/")
        if "upstream" in rel:
            vendored_tests.append(rel)
        else:
            first_party_tests.append((rel, tpath))

    classified_tests = []
    overstated_names = []

    for rel_path, full_path in first_party_tests:
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(full_path))
        except Exception:
            continue

        uses_mock = False
        uses_os_live = False
        uses_subprocess = False
        uses_frozen_exe = False
        uses_fixtures = False

        if "unittest.mock" in content or "MagicMock" in content or "monkeypatch" in content or "patch(" in content:
            uses_mock = True
        if "win32gui" in content or "SendInput" in content or "ctypes" in content or "pywinauto" in content:
            uses_os_live = True
        if "subprocess" in content or "os.system" in content:
            uses_subprocess = True
        if "AstraRun.exe" in content or "dist/AstraRun" in content:
            uses_frozen_exe = True
        if "@pytest.fixture" in content or "fixtures." in content:
            uses_fixtures = True

        name_lower = full_path.name.lower()

        # Classify
        if uses_frozen_exe:
            actual_class = "FROZEN_PRODUCT"
        elif uses_os_live:
            actual_class = "SOURCE_TREE_OS"
        elif uses_mock:
            actual_class = "MOCK"
        elif uses_fixtures:
            actual_class = "FIXTURE_INTEGRATION"
        elif uses_subprocess:
            actual_class = "INTEGRATION_PROCESS"
        elif "unit" in rel_path:
            actual_class = "UNIT"
        else:
            actual_class = "INTEGRATION"

        # Check for overstated names
        overstatement_reasons = []
        if ("frozen" in name_lower or "release" in name_lower) and not uses_frozen_exe:
            overstatement_reasons.append("Test name claims 'frozen' or 'release' but runs against in-process Python source code.")
        if "end_to_end" in name_lower and uses_mock:
            overstatement_reasons.append("Test name claims 'end_to_end' but uses mocks or in-memory stubs.")
        if ("real" in name_lower or "live" in name_lower) and uses_mock and not uses_os_live:
            overstatement_reasons.append("Test name claims 'real' or 'live' but uses mock objects.")
        if "post_freeze_holdout" in name_lower:
            overstatement_reasons.append("Previously treated as holdout; modified/iterated post-creation, now serves as REGRESSION suite.")

        entry = {
            "file": rel_path,
            "claimed_by_name": full_path.stem,
            "actual_classification": actual_class,
            "characteristics": {
                "uses_mock": uses_mock,
                "uses_os_live": uses_os_live,
                "uses_subprocess": uses_subprocess,
                "uses_frozen_exe": uses_frozen_exe,
                "uses_fixtures": uses_fixtures,
            },
        }

        if overstatement_reasons:
            entry["overstatement_reasons"] = overstatement_reasons
            overstated_names.append({
                "file": rel_path,
                "claimed_by_name": full_path.stem,
                "actual_classification": actual_class,
                "discrepancies": overstatement_reasons,
                "corrected_classification": actual_class,
            })

        classified_tests.append(entry)

    summary_by_class = {}
    for t in classified_tests:
        c = t["actual_classification"]
        summary_by_class[c] = summary_by_class.get(c, 0) + 1

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-22",
        "total_test_files_on_disk": len(all_test_files),
        "vendored_upstream_benchmark_tests_count": len(vendored_tests),
        "first_party_astrarun_tests_count": len(classified_tests),
        "classification_breakdown": summary_by_class,
        "overstated_tests_count": len(overstated_names),
        "overstated_tests": overstated_names,
        "vendored_repositories": [
            "tests/benchmarks/phase17/upstream/browser_use",
            "tests/benchmarks/phase17/upstream/ufo",
            "tests/benchmarks/phase17/upstream/osworld",
            "tests/benchmarks/phase17/upstream/open_interpreter",
            "tests/benchmarks/phase17/upstream/windows_agent_arena",
        ],
        "first_party_test_suite_inventory": classified_tests,
    }

    out_file = repo_root / "docs" / "audit" / "F0_22_TEST_REALITY_AUDIT.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Generated {out_file} with {len(classified_tests)} first-party tests classified and {len(overstated_names)} overstated names corrected.")


if __name__ == "__main__":
    audit_test_reality()
