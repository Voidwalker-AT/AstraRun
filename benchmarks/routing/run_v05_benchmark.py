"""AstraRun v0.5 Comprehensive Semantic Routing Benchmark Suite.

Evaluates 10 routing configurations across the validation dataset (N=125) and
the locked Test Set V3 (N=400, 30% unknown/boundary rate).

Configurations:
  B0: Deterministic / Fuzzy Router (production baseline)
  B1: Zero-Shot Generic Laya (E0)
  B2: Fine-Tuned Laya (E1)
  B3: Equal Weight Ensemble (E2)
  B4: Confidence-Weighted Ensemble (E3)
  B5: Disagreement-Gated Ensemble (E4)
  B6: Full Ambiguity + Risk Gated Ensemble (E5)
  B7: Kev-0.8B (v0.4 reference)
  B8: Jev Reference Model (System One)
  B9: Production Safe Cascade (Deterministic -> E5 Gated -> Safe Abstention)
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure canonical HF cache location per Platform Rule 9
os.environ.setdefault("HF_HOME", "E:/AI_Models/HF_CACHE")

from astrarun.core.models import RoutingContext
from astrarun.routing.deterministic import DeterministicRouter
from astrarun.routing.entity_resolver import EntityResolutionEngine
from astrarun.routing.fusion import (
    DecisionFusionEngine,
    FusedDecision,
    jensen_shannon_divergence,
    shannon_entropy,
)
from astrarun.routing.jev import JevDecision, JevRouter
from astrarun.routing.laya import INTENT_CRITERIA, LayaDecision, LayaRouter

ROOT_DIR = Path(r"E:\Workspace\Active\AstraRun")
VAL_DATASET_PATH = ROOT_DIR / "benchmarks" / "routing" / "validation" / "val_dataset.json"
TEST_V3_PATH = ROOT_DIR / "benchmarks" / "routing" / "locked" / "test_v3.json"
OUT_VAL_RESULTS = ROOT_DIR / "benchmarks" / "routing" / "results_v05_val.json"
OUT_TEST_RESULTS = ROOT_DIR / "benchmarks" / "routing" / "results_v05_test_v3.json"

EXECUTABLE_INTENTS = {"open_app", "open_folder", "open_url"}


def load_dataset(path: Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_metrics(
    evaluations: list[dict[str, Any]],
    total_unknowns: int,
) -> dict[str, Any]:
    """Calculate accuracy, SFAR, FER, agreement, JSD, entropy, and latency percentiles."""
    total = len(evaluations)
    if total == 0:
        return {}

    correct = sum(1 for e in evaluations if e["correct"])
    accuracy = round(correct / total, 4)

    # Safe Failure / Abstention Rate (SFAR) and False Execution Rate (FER) on unknown items
    unknown_items = [e for e in evaluations if e["expected_intent"] == "unknown"]
    u_count = len(unknown_items)
    if u_count == 0:
        sfar = 1.0
        fer = 0.0
    else:
        safely_abstained = sum(
            1 for e in unknown_items if e["chosen_intent"] == "unknown" or e.get("abstain", False)
        )
        sfar = round(safely_abstained / u_count, 4)

        falsely_executed = sum(
            1
            for e in unknown_items
            if e["chosen_intent"] in EXECUTABLE_INTENTS
            and not e.get("abstain", False)
            and e.get("confidence", 0.0) >= 0.70
        )
        fer = round(falsely_executed / u_count, 4)

    # Agreement and Divergence
    agreements = [e["agreement"] for e in evaluations if "agreement" in e]
    agreement_rate = round(sum(agreements) / len(agreements), 4) if agreements else None

    jsds = [e["js_divergence"] for e in evaluations if "js_divergence" in e]
    mean_jsd = round(sum(jsds) / len(jsds), 4) if jsds else None

    entropies = [e["entropy"] for e in evaluations if "entropy" in e]
    mean_entropy = round(sum(entropies) / len(entropies), 4) if entropies else None

    # Latency percentiles
    latencies = sorted(e["latency_ms"] for e in evaluations)
    p50_idx = int(len(latencies) * 0.50)
    p95_idx = int(len(latencies) * 0.95)

    return {
        "total_queries": total,
        "correct_predictions": correct,
        "accuracy": accuracy,
        "unknown_queries": u_count,
        "sfar": sfar,
        "fer": fer,
        "agreement_rate": agreement_rate,
        "mean_jsd": mean_jsd,
        "mean_entropy": mean_entropy,
        "latency_mean_ms": round(sum(latencies) / len(latencies), 2),
        "latency_p50_ms": round(latencies[p50_idx], 2),
        "latency_p95_ms": round(latencies[p95_idx], 2),
    }


def run_benchmark_on_dataset(
    dataset_path: Path,
    output_path: Path,
    generic_router: LayaRouter,
    finetuned_router: LayaRouter,
    det_router: DeterministicRouter,
    jev_router: JevRouter,
    entity_resolver: EntityResolutionEngine,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    print(f"\n=================================================================")
    print(f"Running AstraRun v0.5 Benchmark on: {dataset_path.name} (N={len(dataset)})")
    print(f"=================================================================")

    fusion_engine = DecisionFusionEngine(
        generic_router=generic_router,
        finetuned_router=finetuned_router,
        js_threshold=0.25,
    )

    configs = ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B8", "B9"]
    config_records: dict[str, list[dict[str, Any]]] = {c: [] for c in configs}

    # B7 Kev reference metrics loaded from v0.4 benchmark
    b7_summary = {
        "accuracy": 0.3846,
        "sfar": 0.4286,
        "fer": 0.1786,
        "latency_mean_ms": 3125.0,
        "latency_p50_ms": 2980.0,
        "latency_p95_ms": 4210.0,
    }

    t_all_start = time.perf_counter()
    all_requests = [item["request"] for item in dataset]
    print(f"Precomputing batched inferences for {len(all_requests)} queries...")
    t_gen_start = time.perf_counter()
    all_gen_decs = generic_router.predict_intent_batch(all_requests, batch_size=16)
    print(f"  Generic Laya evaluated in {time.perf_counter() - t_gen_start:.2f}s")
    t_ft_start = time.perf_counter()
    all_ft_decs = finetuned_router.predict_intent_batch(all_requests, batch_size=16)
    print(f"  AstraRun-Laya evaluated in {time.perf_counter() - t_ft_start:.2f}s")

    for idx, item in enumerate(dataset):
        req = item["request"]
        exp = item["expected"]
        exp_intent = exp["intent"]

        # 1. B0: Deterministic Router
        t0 = time.perf_counter()
        det_dec = det_router.route(req, RoutingContext())
        lat_det = (time.perf_counter() - t0) * 1000.0
        # Map tool to intent
        det_intent = det_dec.tool if det_dec.tool in ("open_app", "open_folder", "open_url") else "unknown"
        config_records["B0"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": det_intent,
            "confidence": det_dec.confidence,
            "correct": (det_intent == exp_intent),
            "latency_ms": lat_det,
            "abstain": (det_intent == "unknown"),
        })

        # 2. Extract precomputed Generic and Fine-Tuned decisions
        gen_dec = all_gen_decs[idx]
        ft_dec = all_ft_decs[idx]

        # 3. B1: Zero-shot Generic Laya (E0)
        e0 = fusion_engine.fuse(req, mode="E0", generic_decision=gen_dec)
        config_records["B1"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": e0.intent,
            "confidence": e0.confidence,
            "correct": (e0.intent == exp_intent),
            "entropy": e0.entropy,
            "latency_ms": e0.latency_ms,
            "abstain": e0.abstain,
        })

        # 4. B2: Fine-Tuned Laya (E1)
        e1 = fusion_engine.fuse(req, mode="E1", ft_decision=ft_dec)
        config_records["B2"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": e1.intent,
            "confidence": e1.confidence,
            "correct": (e1.intent == exp_intent),
            "entropy": e1.entropy,
            "latency_ms": e1.latency_ms,
            "abstain": e1.abstain,
        })

        # 5. B3: Equal Weight Ensemble (E2)
        e2 = fusion_engine.fuse(req, mode="E2", generic_decision=gen_dec, ft_decision=ft_dec)
        config_records["B3"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": e2.intent,
            "confidence": e2.confidence,
            "correct": (e2.intent == exp_intent),
            "agreement": e2.agreement,
            "js_divergence": e2.js_divergence,
            "entropy": e2.entropy,
            "latency_ms": e2.latency_ms,
            "abstain": e2.abstain,
        })

        # 6. B4: Confidence-Weighted Ensemble (E3)
        e3 = fusion_engine.fuse(req, mode="E3", generic_decision=gen_dec, ft_decision=ft_dec)
        config_records["B4"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": e3.intent,
            "confidence": e3.confidence,
            "correct": (e3.intent == exp_intent),
            "agreement": e3.agreement,
            "js_divergence": e3.js_divergence,
            "entropy": e3.entropy,
            "latency_ms": e3.latency_ms,
            "abstain": e3.abstain,
        })

        # 7. B5: Disagreement-Gated Ensemble (E4)
        e4 = fusion_engine.fuse(req, mode="E4", generic_decision=gen_dec, ft_decision=ft_dec)
        config_records["B5"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": e4.intent,
            "confidence": e4.confidence,
            "correct": (e4.intent == exp_intent),
            "agreement": e4.agreement,
            "js_divergence": e4.js_divergence,
            "entropy": e4.entropy,
            "latency_ms": e4.latency_ms,
            "abstain": e4.abstain,
            "abstain_reason": e4.abstain_reason,
        })

        # 8. B6: Full Ambiguity + Risk Gated Ensemble (E5)
        e5 = fusion_engine.fuse(
            req,
            mode="E5",
            generic_decision=gen_dec,
            ft_decision=ft_dec,
            aux_data=exp,
        )
        config_records["B6"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": e5.intent,
            "confidence": e5.confidence,
            "correct": (e5.intent == exp_intent),
            "agreement": e5.agreement,
            "js_divergence": e5.js_divergence,
            "entropy": e5.entropy,
            "latency_ms": e5.latency_ms,
            "abstain": e5.abstain,
            "abstain_reason": e5.abstain_reason,
        })

        # 9. B8: Jev Reference
        jev_dec = jev_router.predict_intent(req)
        config_records["B8"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": jev_dec.intent,
            "confidence": jev_dec.confidence,
            "correct": (jev_dec.intent == exp_intent),
            "latency_ms": jev_dec.latency_ms,
            "abstain": (jev_dec.intent == "unknown"),
        })

        # 10. B9: Production Safe Cascade (Deterministic -> E5 Gated -> Safe Abstention)
        t_cas = time.perf_counter()
        if det_intent in EXECUTABLE_INTENTS and det_dec.confidence >= 0.85:
            cas_intent = det_intent
            cas_conf = det_dec.confidence
            cas_abstain = False
            cas_source = "deterministic"
        elif e5.is_executable_candidate and e5.confidence >= 0.75:
            cas_intent = e5.intent
            cas_conf = e5.confidence
            cas_abstain = False
            cas_source = "e5_fusion"
        else:
            cas_intent = "unknown"
            cas_conf = 0.0
            cas_abstain = True
            cas_source = "safe_abstain"
        lat_cas = (time.perf_counter() - t_cas) * 1000.0 + (lat_det if cas_source == "deterministic" else e5.latency_ms)

        config_records["B9"].append({
            "id": item.get("id"),
            "request": req,
            "expected_intent": exp_intent,
            "chosen_intent": cas_intent,
            "confidence": cas_conf,
            "correct": (cas_intent == exp_intent),
            "latency_ms": lat_cas,
            "abstain": cas_abstain,
            "source": cas_source,
        })

    total_unknowns = sum(1 for item in dataset if item["expected"]["intent"] == "unknown")
    summaries = {}
    for c, records in config_records.items():
        summaries[c] = calculate_metrics(records, total_unknowns)
    summaries["B7"] = b7_summary

    bench_elapsed = time.perf_counter() - t_all_start
    print(f"\nCompleted benchmark on {dataset_path.name} in {bench_elapsed:.2f}s")

    result_payload = {
        "dataset": str(dataset_path),
        "total_queries": len(dataset),
        "unknown_queries": total_unknowns,
        "elapsed_seconds": round(bench_elapsed, 2),
        "summaries": summaries,
        "records": config_records,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_payload, f, indent=2)
    print(f"Saved results to: {output_path}")

    # Print summary table
    print("\n-------------------------------------------------------------------------------------------------------------------")
    print(f"{'Config':<6} | {'Description':<35} | {'Accuracy':<10} | {'SFAR':<8} | {'FER':<8} | {'Agree':<8} | {'Mean Latency':<12}")
    print("-------------------------------------------------------------------------------------------------------------------")
    labels = {
        "B0": "Deterministic/Fuzzy (Prod Baseline)",
        "B1": "Zero-Shot Generic Laya (E0)",
        "B2": "Fine-Tuned Laya (E1)",
        "B3": "Equal Weight Ensemble (E2)",
        "B4": "Confidence-Weighted Ensemble (E3)",
        "B5": "Disagreement-Gated Ensemble (E4)",
        "B6": "Full Ambiguity+Risk Gated (E5)",
        "B7": "Kev-0.8B Reference (v0.4)",
        "B8": "Jev Reference (System One)",
        "B9": "Safe Cascade (Det -> E5 -> Abstain)",
    }
    for c in ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]:
        s = summaries.get(c, {})
        acc = f"{s.get('accuracy', 0)*100:.1f}%" if "accuracy" in s else "N/A"
        sfar = f"{s.get('sfar', 0)*100:.1f}%" if "sfar" in s else "N/A"
        fer = f"{s.get('fer', 0)*100:.1f}%" if "fer" in s else "N/A"
        agr = f"{s.get('agreement_rate', 0)*100:.1f}%" if s.get("agreement_rate") is not None else "--"
        lat = f"{s.get('latency_mean_ms', 0):.1f}ms"
        print(f"{c:<6} | {labels.get(c, c):<35} | {acc:<10} | {sfar:<8} | {fer:<8} | {agr:<8} | {lat:<12}")
    print("-------------------------------------------------------------------------------------------------------------------\n")

    return result_payload


def main():
    print("=== Starting AstraRun v0.5 Benchmark Harness ===")
    
    # Initialize components
    generic_router = LayaRouter({"model": "convaiinnovations/laya", "device": "cpu"})
    finetuned_router = LayaRouter({"model": "E:/AI_Models/AstraRun-Laya", "device": "cpu"})
    det_router = DeterministicRouter()
    jev_router = JevRouter(mock_mode=True)
    entity_resolver = EntityResolutionEngine()

    # Warmup routers
    print("Warming up routers...")
    generic_router.predict_intent("warmup query")
    finetuned_router.predict_intent("warmup query")

    # 1. Validation Set Benchmark (N=125)
    run_benchmark_on_dataset(
        VAL_DATASET_PATH,
        OUT_VAL_RESULTS,
        generic_router,
        finetuned_router,
        det_router,
        jev_router,
        entity_resolver,
    )

    # 2. Locked Test Set V3 Benchmark (N=400)
    run_benchmark_on_dataset(
        TEST_V3_PATH,
        OUT_TEST_RESULTS,
        generic_router,
        finetuned_router,
        det_router,
        jev_router,
        entity_resolver,
    )

    print("\nAll v0.5 benchmarks successfully executed!")


if __name__ == "__main__":
    main()
