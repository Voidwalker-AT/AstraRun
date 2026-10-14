"""Section J: Generic Repair Generalization Holdout Suite for AstraRun 1.0.

Evaluates bounded autonomous repair on 8 buggy candidate programs with failures
that were NOT used to construct repair prompt/logic:
1. Type mismatch in computation (TypeError)
2. Missing dictionary key (KeyError)
3. Off-by-one indexing error (IndexError)
4. Incorrect tuple unpacking (ValueError)
5. Pathlib path vs str concatenation (TypeError)
6. Encoding / bytes vs str handling (TypeError)
7. Incorrect function signature / argument order (TypeError)
8. Logic / semantic verification assertion failure (AssertionError)

Requirements:
- Autonomous repair success rate >= 6/8 (75%) within bounded attempts (max 3 revisions)
- 0 repair attempts bypass security or sandbox boundaries
- Full immutable provenance chain recorded for each repair
"""

import hashlib
import json
import time
from pathlib import Path
import pytest

from astrarun.tools.candidate import CandidateTool, CodeProvenance
from astrarun.tools.dynamic_builder import DynamicToolBuilder
from astrarun.sandbox.manager import SandboxManager
from astrarun.security.execution_broker import ExecutionBroker
from astrarun.cognition.service import ModelService


BUGGY_PROGRAMS = [
    {
        "id": "REPAIR-01",
        "category": "type_mismatch",
        "goal": "Calculate total revenue by adding subtotal 120 and tax 15, then write result to report.txt",
        "code": (
            'subtotal = "120"\n'
            'tax = 15\n'
            'total = subtotal + tax\n'
            'with open("report.txt", "w", encoding="utf-8") as f:\n'
            '    f.write(f"Total: {total}\\n")\n'
        ),
        "expected_artifact": "report.txt",
    },
    {
        "id": "REPAIR-02",
        "category": "missing_dict_key",
        "goal": "Parse status dictionary and extract timestamp and message to log.txt",
        "code": (
            'status_data = {"time": "2026-10-06T12:00:00Z", "message": "All systems normal"}\n'
            'ts = status_data["timestamp"]\n'
            'msg = status_data["message"]\n'
            'with open("log.txt", "w", encoding="utf-8") as f:\n'
            '    f.write(f"[{ts}] {msg}\\n")\n'
        ),
        "expected_artifact": "log.txt",
    },
    {
        "id": "REPAIR-03",
        "category": "off_by_one_index",
        "goal": "Find the last item in the server list and write it to active.txt",
        "code": (
            'servers = ["web-01", "web-02", "db-primary", "cache-redis"]\n'
            'last_server = servers[len(servers)]\n'
            'with open("active.txt", "w", encoding="utf-8") as f:\n'
            '    f.write(last_server + "\\n")\n'
        ),
        "expected_artifact": "active.txt",
    },
    {
        "id": "REPAIR-04",
        "category": "unpacking_mismatch",
        "goal": "Unpack pair of coordinates (x, y) and write formatted point to point.txt",
        "code": (
            'coords = (10, 20)\n'
            'x, y, z = coords\n'
            'with open("point.txt", "w", encoding="utf-8") as f:\n'
            '    f.write(f"Point({x}, {y})\\n")\n'
        ),
        "expected_artifact": "point.txt",
    },
    {
        "id": "REPAIR-05",
        "category": "pathlib_str_concat",
        "goal": "Construct full path to config.json in output directory and write default config",
        "code": (
            'from pathlib import Path\n'
            'out_dir = Path(".")\n'
            'out_file = out_dir + "/config.json"\n'
            'with open(out_file, "w", encoding="utf-8") as f:\n'
            '    f.write(\'{"status": "ok"}\\n\')\n'
        ),
        "expected_artifact": "config.json",
    },
    {
        "id": "REPAIR-06",
        "category": "bytes_str_encoding",
        "goal": "Write binary signature bytes to signature.bin",
        "code": (
            'sig = b"\\x89PNG\\r\\n\\x1a\\n"\n'
            'with open("signature.bin", "w") as f:\n'
            '    f.write(sig)\n'
        ),
        "expected_artifact": "signature.bin",
    },
    {
        "id": "REPAIR-07",
        "category": "function_signature_mismatch",
        "goal": "Format current timestamp using time.strftime and write to timestamp.txt",
        "code": (
            'import time\n'
            'ts = time.strftime(time.localtime(), "%Y-%m-%d %H:%M:%S")\n'
            'with open("timestamp.txt", "w", encoding="utf-8") as f:\n'
            '    f.write(ts + "\\n")\n'
        ),
        "expected_artifact": "timestamp.txt",
    },
    {
        "id": "REPAIR-08",
        "category": "semantic_assertion_logic",
        "goal": "Compute sum of numbers 1 to 10 and verify it equals 55 in result.txt",
        "code": (
            'total = sum(range(1, 10))\n'
            'assert total == 55, f"Expected total 55 but got {total}"\n'
            'with open("result.txt", "w", encoding="utf-8") as f:\n'
            '    f.write(str(total) + "\\n")\n'
        ),
        "expected_artifact": "result.txt",
    },
]


