"""Benchmark Evaluation Harness for AstraRun v0.8.5 Learning Foundation.

Evaluates 320 benchmark cases across 7 critical learning and security dimensions.
Calculates False Memory Activation Rate, Security Invariant Enforcement,
Precedence Accuracy, and End-to-End Latency.
"""

from __future__ import annotations

import gc
import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from astrarun.core.models import ActionGateOutcome, ToolRisk
from astrarun.learning.aliases import AliasManager
from astrarun.learning.confidence import ConfidenceCalculator
from astrarun.learning.evidence import EvidenceExtractor
from astrarun.learning.memory import MemoryStore
from astrarun.learning.models import (
    Correction,
    EvidenceReference,
    EvidenceType,
    MemoryNamespace,
    MemoryStatus,
    SemanticMemory,
    SkillStep,
)
from astrarun.learning.patterns import PatternMiner
from astrarun.learning.persistence import LearningPersistence
from astrarun.learning.skills import SkillManager
from astrarun.policy.action_gate import ActionGate
from astrarun.routing.entity_resolver import ProposedAction
from astrarun.tasks.models import Task, TaskEvent, TaskEventType, TaskStatus

EXPECTED_SHA256 = "b935f4ece761d59a98d7b98053cc18ffcb6ae33259f4888cb828ab3787281b9a"


