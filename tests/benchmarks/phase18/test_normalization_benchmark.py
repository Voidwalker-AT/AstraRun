"""
Phase 18A: Benchmark for Deterministic Transcript Entity Normalizer
Evaluates the 13 core technical command vectors:
- Raw ASR output (simulating common phonetic & spacing errors)
- Normalized output (processed through stt_normalizer.py)
Measures:
- Entity Preservation (EP %)
- Command Intent Preservation (CIP %)
- Word Error Rate (WER %)
- Technical Token Accuracy (TTA %)
"""

import sys
import json
from pathlib import Path
from stt_normalizer import (
    normalize_transcript,
    calculate_wer,
    calculate_intent_preservation,
    calculate_entity_preservation,
    calculate_technical_token_accuracy
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 13 Technical Vectors with realistic simulated raw ASR outputs
TEST_CASES = [
    {
        "id": "C01",
        "canonical": "open Vivaldi",
        "raw_asr": "open vivaldi",
        "intent": "open",
        "critical_entities": ["Vivaldi"],
        "technical_tokens": ["vivaldi"]
    },
    {
        "id": "C02",
        "canonical": "open my deep learning project",
        "raw_asr": "open my deep learning project",
        "intent": "open",
        "critical_entities": ["deep learning"],
        "technical_tokens": ["deep", "learning"]
    },
    {
        "id": "C03",
        "canonical": "run pytest",
        "raw_asr": "run pie test",
        "intent": "run",
        "critical_entities": ["pytest"],
        "technical_tokens": ["pytest"]
    },
    {
        "id": "C04",
        "canonical": "kill whatever is using port 3000",
        "raw_asr": "kill whatever is using port three thousand",
        "intent": "kill",
        "critical_entities": ["port 3000"],
        "technical_tokens": ["port", "3000"]
    },
    {
        "id": "C05",
        "canonical": "connect to Campus Guest",
        "raw_asr": "connect to campus guest",
        "intent": "connect",
        "critical_entities": ["Campus Guest"],
        "technical_tokens": ["campus", "guest"]
    },
    {
        "id": "C06",
        "canonical": "open E:\\Workspace\\Active\\AstraRun",
        "raw_asr": "open e colon workspace active astrarun",
        "intent": "open",
        "critical_entities": ["E:\\Workspace\\Active\\AstraRun"],
        "technical_tokens": ["workspace", "astrarun"]
    },
    {
        "id": "C07",
        "canonical": "run the CUDA benchmark",
        "raw_asr": "run the cuda benchmark",
        "intent": "run",
        "critical_entities": ["CUDA"],
        "technical_tokens": ["cuda"]
    },
    {
        "id": "C08",
        "canonical": "use Qwen for this",
        "raw_asr": "use cue when for this",
        "intent": "use",
        "critical_entities": ["Qwen"],
        "technical_tokens": ["qwen"]
    },
    {
        "id": "C09",
        "canonical": "ask Spark to inspect it",
        "raw_asr": "ask spark to inspect it",
        "intent": "ask",
        "critical_entities": ["Spark"],
        "technical_tokens": ["spark"]
    },
    {
        "id": "C10",
        "canonical": "Q4_K_M",
        "raw_asr": "q four k m",
        "intent": "q4_k_m",
        "critical_entities": ["Q4_K_M"],
        "technical_tokens": ["q4_k_m"]
    },
    {
        "id": "C11",
        "canonical": "git status",
        "raw_asr": "get status",
        "intent": "git status",
        "critical_entities": ["git status"],
        "technical_tokens": ["git", "status"]
    },
    {
        "id": "C12",
        "canonical": "open VS Code",
        "raw_asr": "open v s code",
        "intent": "open",
        "critical_entities": ["VS Code"],
        "technical_tokens": ["vs code"]
    },
    {
        "id": "C13",
        "canonical": "run nvidia-smi",
        "raw_asr": "run nvidia s m i",
        "intent": "run",
        "critical_entities": ["nvidia-smi"],
        "technical_tokens": ["nvidia-smi"]
    }
]

def main():
    print("=== Executing Phase 18A: Transcript Entity Normalization Benchmark ===")
    
    raw_ep_scores = []
    norm_ep_scores = []
    raw_tta_scores = []
    norm_tta_scores = []
    
    records = []
    
    for tc in TEST_CASES:
        canonical = tc["canonical"]
        raw = tc["raw_asr"]
        norm = normalize_transcript(raw)
        
        # Raw metrics
        raw_ep, raw_missing = calculate_entity_preservation(tc["critical_entities"], raw)
        raw_tta = calculate_technical_token_accuracy(tc["technical_tokens"], raw)
        raw_cip = calculate_intent_preservation(tc["intent"], raw)
        
        # Normalized metrics
        norm_ep, norm_missing = calculate_entity_preservation(tc["critical_entities"], norm)
        norm_tta = calculate_technical_token_accuracy(tc["technical_tokens"], norm)
        norm_cip = calculate_intent_preservation(tc["intent"], norm)
        
        raw_ep_scores.append(raw_ep)
        norm_ep_scores.append(norm_ep)
        raw_tta_scores.append(raw_tta)
        norm_tta_scores.append(norm_tta)
        
        print(f"\n[{tc['id']}] Canonical:  '{canonical}'")
        print(f"      Raw ASR:    '{raw}' -> EP: {raw_ep}% | TTA: {raw_tta}%")
        print(f"      Normalized: '{norm}' -> EP: {norm_ep}% | TTA: {norm_tta}%")
        
        records.append({
            "id": tc["id"],
            "canonical": canonical,
            "raw_asr": raw,
            "normalized": norm,
            "raw_ep": raw_ep,
            "norm_ep": norm_ep,
            "raw_tta": raw_tta,
            "norm_tta": norm_tta
        })
        
    avg_raw_ep = round(sum(raw_ep_scores) / len(raw_ep_scores), 1)
    avg_norm_ep = round(sum(norm_ep_scores) / len(norm_ep_scores), 1)
    avg_raw_tta = round(sum(raw_tta_scores) / len(raw_tta_scores), 1)
    avg_norm_tta = round(sum(norm_tta_scores) / len(norm_tta_scores), 1)
    
    summary = {
        "total_cases": len(TEST_CASES),
        "raw_entity_preservation_pct": avg_raw_ep,
        "normalized_entity_preservation_pct": avg_norm_ep,
        "entity_preservation_delta_pct": round(avg_norm_ep - avg_raw_ep, 1),
        "raw_technical_token_accuracy_pct": avg_raw_tta,
        "normalized_technical_token_accuracy_pct": avg_norm_tta,
        "records": records
    }
    
    out_file = RESULTS_DIR / "NORMALIZATION_BENCHMARK_RESULTS.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved Normalization benchmark results to: {out_file}")
    
    print("\n==================== NORMALIZATION IMPACT ====================")
    print(f"Raw Entity Preservation:        {avg_raw_ep}%")
    print(f"Normalized Entity Preservation: {avg_norm_ep}%")
    print(f"Empirical Delta:                +{round(avg_norm_ep - avg_raw_ep, 1)}% improvement!")
    print(f"Raw Technical Token Accuracy:   {avg_raw_tta}%")
    print(f"Normalized Tech Token Accuracy: {avg_norm_tta}%")
    print("==============================================================")

if __name__ == "__main__":
    main()
