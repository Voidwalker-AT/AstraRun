"""High-throughput vectorized domain adaptation script for Laya on AstraRun workstation commands.

Adapts Laya's decision head and scoring parameters on AstraRun's 10-class intent taxonomy,
ambiguity resolution, and consequence risk classification.
Preserves ModernBERT-large encoder weights (frozen) for safety and zero catastrophic forgetting.
Saves the fine-tuned model canonically to E:/AI_Models/AstraRun-Laya.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

# Ensure line-buffering on stdout so prints appear immediately in logs
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

# Ensure canonical HF cache location per Platform Rule 9
os.environ.setdefault("HF_HOME", "E:/AI_Models/HF_CACHE")

import torch
import torch.nn.functional as F
from safetensors.torch import save_file

import laya
from laya.common import collate_items
from astrarun.routing.laya import INTENT_CRITERIA

BASE_SNAPSHOT_DIR = Path(
    r"E:\AI_Models\HF_CACHE\hub\models--convaiinnovations--laya\snapshots\55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851"
)
OUTPUT_MODEL_DIR = Path(r"E:\AI_Models\AstraRun-Laya")
TRAIN_DATA_PATH = Path(r"E:\Workspace\Active\AstraRun\data\training\train_dataset.json")
VAL_DATA_PATH = Path(r"E:\Workspace\Active\AstraRun\benchmarks\routing\validation\val_dataset.json")

AMBIGUITY_CRITERIA = {
    "safe_to_resolve": "Request contains clear target entity and specific action",
    "ambiguous": "Request uses unclear pronouns or lacks target information",
    "unknown": "Request is gibberish or unsupported",
}

RISK_CRITERIA = {
    "LOW": "Benign desktop application, file search, or navigation",
    "MEDIUM": "Modifies project or workspace configuration",
    "HIGH": "Terminates process, deletes file, or changes system setting",
    "BLOCKED": "Destructive system modification or dangerous command",
}

QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": "Which action does the user intend?",
        "criteria": INTENT_CRITERIA,
    },
    "ambiguity": {
        "type": "choice",
        "instructions": "Is this request safe and specific enough to resolve directly, or is it ambiguous/underspecified?",
        "criteria": AMBIGUITY_CRITERIA,
    },
    "risk": {
        "type": "choice",
        "instructions": "What is the consequence risk of executing this request?",
        "criteria": RISK_CRITERIA,
    },
}


def load_dataset(path: Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate(agent: laya.Agent, dataset: list[dict[str, Any]], batch_size: int = 16) -> dict[str, float]:
    """Evaluate current model accuracy using high-throughput batched inference."""
    correct_intent = 0
    correct_ambiguity = 0
    correct_risk = 0
    total = len(dataset)

    requests = [item["request"] for item in dataset]
    t0 = time.perf_counter()

    results = agent.predict_batch(requests, QUESTIONS, batch_size=batch_size)
    eval_time = time.perf_counter() - t0

    for item, res in zip(dataset, results):
        exp = item["expected"]
        ans = res.get("answers", {})

        pred_intent = ans.get("intent", {}).get("choice")
        if pred_intent == exp["intent"]:
            correct_intent += 1

        pred_amb = ans.get("ambiguity", {}).get("choice")
        if pred_amb == exp.get("ambiguity"):
            correct_ambiguity += 1

        pred_risk = ans.get("risk", {}).get("choice")
        if pred_risk == exp.get("risk"):
            correct_risk += 1

    return {
        "intent_accuracy": round(correct_intent / total, 4),
        "ambiguity_accuracy": round(correct_ambiguity / total, 4),
        "risk_accuracy": round(correct_risk / total, 4),
        "total": total,
        "eval_seconds": round(eval_time, 2),
    }


def train() -> None:
    print("=== AstraRun Laya Domain Adaptation (High-Throughput Vectorized) ===", flush=True)
    train_data = load_dataset(TRAIN_DATA_PATH)
    val_data = load_dataset(VAL_DATA_PATH)
    print(f"Loaded {len(train_data)} training items, {len(val_data)} validation items.", flush=True)

    print("Loading base Laya agent...", flush=True)
    t0 = time.perf_counter()
    agent = laya.load("convaiinnovations/laya", device="cpu")
    print(f"Loaded base model in {time.perf_counter() - t0:.2f}s", flush=True)

    print("\nRunning pre-training evaluation on validation set...", flush=True)
    pre_metrics = evaluate(agent, val_data, batch_size=16)
    print(f"  Zero-shot Intent Accuracy:    {pre_metrics['intent_accuracy']*100:.2f}%", flush=True)
    print(f"  Zero-shot Ambiguity Accuracy: {pre_metrics['ambiguity_accuracy']*100:.2f}%", flush=True)
    print(f"  Zero-shot Risk Accuracy:      {pre_metrics['risk_accuracy']*100:.2f}%", flush=True)
    print(f"  Evaluated in {pre_metrics['eval_seconds']}s", flush=True)

    # Freeze ModernBERT-large encoder
    for param in agent.model.encoder.parameters():
        param.requires_grad = False

    trainable_params = []
    for name, child in agent.model.named_children():
        if name != "encoder":
            for param in child.parameters():
                param.requires_grad = True
                trainable_params.append(param)

    trainable_count = sum(p.numel() for p in trainable_params)
    frozen_count = sum(p.numel() for p in agent.model.encoder.parameters())
    print(f"\nParameter Split: {frozen_count:,} frozen (encoder), {trainable_count:,} trainable (head+scorer)", flush=True)

    optimizer = torch.optim.AdamW(trainable_params, lr=3e-4, weight_decay=0.01)

    internal = {qid: agent._to_internal(spec) for qid, spec in QUESTIONS.items()}
    intent_keys = list(INTENT_CRITERIA.keys())
    ambiguity_keys = list(AMBIGUITY_CRITERIA.keys())
    risk_keys = list(RISK_CRITERIA.keys())

    # Pre-encode all training examples in batches of 16
    print("\nPre-encoding and caching encoder representations (batch size 16)...", flush=True)
    cached_batches = []
    agent.model.eval()

    chunk_size = 16
    t_cache_start = time.perf_counter()

    with torch.no_grad():
        for start_idx in range(0, len(train_data), chunk_size):
            chunk = train_data[start_idx : start_idx + chunk_size]
            per_state_items = []
            targets_intent = []
            targets_amb = []
            targets_risk = []

            for item in chunk:
                req = item["request"]
                exp = item["expected"]
                items = agent._encode_state(req, ["intent", "ambiguity", "risk"], internal)
                per_state_items.append(items)
                targets_intent.append(intent_keys.index(exp["intent"]))
                targets_amb.append(ambiguity_keys.index(exp.get("ambiguity", "unknown")))
                targets_risk.append(risk_keys.index(exp.get("risk", "LOW")))

            b = collate_items(per_state_items, agent.tok.pad_token_id)
            h_enc = agent.model.encoder(b["input_ids"], b["attention_mask"]).last_hidden_state

            cached_batches.append({
                "h_enc": h_enc,
                "attention_mask": b["attention_mask"],
                "marker_pos": b["marker_pos"],
                "marker_mask": b["marker_mask"],
                "qtype": b["qtype"],
                "num_states": len(chunk),
                "targets_intent": torch.tensor(targets_intent),
                "targets_amb": torch.tensor(targets_amb),
                "targets_risk": torch.tensor(targets_risk),
            })

    print(f"Encoded {len(train_data)} items into {len(cached_batches)} batches in {time.perf_counter() - t_cache_start:.2f}s", flush=True)

    print("\nTraining decision head and scoring parameters...", flush=True)
    epochs = 5
    agent.model.train()
    agent.model.encoder.eval()

    train_start = time.perf_counter()
    loss_history = []

    for epoch in range(1, epochs + 1):
        epoch_loss = 0.0
        # Shuffle batches
        batch_order = torch.randperm(len(cached_batches)).tolist()

        for b_idx in batch_order:
            batch = cached_batches[b_idx]
            optimizer.zero_grad()

            h = batch["h_enc"] + agent.model.type_emb(batch["qtype"])[:, None, :]
            pad = ~batch["attention_mask"].bool()
            for layer in agent.model.head.layers:
                h = layer(h, src_key_padding_mask=pad)

            idx = batch["marker_pos"].clamp(min=0)[:, :, None].expand(-1, -1, h.size(-1))
            m = torch.gather(h, 1, idx)
            logits = agent.model.scorer(m).squeeze(-1).float()
            logits = logits.masked_fill(~batch["marker_mask"], -1e4)

            # Each state has 3 consecutive rows: row 0: intent, row 1: ambiguity, row 2: risk
            n_states = batch["num_states"]
            intent_rows = logits[0::3, :len(intent_keys)]
            amb_rows = logits[1::3, :len(ambiguity_keys)]
            risk_rows = logits[2::3, :len(risk_keys)]

            loss_intent = F.cross_entropy(intent_rows, batch["targets_intent"])
            loss_amb = F.cross_entropy(amb_rows, batch["targets_amb"])
            loss_risk = F.cross_entropy(risk_rows, batch["targets_risk"])

            total_loss = loss_intent + 0.5 * loss_amb + 0.5 * loss_risk
            total_loss.backward()

            torch.nn.utils.clip_grad_norm_(trainable_params, max_norm=1.0)
            optimizer.step()

            epoch_loss += total_loss.item()

        avg_loss = epoch_loss / len(cached_batches)
        loss_history.append(avg_loss)
        print(f"  Epoch {epoch}/{epochs} - Avg Loss: {avg_loss:.4f}", flush=True)

    training_time = time.perf_counter() - train_start
    print(f"Training completed in {training_time:.2f}s", flush=True)

    print("\nRunning post-training evaluation on validation set...", flush=True)
    agent.model.eval()
    post_metrics = evaluate(agent, val_data, batch_size=16)
    print(f"  Fine-tuned Intent Accuracy:    {post_metrics['intent_accuracy']*100:.2f}% (was {pre_metrics['intent_accuracy']*100:.2f}%)", flush=True)
    print(f"  Fine-tuned Ambiguity Accuracy: {post_metrics['ambiguity_accuracy']*100:.2f}% (was {pre_metrics['ambiguity_accuracy']*100:.2f}%)", flush=True)
    print(f"  Fine-tuned Risk Accuracy:      {post_metrics['risk_accuracy']*100:.2f}% (was {pre_metrics['risk_accuracy']*100:.2f}%)", flush=True)
    print(f"  Evaluated in {post_metrics['eval_seconds']}s", flush=True)

    print(f"\nSaving fine-tuned model canonically to: {OUTPUT_MODEL_DIR}", flush=True)
    OUTPUT_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Copy metadata files and subdirectories from base snapshot
    src_config = BASE_SNAPSHOT_DIR / "rl_agent_config.json"
    dst_config = OUTPUT_MODEL_DIR / "rl_agent_config.json"
    shutil.copy2(src_config, dst_config)

    src_tok = BASE_SNAPSHOT_DIR / "tokenizer"
    dst_tok = OUTPUT_MODEL_DIR / "tokenizer"
    if not dst_tok.exists():
        shutil.copytree(src_tok, dst_tok)

    src_enc = BASE_SNAPSHOT_DIR / "encoder"
    dst_enc = OUTPUT_MODEL_DIR / "encoder"
    if not dst_enc.exists():
        shutil.copytree(src_enc, dst_enc)

    weights_path = OUTPUT_MODEL_DIR / "model.safetensors"
    print(f"Saving safetensors weights to: {weights_path}", flush=True)
    sd = agent.model.state_dict()
    save_file(sd, str(weights_path))

    report = {
        "base_model": "convaiinnovations/laya",
        "output_path": str(OUTPUT_MODEL_DIR),
        "train_samples": len(train_data),
        "val_samples": len(val_data),
        "epochs": epochs,
        "batch_size": chunk_size,
        "training_time_sec": round(training_time, 2),
        "initial_loss": round(loss_history[0], 4),
        "final_loss": round(loss_history[-1], 4),
        "pre_metrics": pre_metrics,
        "post_metrics": post_metrics,
    }
    report_path = OUTPUT_MODEL_DIR / "training_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Saved training report to: {report_path}", flush=True)

    print("\nVerifying fine-tuned model loading via laya.load...", flush=True)
    t_test = time.perf_counter()
    ft_agent = laya.load(str(OUTPUT_MODEL_DIR), device="cpu")
    print(f"Successfully loaded fine-tuned model in {time.perf_counter() - t_test:.2f}s!", flush=True)

    smoke_res = ft_agent.predict("open notepad", QUESTIONS)
    ans = smoke_res.get("answers", {})
    print("Smoke test 'open notepad':", flush=True)
    print(f"  Intent:    {ans.get('intent', {}).get('choice')} (conf: {ans.get('intent', {}).get('confidence')})", flush=True)
    print(f"  Ambiguity: {ans.get('ambiguity', {}).get('choice')} (conf: {ans.get('ambiguity', {}).get('confidence')})", flush=True)
    print(f"  Risk:      {ans.get('risk', {}).get('choice')} (conf: {ans.get('risk', {}).get('confidence')})", flush=True)
    print("\nDomain adaptation complete and verified!", flush=True)


if __name__ == "__main__":
    train()
