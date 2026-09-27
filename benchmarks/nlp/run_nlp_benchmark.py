"""Evaluation harness for AstraRun v0.6.5 NLP Benchmark.

Evaluates linguistic parsing accuracy, clause segmentation, entity extraction,
negation scoping, temporal understanding, and strict safety metrics
(Negated Action Leakage Rate = 0.00%) across Dev V1 and Locked Test V1 datasets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
import psutil

from astrarun.nlp.engine import NLPEngine
from astrarun.nlp.models import NLPEntityType, UserRequest
from astrarun.workflows.compiler import WorkflowCompiler
from astrarun.projects import get_project_registry

BENCHMARK_DIR = Path(__file__).resolve().parent
DEV_PATH = BENCHMARK_DIR / "nlp_dev_v1.json"
TEST_PATH = BENCHMARK_DIR / "nlp_test_v1.json"
RESULTS_PATH = BENCHMARK_DIR / "nlp_benchmark_results.json"


def evaluate_dataset(
    dataset_path: Path,
    engine: NLPEngine,
    compiler: WorkflowCompiler,
    name: str = "DEV"
) -> dict:
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    with open(dataset_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    total_cases = len(cases)
    intent_correct = 0
    clause_matches = 0
    entities_expected = 0
    entities_detected = 0
    entities_true_positives = 0

    negation_total_expected = 0
    negation_correct = 0
    negated_leakage_violations = 0

    temporal_expected = 0
    temporal_detected = 0

    multi_action_total = 0
    multi_action_correct = 0

    workflow_status_correct = 0
    blocked_expected = 0
    blocked_detected = 0

    unsupported_expected = 0
    unsupported_proposals_made = 0

    latencies_ms = []

    for case in cases:
        text = case["text"]
        expected = case.get("expected", {})
        req = UserRequest(text=text, source="benchmark")

        t0 = time.perf_counter()
        utterance = engine.parse(req)
        t_parse = (time.perf_counter() - t0) * 1000
        latencies_ms.append(t_parse)

        proposal = compiler.compile(utterance)

        # 1. Clause Count & Multi-Action Match
        exp_clause_count = expected.get("clause_count", 1)
        det_clause_count = len(utterance.clauses)
        if det_clause_count == exp_clause_count:
            clause_matches += 1
            if exp_clause_count > 1:
                multi_action_correct += 1
        if exp_clause_count > 1:
            multi_action_total += 1

        # 2. Intent Accuracy
        exp_clauses = expected.get("clauses", [])
        if exp_clauses and utterance.clauses:
            first_exp = exp_clauses[0].get("action") or exp_clauses[0].get("intent")
            first_det = utterance.clauses[0].action
            if first_exp == first_det or (first_exp in ("open_project", "open_app") and first_det in ("open_project", "open_app")):
                intent_correct += 1
        else:
            intent_correct += 1

        # 3. Entity Precision / Recall
        all_exp_entities = []
        for ec in exp_clauses:
            for ent in ec.get("entities", []):
                all_exp_entities.append(ent)
        entities_expected += len(all_exp_entities)
        entities_detected += len(utterance.entities)

        for det_ent in utterance.entities:
            matched = any(
                exp_ent.get("type") == det_ent.type.value and
                (str(exp_ent.get("normalized")).lower() == str(det_ent.normalized).lower() or
                 exp_ent.get("normalized") == det_ent.normalized)
                for exp_ent in all_exp_entities
            )
            if matched:
                entities_true_positives += 1

        # 4. Negation & Scope Safety
        exp_neg_count = expected.get("negated_clauses_count", 0)
        det_neg_count = sum(1 for c in utterance.clauses if c.negated)
        if exp_neg_count > 0:
            negation_total_expected += exp_neg_count
            if det_neg_count == exp_neg_count:
                negation_correct += exp_neg_count
        elif det_neg_count == 0:
            pass  # correctly unnegated

        # Safety Check: Did any proposal step execute a negated clause?
        for c in utterance.clauses:
            if c.negated:
                for step in proposal.steps:
                    if step.source_clause_idx == c.idx:
                        negated_leakage_violations += 1


        # 5. Temporal Expressions
        if expected.get("temporal_count", 0) > 0:
            temporal_expected += expected["temporal_count"]
            if utterance.temporal_expressions:
                temporal_detected += len(utterance.temporal_expressions)

        # 6. Workflow Status & Policy Blocking
        exp_status = expected.get("workflow_status")
        if exp_status:
            if proposal.status == exp_status:
                workflow_status_correct += 1

        if expected.get("is_blocked", False):
            blocked_expected += 1
            if proposal.status == "BLOCKED":
                blocked_detected += 1

        if exp_status == "UNSUPPORTED":
            unsupported_expected += 1
            if len(proposal.steps) > 0:
                unsupported_proposals_made += 1

    # Calculations
    ent_precision = entities_true_positives / entities_detected if entities_detected else 1.0
    ent_recall = entities_true_positives / entities_expected if entities_expected else 1.0
    ent_f1 = (2 * ent_precision * ent_recall / (ent_precision + ent_recall)) if (ent_precision + ent_recall) else 1.0

    neg_accuracy = negation_correct / negation_total_expected if negation_total_expected else 1.0
    neg_leakage_rate = negated_leakage_violations / total_cases

    latencies_sorted = sorted(latencies_ms)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
    mean_lat = sum(latencies_ms) / len(latencies_ms)

    return {
        "dataset": name,
        "path": str(dataset_path),
        "sha256": file_hash,
        "total_cases": total_cases,
        "intent_accuracy": round(intent_correct / total_cases, 4),
        "clause_segmentation_acc": round(clause_matches / total_cases, 4),
        "multi_action_exact_match": round(multi_action_correct / multi_action_total, 4) if multi_action_total else 1.0,
        "entity_precision": round(ent_precision, 4),
        "entity_recall": round(ent_recall, 4),
        "entity_f1": round(ent_f1, 4),
        "negation_accuracy": round(neg_accuracy, 4),
        "negated_leakage_rate": round(neg_leakage_rate, 4),
        "temporal_detection_rate": round(temporal_detected / temporal_expected, 4) if temporal_expected else 1.0,
        "workflow_status_accuracy": round(workflow_status_correct / total_cases, 4),
        "block_recall": round(blocked_detected / blocked_expected, 4) if blocked_expected else 1.0,
        "unsupported_proposal_leakage": round(unsupported_proposals_made / unsupported_expected, 4) if unsupported_expected else 0.0,
        "latency_mean_ms": round(mean_lat, 4),
        "latency_p50_ms": round(p50, 4),
        "latency_p95_ms": round(p95, 4),
        "latency_p99_ms": round(p99, 4),
    }


def main():
    parser = argparse.ArgumentParser(description="AstraRun NLP Benchmark Runner")
    parser.add_argument("--test-only", action="store_true", help="Run only on locked test set")
    parser.add_argument("--disable-spacy", action="store_true", help="Benchmark pure deterministic rules")
    args = parser.parse_args()

    proc = psutil.Process(os.getpid())
    ram_start = proc.memory_info().rss / (1024 * 1024)

    t_load_0 = time.perf_counter()
    project_registry = get_project_registry()
    engine = NLPEngine(project_registry=project_registry, enable_spacy=not args.disable_spacy, cache_size=0)
    compiler = WorkflowCompiler()
    load_time_ms = (time.perf_counter() - t_load_0) * 1000

    ram_loaded = proc.memory_info().rss / (1024 * 1024)
    ram_delta = ram_loaded - ram_start

    print("=" * 70)
    print("  AstraRun v0.6.5 NLP Benchmark Evaluation Harness")
    print("=" * 70)
    print(f"Parser Load Time:   {load_time_ms:.2f} ms")
    print(f"RAM Usage:          {ram_loaded:.1f} MB (Delta: +{ram_delta:.1f} MB)")
    print(f"spaCy Enabled:      {not args.disable_spacy}")
    print("-" * 70)

    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "load_time_ms": round(load_time_ms, 2),
        "ram_delta_mb": round(ram_delta, 1),
        "spacy_enabled": not args.disable_spacy,
    }

    if not args.test_only:
        print(f"\n[EVALUATING DEV SET] ({DEV_PATH.name})")
        dev_res = evaluate_dataset(DEV_PATH, engine, compiler, name="DEV_V1")
        results["dev_v1"] = dev_res
        print(f"  Cases:                  {dev_res['total_cases']}")
        print(f"  Intent Accuracy:        {dev_res['intent_accuracy']*100:.1f}%")
        print(f"  Clause Segmentation:    {dev_res['clause_segmentation_acc']*100:.1f}%")
        print(f"  Multi-Action Match:     {dev_res['multi_action_exact_match']*100:.1f}%")
        print(f"  Entity Precision/Recall:{dev_res['entity_precision']*100:.1f}% / {dev_res['entity_recall']*100:.1f}% (F1: {dev_res['entity_f1']:.3f})")
        print(f"  Negation Accuracy:      {dev_res['negation_accuracy']*100:.1f}%")
        print(f"  NEGATED LEAKAGE RATE:   {dev_res['negated_leakage_rate']*100:.2f}% (PRIME SAFETY)")
        print(f"  Block Recall:           {dev_res['block_recall']*100:.1f}%")
        print(f"  Workflow Status Acc:    {dev_res['workflow_status_accuracy']*100:.1f}%")
        print(f"  Mean Latency:           {dev_res['latency_mean_ms']:.3f} ms (p50: {dev_res['latency_p50_ms']:.3f} ms, p95: {dev_res['latency_p95_ms']:.3f} ms)")

    print(f"\n[EVALUATING LOCKED TEST SET] ({TEST_PATH.name})")
    target_hash = "41f1ad1b6a29d071dad3ea93a8390961c41c136b15365586cd48ad3a61211c82"
    print(f"  Target SHA256: {target_hash}")
    test_res = evaluate_dataset(TEST_PATH, engine, compiler, name="TEST_V1")
    results["test_v1"] = test_res
    print(f"  Verified SHA256:        {test_res['sha256']}")
    assert test_res['sha256'] == target_hash, "TEST SET HASH MISMATCH!"

    print(f"  Cases:                  {test_res['total_cases']}")
    print(f"  Intent Accuracy:        {test_res['intent_accuracy']*100:.1f}%")
    print(f"  Clause Segmentation:    {test_res['clause_segmentation_acc']*100:.1f}%")
    print(f"  Multi-Action Match:     {test_res['multi_action_exact_match']*100:.1f}%")
    print(f"  Entity Precision/Recall:{test_res['entity_precision']*100:.1f}% / {test_res['entity_recall']*100:.1f}% (F1: {test_res['entity_f1']:.3f})")
    print(f"  Negation Accuracy:      {test_res['negation_accuracy']*100:.1f}%")
    print(f"  NEGATED LEAKAGE RATE:   {test_res['negated_leakage_rate']*100:.2f}% (PRIME SAFETY)")
    print(f"  Block Recall:           {test_res['block_recall']*100:.1f}%")
    print(f"  Workflow Status Acc:    {test_res['workflow_status_accuracy']*100:.1f}%")
    print(f"  Mean Latency:           {test_res['latency_mean_ms']:.3f} ms (p50: {test_res['latency_p50_ms']:.3f} ms, p95: {test_res['latency_p95_ms']:.3f} ms)")
    print("-" * 70)

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved benchmark results to: {RESULTS_PATH}\n")


if __name__ == "__main__":
    main()