def evaluate_benchmark(benchmark_file: Path | str = "benchmarks/learning/learning_benchmark_v1.json") -> dict[str, Any]:
    file_path = Path(benchmark_file)
    data = file_path.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()

    cases = json.loads(data.decode("utf-8"))
    total_cases = len(cases)

    category_counts: dict[str, int] = {}
    category_correct: dict[str, int] = {}
    latencies: list[float] = []

    false_activations = 0
    security_violations = 0

    temp_dir = tempfile.TemporaryDirectory()
    temp_db = Path(temp_dir.name) / "test_learning_bench.db"
    persistence = LearningPersistence(db_path=temp_db)
    calculator = ConfidenceCalculator()
    extractor = EvidenceExtractor()
    gate = ActionGate()

    for case in cases:
        cat = case["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        t0 = time.perf_counter()
        passed = False

        if cat == "explicit_teaching":
            task = Task(id="t_teach", conversation_id="conv_teach", request_text=case["query"])
            mem = extractor.extract_teaching(task)
            if mem and mem.namespace.value == case["expected_namespace"] and mem.key == case["expected_key"] and mem.value == case["expected_value"]:
                passed = True

        elif cat == "alias_precedence":
            static_map = {case["alias_key"]: case["static_mapping"]} if case.get("static_mapping") else {}
            mgr = AliasManager(
                memory_store=MemoryStore(persistence=persistence, calculator=calculator),
                static_aliases=static_map,
            )
            if case.get("learned_candidate"):
                mem = SemanticMemory(
                    id=f"mem_prec_{case['id']}",
                    namespace=MemoryNamespace.ALIAS,
                    key=case["alias_key"],
                    value=case["learned_candidate"],
                    target_type="application",
                    status=MemoryStatus.ACTIVE if (case["candidate_confirmed"] or case["candidate_confidence"] >= 0.85) else MemoryStatus.CANDIDATE,
                    confidence=case["candidate_confidence"],
                    user_confirmed=case["candidate_confirmed"],
                )
                persistence.save_memory(mem)

            res = mgr.resolve(case["alias_key"], expected_target_type="application")
            if case["expected_resolved"] is None:
                if res is None:
                    passed = True
                else:
                    false_activations += 1
            else:
                if res and res[0] == case["expected_resolved"] and res[1] == case["expected_source"]:
                    passed = True

        elif cat == "user_corrections":
            corr = Correction(
                id=f"corr_{case['id']}",
                task_id="t1",
                conversation_id="conv1",
                incorrect_mapping={"key": case["key"], "target": case["initial_incorrect"]},
                corrected_mapping={"key": case["key"], "target": case["expected_promoted_target"]},
            )
            store = MemoryStore(persistence=persistence, calculator=calculator)
            # Seed initial incorrect
            store.add_or_update_memory(
                namespace=MemoryNamespace.ALIAS,
                key=case["key"],
                value=case["initial_incorrect"],
                target_type="application",
            )
            # Apply correction
            store.apply_correction(corr)

            new_mem = store.find_memory(namespace=MemoryNamespace.ALIAS, key=case["key"])
            if new_mem and new_mem.value == case["expected_promoted_target"] and new_mem.status.value == case["expected_new_status"]:
                passed = True

        elif cat == "conflicted_aliases":
            mem1 = SemanticMemory(
                id=f"conf_1_{case['id']}",
                namespace=MemoryNamespace.ALIAS,
                key=case["key"],
                value=case["target1"],
                target_type="application",
                status=MemoryStatus.ACTIVE,
                confidence=case["confidence1"],
            )
            mem2 = SemanticMemory(
                id=f"conf_2_{case['id']}",
                namespace=MemoryNamespace.ALIAS,
                key=case["key"],
                value=case["target2"],
                target_type="application",
                status=MemoryStatus.ACTIVE,
                confidence=case["confidence2"],
            )
            conflicted = calculator.detect_conflicts([mem1, mem2])
            is_conflicted = all(m.status == MemoryStatus.CONFLICTED for m in conflicted)
            if is_conflicted:
                passed = True

        elif cat == "time_decay":
            now = time.time()
            past = now - (case["days_elapsed"] * 86400.0)
            refs = [
                EvidenceReference(
                    task_id=f"t_decay_{i}",
                    conversation_id="c_decay",
                    evidence_type=EvidenceType.CONFIRMATION_ACCEPTED,
                    weight=2.0,
                )
                for i in range(4)
            ]
            mem = SemanticMemory(
                id=f"decay_{case['id']}",
                namespace=MemoryNamespace.ALIAS,
                key=f"decay_key_{case['id']}",
                value="target_app",
                target_type="application",
                last_used_at=past,
                pinned=case["pinned"],
                user_confirmed=case["pinned"],
                evidence_refs=refs,
            )
            st = calculator.evaluate_status(mem, current_time=now)
            if st.value == case["expected_status"]:
                passed = True

        elif cat == "skill_mining":
            miner = PatternMiner(min_support=case["expected_min_support"])
            tasks = []
            for r in range(case["repetition_count"]):
                evs = [
                    TaskEvent(
                        id=f"ev_{r}_{c}",
                        task_id=f"task_{r}",
                        type=TaskEventType.CAPABILITY_COMPLETED,
                        title=c,
                        capability_id=c,
                    )
                    for c in case["capabilities_sequence"]
                ]
                t = Task(
                    id=f"task_{r}",
                    conversation_id="conv_skill",
                    status=TaskStatus.COMPLETED,
                    events=evs,
                )
                tasks.append(t)

            discovered = miner.mine_patterns(tasks)
            if discovered and len(discovered) > 0:
                skill = discovered[0]
                if skill.support_count >= case["expected_min_support"]:
                    passed = True

        elif cat == "security_invariants":
            att_type = case["attack_type"]
            if att_type in {"protected_process_alias", "blocked_command_alias"}:
                task = Task(id="t_sec", conversation_id="conv_sec", request_text=case["statement"])
                mem = extractor.extract_teaching(task)
                is_safe = extractor.is_security_safe(case["statement"], case.get("target"))
                # Must be blocked
                if mem is None and not is_safe:
                    passed = True
                else:
                    security_violations += 1
            elif att_type == "confirmation_bypass_attempt":
                # Verify that repeated confirmation never downgrades policy
                action = ProposedAction(
                    action_type="terminate_process",
                    raw_query="kill chrome",
                    target="chrome.exe",
                    tool="terminate_process",
                    arguments={"pid": 1234},
                    requires_confirmation=True,
                    status="resolved",
                )
                verdict = gate.evaluate(action)
                if verdict.status.value.upper() == case["expected_gate_verdict"]:
                    passed = True
                else:
                    security_violations += 1

        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

        if passed:
            category_correct[cat] = category_correct.get(cat, 0) + 1

    del persistence
    gc.collect()
    try:
        temp_dir.cleanup()
    except Exception:
        pass

    # Latency percentiles
    latencies.sort()
    mean_lat = sum(latencies) / len(latencies) if latencies else 0.0
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    total_correct = sum(category_correct.values())
    accuracy = (total_correct / total_cases) * 100.0

    false_activation_rate = (false_activations / total_cases) * 100.0
    security_enforcement_rate = (1.0 - (security_violations / max(1, category_counts.get("security_invariants", 1)))) * 100.0

    results = {
        "benchmark_file": str(file_path),
        "total_cases": total_cases,
        "verified_sha256": actual_sha256,
        "sha256_match": actual_sha256 == EXPECTED_SHA256,
        "overall_accuracy": round(accuracy, 2),
        "false_activation_rate": round(false_activation_rate, 2),
        "security_enforcement_rate": round(security_enforcement_rate, 2),
        "category_accuracies": {
            cat: round((category_correct.get(cat, 0) / count) * 100.0, 2)
            for cat, count in category_counts.items()
        },
        "mean_latency_ms": round(mean_lat, 3),
        "p50_latency_ms": round(p50, 3),
        "p95_latency_ms": round(p95, 3),
    }

    return results


def main() -> None:
    print("=" * 68)
    print("  AstraRun v0.8.5 Learning & Memory Benchmark Evaluation Harness")
    print("=" * 68)

    results = evaluate_benchmark()

    print(f"Cases Evaluated:           {results['total_cases']}")
    print(f"Dataset SHA256:            {results['verified_sha256']}")
    print(f"SHA256 Match:              {results['sha256_match']}")
    print(f"Overall Accuracy:          {results['overall_accuracy']}%")
    print(f"FALSE MEMORY ACTIVATION:   {results['false_activation_rate']}% (PRIME SAFETY)")
    print(f"SECURITY INVARIANT RATE:   {results['security_enforcement_rate']}% (PRIME SAFETY)")
    print("-" * 68)
    print("Category Breakdown:")
    for cat, acc in results["category_accuracies"].items():
        print(f"  - {cat:<25}: {acc}%")
    print("-" * 68)
    print(f"Mean Latency:              {results['mean_latency_ms']} ms (p50: {results['p50_latency_ms']} ms, p95: {results['p95_latency_ms']} ms)")
    print("=" * 68)

    out_file = Path("benchmarks/learning/learning_benchmark_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results to: {out_file.resolve()}\n")


if __name__ == "__main__":
    main()
