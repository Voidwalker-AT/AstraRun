"""Dataset generator and validation tool for AstraRun Neural NLP benchmarks.

Generates:
- benchmarks/nlp_neural/neural_nlp_dev_v1.json (>= 500 items)
- benchmarks/nlp_neural/neural_nlp_test_v1.json (>= 300 items)

Covers 9 linguistic classes:
1. simple_launch
2. compound_sequential
3. paraphrases_informal
4. coreference_pronoun
5. explicit_negation
6. conversational_ellipsis
7. ui_control_targeting
8. ambiguous_clarify
9. unsupported_out_of_domain
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path


def create_span(query: str, substring: str, occurrence: int = 1) -> tuple[int, int]:
    """Find the start and end character offsets of substring in query."""
    start = -1
    for _ in range(occurrence):
        start = query.find(substring, start + 1)
        if start == -1:
            raise ValueError(f"Substring '{substring}' not found in query '{query}'")
    return start, start + len(substring)


def generate_dataset(seed: int, target_count: int, prefix: str) -> list[dict]:
    rng = random.Random(seed)
    items: list[dict] = []
    item_id = 1

    # Base entity pools
    apps = [
        ("notepad", "Notepad"), ("calc", "Calculator"), ("calculator", "Calculator"),
        ("edge", "Microsoft Edge"), ("chrome", "Google Chrome"), ("code", "Visual Studio Code"),
        ("vscode", "Visual Studio Code"), ("terminal", "Windows Terminal"), ("cmd", "Command Prompt"),
        ("explorer", "File Explorer"), ("spotify", "Spotify"), ("taskmgr", "Task Manager"),
        ("paint", "Paint"), ("snippingtool", "Snipping Tool"), ("word", "Microsoft Word"),
        ("excel", "Microsoft Excel"), ("slack", "Slack"), ("discord", "Discord")
    ]
    folders = [
        ("downloads", "Downloads"), ("documents", "Documents"), ("desktop", "Desktop"),
        ("pictures", "Pictures"), ("workspace", "Workspace"), ("active projects", "Active Projects")
    ]
    urls = [
        ("github.com", "https://github.com"), ("youtube.com", "https://youtube.com"),
        ("google.com", "https://google.com"), ("reddit.com", "https://reddit.com")
    ]
    texts = [
        "hello world", "test 123", "pqr", "meeting notes for project review",
        "quick brown fox", "def process_data(records):", "import os, sys",
        "Status: System fully operational", "Please review PR #142", "urgent: check database logs",
        "TODO: refactor caching layer", "Antigravity workstation ready"
    ]
    snap_positions = ["left", "right", "top", "bottom", "top left", "top right", "bottom left", "bottom right"]
    keys = ["enter", "escape", "ctrl+s", "ctrl+a", "ctrl+c", "ctrl+v", "delete", "f5", "alt+f4"]

    # 1. Simple Single-Intent Commands (~20%)
    simple_templates = [
        ("open {app}", "open_app", "open", "app_name"),
        ("launch {app}", "open_app", "launch", "app_name"),
        ("start {app}", "open_app", "start", "app_name"),
        ("run {app}", "open_app", "run", "app_name"),
        ("bring up {app}", "open_app", "bring up", "app_name"),
        ("open {folder}", "open_folder", "open", "folder_name"),
        ("open {url}", "open_url", "open", "url"),
        ("minimize window", "minimize_window", "minimize", None),
        ("maximize window", "maximize_window", "maximize", None),
        ("restore window", "restore_window", "restore", None),
        ("close window", "close_window", "close", None),
        ("cpu status", "system_status", "status", None),
        ("ram usage", "system_status", "usage", None),
        ("battery level", "system_status", "level", None),
        ("mute volume", "system_volume", "mute", None),
    ]

    count_simple = int(target_count * 0.22)
    for _ in range(count_simple):
        tmpl, intent, verb, ent_type = rng.choice(simple_templates)
        if ent_type == "app_name":
            ent_val, _ = rng.choice(apps)
            q = tmpl.format(app=ent_val)
            s, e = create_span(q, ent_val)
            clauses = [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": false if False else False,
                "entities": [{"type": ent_type, "value": ent_val, "start": s, "end": e}],
                "payload": None,
                "raw_clause": q
            }]
        elif ent_type == "folder_name":
            ent_val, _ = rng.choice(folders)
            q = tmpl.format(folder=ent_val)
            s, e = create_span(q, ent_val)
            clauses = [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": False,
                "entities": [{"type": ent_type, "value": ent_val, "start": s, "end": e}],
                "payload": None,
                "raw_clause": q
            }]
        elif ent_type == "url":
            ent_val, _ = rng.choice(urls)
            q = tmpl.format(url=ent_val)
            s, e = create_span(q, ent_val)
            clauses = [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": False,
                "entities": [{"type": ent_type, "value": ent_val, "start": s, "end": e}],
                "payload": None,
                "raw_clause": q
            }]
        else:
            q = tmpl
            clauses = [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": False,
                "entities": [],
                "payload": None,
                "raw_clause": q
            }]

        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "simple_launch",
            "is_compound": False,
            "has_negation": False,
            "clauses": clauses
        })
        item_id += 1

    # 2. Compound Sequential Commands (~30%)
    compound_connectors = ["and", "then", "and then", ";"]
    count_compound = int(target_count * 0.32)
    for _ in range(count_compound):
        conn = rng.choice(compound_connectors)
        app_val, _ = rng.choice(apps)
        c_type = rng.choice(["launch_and_type", "launch_and_snap", "snap_and_focus", "triple_sequence"])

        if c_type == "launch_and_type":
            txt = rng.choice(texts)
            q = f"open {app_val} {conn} type {txt}"
            s_app, e_app = create_span(q, app_val)
            s_txt, e_txt = create_span(q, txt)
            clauses = [
                {
                    "sequence_index": 0,
                    "intent": "open_app",
                    "action_verb": "open",
                    "is_negated": False,
                    "entities": [{"type": "app_name", "value": app_val, "start": s_app, "end": e_app}],
                    "payload": None,
                    "raw_clause": f"open {app_val}"
                },
                {
                    "sequence_index": 1,
                    "intent": "type_text",
                    "action_verb": "type",
                    "is_negated": False,
                    "entities": [],
                    "payload": {"text": txt, "start": s_txt, "end": e_txt},
                    "raw_clause": f"type {txt}"
                }
            ]
        elif c_type == "launch_and_snap":
            pos = rng.choice(snap_positions)
            q = f"launch {app_val} {conn} snap {pos}"
            s_app, e_app = create_span(q, app_val)
            s_pos, e_pos = create_span(q, pos)
            clauses = [
                {
                    "sequence_index": 0,
                    "intent": "open_app",
                    "action_verb": "launch",
                    "is_negated": False,
                    "entities": [{"type": "app_name", "value": app_val, "start": s_app, "end": e_app}],
                    "payload": None,
                    "raw_clause": f"launch {app_val}"
                },
                {
                    "sequence_index": 1,
                    "intent": "snap_window",
                    "action_verb": "snap",
                    "is_negated": False,
                    "entities": [{"type": "snap_position", "value": pos, "start": s_pos, "end": e_pos}],
                    "payload": None,
                    "raw_clause": f"snap {pos}"
                }
            ]
        elif c_type == "snap_and_focus":
            pos = rng.choice(snap_positions)
            q = f"snap active window {pos} {conn} maximize it"
            s_pos, e_pos = create_span(q, pos)
            clauses = [
                {
                    "sequence_index": 0,
                    "intent": "snap_window",
                    "action_verb": "snap",
                    "is_negated": False,
                    "entities": [{"type": "snap_position", "value": pos, "start": s_pos, "end": e_pos}],
                    "payload": None,
                    "raw_clause": f"snap active window {pos}"
                },
                {
                    "sequence_index": 1,
                    "intent": "maximize_window",
                    "action_verb": "maximize",
                    "is_negated": False,
                    "entities": [{"type": "target_ref", "value": "it", "start": q.rfind("it"), "end": q.rfind("it") + 2}],
                    "payload": None,
                    "raw_clause": "maximize it"
                }
            ]
        else: # triple sequence
            pos = rng.choice(snap_positions)
            txt = rng.choice(texts[:5])
            q = f"open {app_val} {conn} snap {pos} and type {txt}"
            s_app, e_app = create_span(q, app_val)
            s_pos, e_pos = create_span(q, pos)
            s_txt, e_txt = create_span(q, txt)
            clauses = [
                {
                    "sequence_index": 0,
                    "intent": "open_app",
                    "action_verb": "open",
                    "is_negated": False,
                    "entities": [{"type": "app_name", "value": app_val, "start": s_app, "end": e_app}],
                    "payload": None,
                    "raw_clause": f"open {app_val}"
                },
                {
                    "sequence_index": 1,
                    "intent": "snap_window",
                    "action_verb": "snap",
                    "is_negated": False,
                    "entities": [{"type": "snap_position", "value": pos, "start": s_pos, "end": e_pos}],
                    "payload": None,
                    "raw_clause": f"snap {pos}"
                },
                {
                    "sequence_index": 2,
                    "intent": "type_text",
                    "action_verb": "type",
                    "is_negated": False,
                    "entities": [],
                    "payload": {"text": txt, "start": s_txt, "end": e_txt},
                    "raw_clause": f"type {txt}"
                }
            ]

        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "compound_sequential",
            "is_compound": True,
            "has_negation": False,
            "clauses": clauses
        })
        item_id += 1

    # 3. Paraphrases and Informal Syntax (~10%)
    informal_phrases = [
        ("can you please open {app}", "open_app", "open", "app"),
        ("hey astra fire up {app}", "open_app", "fire up", "app"),
        ("i need to write some notes in {app}", "open_app", "write", "app"),
        ("get {app} running right now", "open_app", "get running", "app"),
        ("show me my {folder} folder", "open_folder", "show", "folder"),
        ("take me to {folder}", "open_folder", "take", "folder"),
        ("navigate over to {url}", "open_url", "navigate", "url"),
        ("put the active window on the {pos}", "snap_window", "put", "pos"),
        ("dock this window to the {pos}", "snap_window", "dock", "pos"),
    ]
    count_informal = int(target_count * 0.10)
    for _ in range(count_informal):
        tmpl, intent, verb, ent_kind = rng.choice(informal_phrases)
        if ent_kind == "app":
            app_val, _ = rng.choice(apps)
            q = tmpl.format(app=app_val)
            s, e = create_span(q, app_val)
            ents = [{"type": "app_name", "value": app_val, "start": s, "end": e}]
        elif ent_kind == "folder":
            f_val, _ = rng.choice(folders)
            q = tmpl.format(folder=f_val)
            s, e = create_span(q, f_val)
            ents = [{"type": "folder_name", "value": f_val, "start": s, "end": e}]
        elif ent_kind == "url":
            u_val, _ = rng.choice(urls)
            q = tmpl.format(url=u_val)
            s, e = create_span(q, u_val)
            ents = [{"type": "url", "value": u_val, "start": s, "end": e}]
        else:
            p_val = rng.choice(snap_positions)
            q = tmpl.format(pos=p_val)
            s, e = create_span(q, p_val)
            ents = [{"type": "snap_position", "value": p_val, "start": s, "end": e}]

        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "paraphrases_informal",
            "is_compound": False,
            "has_negation": False,
            "clauses": [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": False,
                "entities": ents,
                "payload": None,
                "raw_clause": q
            }]
        })
        item_id += 1

    # 4. Explicit Negation Commands (~10%)
    negation_templates = [
        ("don't close {app}", "close_app", "close", "app_name", True),
        ("do not close {app}", "close_app", "close", "app_name", True),
        ("never close {app}", "close_app", "close", "app_name", True),
        ("close the window but don't save", "close_window", "close", None, True),
        ("open {app} and not {app2}", "open_app", "open", "app_name", True),
        ("type {txt} but do not press enter", "type_text", "type", "payload", True),
        ("minimize everything except {app}", "minimize_all", "minimize", "app_name", True),
    ]
    count_neg = int(target_count * 0.10)
    for _ in range(count_neg):
        tmpl, intent, verb, ent_kind, is_neg = rng.choice(negation_templates)
        app1, _ = rng.choice(apps)
        app2, _ = rng.choice([a for a in apps if a != app1])
        txt = rng.choice(texts[:4])

        if ent_kind == "app_name" and "{app2}" in tmpl:
            q = tmpl.format(app=app1, app2=app2)
            s1, e1 = create_span(q, app1)
            s2, e2 = create_span(q, app2)
            clauses = [
                {
                    "sequence_index": 0,
                    "intent": "open_app",
                    "action_verb": "open",
                    "is_negated": False,
                    "entities": [{"type": "app_name", "value": app1, "start": s1, "end": e1}],
                    "payload": None,
                    "raw_clause": f"open {app1}"
                },
                {
                    "sequence_index": 1,
                    "intent": "open_app",
                    "action_verb": "open",
                    "is_negated": True,
                    "entities": [{"type": "app_name", "value": app2, "start": s2, "end": e2}],
                    "payload": None,
                    "raw_clause": f"not {app2}"
                }
            ]
        elif ent_kind == "payload":
            q = tmpl.format(txt=txt)
            s_txt, e_txt = create_span(q, txt)
            clauses = [
                {
                    "sequence_index": 0,
                    "intent": "type_text",
                    "action_verb": "type",
                    "is_negated": False,
                    "entities": [],
                    "payload": {"text": txt, "start": s_txt, "end": e_txt},
                    "raw_clause": f"type {txt}"
                },
                {
                    "sequence_index": 1,
                    "intent": "press_key",
                    "action_verb": "press",
                    "is_negated": True,
                    "entities": [{"type": "key_name", "value": "enter", "start": q.rfind("enter"), "end": q.rfind("enter") + 5}],
                    "payload": None,
                    "raw_clause": "do not press enter"
                }
            ]
        elif ent_kind == "app_name":
            q = tmpl.format(app=app1)
            s1, e1 = create_span(q, app1)
            clauses = [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": True,
                "entities": [{"type": "app_name", "value": app1, "start": s1, "end": e1}],
                "payload": None,
                "raw_clause": q
            }]
        else:
            q = tmpl
            clauses = [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": False,
                "entities": [],
                "payload": None,
                "raw_clause": q
            }]

        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "explicit_negation",
            "is_compound": len(clauses) > 1,
            "has_negation": True,
            "clauses": clauses
        })
        item_id += 1

    # 5. Coreference & Pronoun Resolution (~8%)
    coref_templates = [
        ("open {app} then minimize it", "open_app", "minimize_window"),
        ("launch {app} and snap it to {pos}", "open_app", "snap_window"),
        ("find {app} and close that window", "open_app", "close_window"),
        ("switch to {app} and maximize it", "focus_window", "maximize_window"),
    ]
    count_coref = int(target_count * 0.08)
    for _ in range(count_coref):
        tmpl, int1, int2 = rng.choice(coref_templates)
        app_val, _ = rng.choice(apps)
        pos_val = rng.choice(snap_positions)
        if "{pos}" in tmpl:
            q = tmpl.format(app=app_val, pos=pos_val)
            s_app, e_app = create_span(q, app_val)
            s_pos, e_pos = create_span(q, pos_val)
            it_idx = q.find("it")
            clauses = [
                {
                    "sequence_index": 0,
                    "intent": int1,
                    "action_verb": "launch",
                    "is_negated": False,
                    "entities": [{"type": "app_name", "value": app_val, "start": s_app, "end": e_app}],
                    "payload": None,
                    "raw_clause": f"launch {app_val}"
                },
                {
                    "sequence_index": 1,
                    "intent": int2,
                    "action_verb": "snap",
                    "is_negated": False,
                    "entities": [
                        {"type": "pronoun_referent", "value": "it", "start": it_idx, "end": it_idx + 2, "referent_index": 0},
                        {"type": "snap_position", "value": pos_val, "start": s_pos, "end": e_pos}
                    ],
                    "payload": None,
                    "raw_clause": f"snap it to {pos_val}"
                }
            ]
        else:
            q = tmpl.format(app=app_val)
            s_app, e_app = create_span(q, app_val)
            ref_word = "that window" if "that window" in q else "it"
            s_ref, e_ref = create_span(q, ref_word)
            clauses = [
                {
                    "sequence_index": 0,
                    "intent": int1,
                    "action_verb": "open",
                    "is_negated": False,
                    "entities": [{"type": "app_name", "value": app_val, "start": s_app, "end": e_app}],
                    "payload": None,
                    "raw_clause": f"open {app_val}"
                },
                {
                    "sequence_index": 1,
                    "intent": int2,
                    "action_verb": int2.split("_")[0],
                    "is_negated": False,
                    "entities": [{"type": "pronoun_referent", "value": ref_word, "start": s_ref, "end": e_ref, "referent_index": 0}],
                    "payload": None,
                    "raw_clause": f"{int2.split('_')[0]} {ref_word}"
                }
            ]

        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "coreference_pronoun",
            "is_compound": True,
            "has_negation": False,
            "clauses": clauses
        })
        item_id += 1

    # 6. Conversational Ellipsis (~6%)
    ellipsis_queries = [
        ("and type pqr", "type_text", "type", {"text": "pqr"}),
        ("then maximize it", "maximize_window", "maximize", None),
        ("now snap right", "snap_window", "snap", {"position": "right"}),
        ("and press enter", "press_key", "press", {"key": "enter"}),
        ("also open chrome", "open_app", "open", {"app": "chrome"}),
        ("then close", "close_window", "close", None),
    ]
    count_ellipsis = int(target_count * 0.06)
    for _ in range(count_ellipsis):
        q, intent, verb, details = rng.choice(ellipsis_queries)
        ents = []
        payload = None
        if details and "text" in details:
            s, e = create_span(q, details["text"])
            payload = {"text": details["text"], "start": s, "end": e}
        elif details and "position" in details:
            s, e = create_span(q, details["position"])
            ents.append({"type": "snap_position", "value": details["position"], "start": s, "end": e})
        elif details and "key" in details:
            s, e = create_span(q, details["key"])
            ents.append({"type": "key_name", "value": details["key"], "start": s, "end": e})
        elif details and "app" in details:
            s, e = create_span(q, details["app"])
            ents.append({"type": "app_name", "value": details["app"], "start": s, "end": e})

        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "conversational_ellipsis",
            "is_compound": False,
            "has_negation": False,
            "clauses": [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": False,
                "entities": ents,
                "payload": payload,
                "raw_clause": q
            }]
        })
        item_id += 1

    # 7. UI Control Targeting (~4%)
    ui_templates = [
        ("click the Save button", "ui_click", "click", "Save"),
        ("click OK", "ui_click", "click", "OK"),
        ("press Cancel", "ui_click", "press", "Cancel"),
        ("focus the address bar", "ui_focus", "focus", "address bar"),
        ("select the first tab", "ui_select", "select", "first tab"),
    ]
    count_ui = int(target_count * 0.04)
    for _ in range(count_ui):
        q, intent, verb, target = rng.choice(ui_templates)
        s, e = create_span(q, target)
        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "ui_control_targeting",
            "is_compound": False,
            "has_negation": False,
            "clauses": [{
                "sequence_index": 0,
                "intent": intent,
                "action_verb": verb,
                "is_negated": False,
                "entities": [{"type": "ui_element", "value": target, "start": s, "end": e}],
                "payload": None,
                "raw_clause": q
            }]
        })
        item_id += 1

    # 8. Ambiguous / Clarification (~4%)
    ambig_queries = [
        "open the document",
        "restart it",
        "show my files",
        "open project",
        "switch window",
        "close",
        "open note",
    ]
    count_ambig = int(target_count * 0.04)
    for _ in range(count_ambig):
        q = rng.choice(ambig_queries)
        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "ambiguous_clarify",
            "is_compound": False,
            "has_negation": False,
            "clauses": [{
                "sequence_index": 0,
                "intent": "clarify",
                "action_verb": q.split()[0],
                "is_negated": False,
                "entities": [],
                "payload": None,
                "raw_clause": q
            }]
        })
        item_id += 1

    # 9. Unsupported / Out-of-Domain (~4%)
    unsupported_queries = [
        "make me a cup of coffee",
        "book a flight to New York",
        "what is the capital of France?",
        "solve this differential equation: dy/dx = y",
        "tell me a joke about programming",
        "order groceries online",
        "play chess against grandmaster engine",
    ]
    while len(items) < target_count:
        q = rng.choice(unsupported_queries)
        items.append({
            "id": f"{prefix}_{item_id:04d}",
            "query": q,
            "category": "unsupported_out_of_domain",
            "is_compound": False,
            "has_negation": False,
            "clauses": [{
                "sequence_index": 0,
                "intent": "unknown",
                "action_verb": q.split()[0],
                "is_negated": False,
                "entities": [],
                "payload": None,
                "raw_clause": q
            }]
        })
        item_id += 1

    return items


def main() -> None:
    output_dir = Path("benchmarks/nlp_neural")
    output_dir.mkdir(parents=True, exist_ok=True)

    dev_items = generate_dataset(seed=42, target_count=520, prefix="dev")
    test_items = generate_dataset(seed=999, target_count=320, prefix="test")

    dev_path = output_dir / "neural_nlp_dev_v1.json"
    test_path = output_dir / "neural_nlp_test_v1.json"

    with open(dev_path, "w", encoding="utf-8") as f:
        json.dump(dev_items, f, indent=2)

    with open(test_path, "w", encoding="utf-8") as f:
        json.dump(test_items, f, indent=2)

    dev_bytes = dev_path.read_bytes()
    test_bytes = test_path.read_bytes()
    dev_sha256 = hashlib.sha256(dev_bytes).hexdigest()
    test_sha256 = hashlib.sha256(test_bytes).hexdigest()

    manifest = {
        "milestone": "AstraRun v0.10.3",
        "dataset_name": "neural_nlp_v1",
        "created_at": "2026-09-28",
        "dev_set": {
            "path": str(dev_path),
            "count": len(dev_items),
            "sha256": dev_sha256
        },
        "test_set": {
            "path": str(test_path),
            "count": len(test_items),
            "sha256": test_sha256
        },
        "categories": [
            "simple_launch",
            "compound_sequential",
            "paraphrases_informal",
            "coreference_pronoun",
            "explicit_negation",
            "conversational_ellipsis",
            "ui_control_targeting",
            "ambiguous_clarify",
            "unsupported_out_of_domain"
        ]
    }

    manifest_path = output_dir / "dataset_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("Datasets generated and frozen successfully:")
    print(f"  Dev set:  {len(dev_items)} items -> {dev_path} (SHA-256: {dev_sha256[:12]}...)")
    print(f"  Test set: {len(test_items)} items -> {test_path} (SHA-256: {test_sha256[:12]}...)")


if __name__ == "__main__":
    main()