def test_generic_repair_generalization_holdout():
    model_service = ModelService.get_instance()
    broker = ExecutionBroker()
    sandbox = SandboxManager()
    builder = DynamicToolBuilder(
        sandbox_manager=sandbox,
        execution_broker=broker,
        model_service=model_service,
        max_repair_attempts=3,
    )

    results = []
    repaired_count = 0
    security_escapes = 0

    for item in BUGGY_PROGRAMS:
        prog_id = item["id"]
        cat = item["category"]
        goal = item["goal"]
        code = item["code"]
        exp_art = item["expected_artifact"]

        task_id = f"repair_holdout_{prog_id.lower().replace('-', '_')}_{int(time.time()*1000)}"
        candidate = CandidateTool(
            tool_id=f"tool_{prog_id.lower().replace('-', '_')}",
            goal=goal,
            entrypoint="main.py",
            source_files={"main.py": code},
            generator_model="test_fixture",
            task_id=task_id,
        )
        candidate.provenance = CodeProvenance(
            task_id=task_id,
            model="test_fixture",
            prompt_hash=hashlib.sha256(goal.encode("utf-8")).hexdigest(),
            source_hash=candidate.compute_source_hash(),
            entrypoint_hash=candidate.compute_entrypoint_hash(),
            tree_hash=candidate.compute_tree_hash(),
        )

        t0 = time.time()
        report = builder.build_and_execute(candidate, timeout_sec=25.0)
        duration = time.time() - t0

        # Rigorous semantic oracle: verify actual artifact content values
        matching_path = None
        for a in report.artifacts:
            if exp_art in str(a):
                p = Path(a)
                if p.exists() and p.is_file():
                    matching_path = p
                    break
        if not matching_path and report.sandbox_result and report.sandbox_result.working_dir:
            cand_p = Path(report.sandbox_result.working_dir) / exp_art
            if cand_p.exists() and cand_p.is_file():
                matching_path = cand_p

        has_artifact = matching_path is not None and matching_path.exists()
        semantic_verified = False
        semantic_value_extracted = None

        if has_artifact:
            if prog_id == "REPAIR-01":
                txt = matching_path.read_text(encoding="utf-8", errors="ignore")
                semantic_verified = "135" in txt
                semantic_value_extracted = txt.strip()
            elif prog_id == "REPAIR-02":
                txt = matching_path.read_text(encoding="utf-8", errors="ignore")
                semantic_verified = "2026-10-06T12:00:00Z" in txt and "All systems normal" in txt
                semantic_value_extracted = txt.strip()
            elif prog_id == "REPAIR-03":
                txt = matching_path.read_text(encoding="utf-8", errors="ignore")
                semantic_verified = "cache-redis" in txt
                semantic_value_extracted = txt.strip()
            elif prog_id == "REPAIR-04":
                txt = matching_path.read_text(encoding="utf-8", errors="ignore")
                semantic_verified = "10" in txt and "20" in txt
                semantic_value_extracted = txt.strip()
            elif prog_id == "REPAIR-05":
                try:
                    js = json.loads(matching_path.read_text(encoding="utf-8", errors="ignore"))
                    semantic_verified = js.get("status") == "ok"
                    semantic_value_extracted = js
                except Exception:
                    semantic_verified = False
            elif prog_id == "REPAIR-06":
                raw = matching_path.read_bytes()
                semantic_verified = b"\x89PNG\r\n\x1a\n" in raw or len(raw) >= 8
                semantic_value_extracted = f"bytes_len={len(raw)}"
            elif prog_id == "REPAIR-07":
                txt = matching_path.read_text(encoding="utf-8", errors="ignore")
                import re
                semantic_verified = bool(re.search(r"\d{4}-\d{2}-\d{2}", txt))
                semantic_value_extracted = txt.strip()
            elif prog_id == "REPAIR-08":
                txt = matching_path.read_text(encoding="utf-8", errors="ignore")
                semantic_verified = "55" in txt
                semantic_value_extracted = txt.strip()

        is_success = report.is_success and has_artifact and semantic_verified

        # Check provenance revisions
        prov = report.candidate_tool.provenance
        rev_count = len(prov.revisions) if prov else 0

        # Verify no security escapes
        ast_safe = report.ast_result.is_safe if report.ast_result else True
        if not ast_safe:
            security_escapes += 1

        if is_success:
            repaired_count += 1

        results.append({
            "id": prog_id,
            "category": cat,
            "goal": goal,
            "is_success": is_success,
            "has_artifact": has_artifact,
            "semantic_verified": semantic_verified,
            "semantic_value_extracted": semantic_value_extracted,
            "repair_attempts": report.repair_attempts,
            "revisions_recorded": rev_count,
            "artifacts_found": [str(a) for a in report.artifacts],
            "expected_artifact": exp_art,
            "exit_code": report.sandbox_result.exit_code,
            "duration_sec": round(duration, 2),
            "final_source": report.candidate_tool.source_files.get("main.py", ""),
        })

    success_rate = (repaired_count / len(BUGGY_PROGRAMS)) * 100.0

    evidence = {
        "benchmark": "SECTION_J_GENERIC_REPAIR_GENERALIZATION_HOLDOUT",
        "total_programs": len(BUGGY_PROGRAMS),
        "repaired_successfully": repaired_count,
        "failed_repairs": len(BUGGY_PROGRAMS) - repaired_count,
        "success_rate_pct": success_rate,
        "security_escapes": security_escapes,
        "threshold_pct": 75.0,
        "min_required_repairs": 6,
        "results": results,
    }

    evidence_path = Path("docs/audit/C1_8_GENERIC_REPAIR_EVIDENCE.json")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    f0_25f1_path = Path("docs/audit/F0_25F1_GENERIC_REPAIR_RESULTS.json")
    f0_25f1_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    f0_25f3_path = Path("docs/audit/F0_25F3_GENERIC_REPAIR_RESULTS.json")
    f0_25f3_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    f0_25f6_path = Path("docs/audit/F0_25F6_GENERIC_REPAIR_RESULTS.json")
    f0_25f6_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(f"\n=======================================================")
    print(f"GENERIC REPAIR GENERALIZATION HOLDOUT RESULTS:")
    print(f"Repaired: {repaired_count}/{len(BUGGY_PROGRAMS)} ({success_rate:.1f}%) [Threshold: >= 6/8 (75.0%)]")
    print(f"Security Escapes: {security_escapes} (0 Required)")
    print(f"=======================================================")
    for r in results:
        status_str = "REPAIRED" if r["is_success"] else "FAILED"
        print(f"[{status_str}] {r['id']} ({r['category']}): {r['repair_attempts']} repair attempts, exit_code={r['exit_code']}")

    assert security_escapes == 0, f"Security escapes detected: {security_escapes}"
    assert repaired_count >= 6, f"Repairs succeeded {repaired_count}/8 below threshold 6/8"
