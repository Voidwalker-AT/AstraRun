"""Local CLI Tool for labeling AstraRun training & evaluation data.

Enforces zero-cloud privacy: all data stays local on disk.
Labels:
  - Intent: 10-class taxonomy
  - Ambiguity: safe_to_resolve | ambiguous | unknown
  - Risk: LOW | MEDIUM | HIGH | BLOCKED
  - Entity: Optional target entity string or null
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

INTENTS = [
    "open_app",
    "open_folder",
    "open_url",
    "open_project",
    "find_file",
    "process_action",
    "system_action",
    "ai_query",
    "browser_action",
    "unknown"
]

AMBIGUITIES = ["safe_to_resolve", "ambiguous", "unknown"]
RISKS = ["LOW", "MEDIUM", "HIGH", "BLOCKED"]


def label_single_request(
    request: str,
    category: str = "custom",
    default_intent: str | None = None,
    default_ambiguity: str = "safe_to_resolve",
    default_risk: str = "LOW",
    default_entity: str | None = None
) -> dict[str, Any]:
    """Structure a labeled example following AstraRun v0.5 schema."""
    return {
        "request": request.strip(),
        "category": category.strip(),
        "expected_intent": default_intent or "unknown",
        "expected_ambiguity": default_ambiguity,
        "expected_risk": default_risk,
        "expected_entity": default_entity
    }


def interactive_label_cli(input_path: str, output_path: str) -> None:
    inp = Path(input_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not inp.exists():
        print(f"Error: input file {inp} not found.")
        sys.exit(1)

    items = []
    if inp.suffix == ".json":
        items = json.loads(inp.read_text(encoding="utf-8"))
    elif inp.suffix in (".jsonl", ".txt"):
        for line in inp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                items.append({"request": line})

    labeled_results = []
    print(f"Loaded {len(items)} items to label. Output: {out}")
    print("Commands: (1-10) for intent, 's' to skip, 'q' to quit & save.\n")

    for idx, it in enumerate(items, start=1):
        req = it.get("request", "")
        print(f"\n[{idx}/{len(items)}] Request: \"{req}\"")
        for i, name in enumerate(INTENTS, 1):
            print(f"  {i}. {name}")
        
        choice = input("Select Intent [1-10, s=skip, q=quit]: ").strip().lower()
        if choice == "q":
            break
        if choice == "s":
            continue
        try:
            intent_idx = int(choice) - 1
            chosen_intent = INTENTS[intent_idx]
        except (ValueError, IndexError):
            print("Invalid selection; defaulting to unknown.")
            chosen_intent = "unknown"

        # Ambiguity
        print("Ambiguity: 1. safe_to_resolve  2. ambiguous  3. unknown")
        amb_choice = input("Select Ambiguity [1-3, default 1]: ").strip()
        amb = AMBIGUITIES[int(amb_choice)-1] if amb_choice in ("1", "2", "3") else "safe_to_resolve"

        # Risk
        print("Risk: 1. LOW  2. MEDIUM  3. HIGH  4. BLOCKED")
        risk_choice = input("Select Risk [1-4, default 1]: ").strip()
        risk = RISKS[int(risk_choice)-1] if risk_choice in ("1", "2", "3", "4") else "LOW"

        # Entity
        entity = input("Target Entity (or Enter for None): ").strip() or None

        record = label_single_request(
            request=req,
            category=it.get("category", "curated"),
            default_intent=chosen_intent,
            default_ambiguity=amb,
            default_risk=risk,
            default_entity=entity
        )
        record["id"] = it.get("id", f"lbl_{idx:04d}")
        labeled_results.append(record)

    out.write_text(json.dumps(labeled_results, indent=2), encoding="utf-8")
    print(f"\nSaved {len(labeled_results)} labeled items to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstraRun Local Data Labeling Utility")
    parser.add_argument("--input", "-i", help="Input file (txt, json, jsonl)")
    parser.add_argument("--output", "-o", default="data/training/labeled_data.json", help="Output JSON path")
    args = parser.parse_args()

    if args.input:
        interactive_label_cli(args.input, args.output)
    else:
        print("Usage: python scripts/label_tool.py -i <input_file> -o <output_file>")
