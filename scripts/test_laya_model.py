import os
import sys
import time

os.environ["HF_HOME"] = "E:/AI_Models/HF_CACHE"

import laya

print("Loading convaiinnovations/laya on CPU...", flush=True)
t0 = time.perf_counter()
try:
    agent = laya.load(model_id_or_path="convaiinnovations/laya", device="cpu")
    load_time = time.perf_counter() - t0
    print(f"Model loaded in {load_time:.2f}s", flush=True)

    state = "open my vivaldi project"
    questions = {
        "intent": {
            "type": "choice",
            "instructions": "Which action does the user intend?",
            "criteria": {
                "open_app": "Launch an installed desktop application",
                "open_folder": "Open a local folder in File Explorer",
                "open_url": "Navigate to a website URL",
                "open_project": "Open a software development workspace or project",
                "find_file": "Search for or open an individual document or file",
                "process_action": "Manage, restart, or kill running processes or ports",
                "system_action": "System, hardware, volume, or power actions",
                "ai_query": "Ask a conversational AI or coding question",
                "browser_action": "Search the web or perform in-browser actions",
                "unknown": "Ambiguous, unsupported, or unsafe request"
            }
        }
    }

    print("Running sample inference...", flush=True)
    t1 = time.perf_counter()
    result = agent.predict(state, questions)
    infer_time = time.perf_counter() - t1
    print(f"Inference completed in {infer_time*1000:.1f}ms", flush=True)
    print("Result:", result, flush=True)
except Exception as e:
    print("Error loading or running model:", type(e), e, flush=True)
    import traceback
    traceback.print_exc()
