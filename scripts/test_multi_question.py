"""Test multi-question Laya prediction (intent + ambiguity + risk in one forward pass)."""
import os
import sys
import time

os.environ["HF_HOME"] = "E:/AI_Models/HF_CACHE"
import laya

print("Loading Laya...")
t_load = time.perf_counter()
agent = laya.load("convaiinnovations/laya", device="cpu")
print(f"Loaded in {(time.perf_counter() - t_load):.2f}s")

questions = {
    "intent": {
        "type": "choice",
        "instructions": "Which action does the user intend?",
        "criteria": {
            "open_app": "Launch an installed desktop application",
            "open_folder": "Open a local filesystem folder",
            "open_url": "Navigate to a website URL",
            "unknown": "Ambiguous, out-of-scope, or unsupported"
        }
    },
    "ambiguity": {
        "type": "choice",
        "instructions": "Is this request safe and specific enough to resolve directly, or is it ambiguous/underspecified?",
        "criteria": {
            "safe_to_resolve": "Request contains clear target entity and specific action",
            "ambiguous": "Request uses unclear pronouns or lacks target information",
            "unknown": "Request is gibberish or unsupported"
        }
    },
    "risk": {
        "type": "choice",
        "instructions": "What is the consequence risk of executing this request?",
        "criteria": {
            "low": "Benign desktop application or navigation",
            "medium": "Modifies project or workspace configuration",
            "high": "Terminates process, deletes file, or changes system setting",
            "blocked": "Destructive system modification or dangerous command"
        }
    }
}

# Warmup
agent.predict("warmup query", questions)

test_queries = [
    "open notepad",
    "open it",
    "delete system32",
    "asdfgh",
    "kill port 3000"
]

print("\n--- Multi-Question Evaluation (Single Shared Forward Pass) ---")
for q in test_queries:
    t0 = time.perf_counter()
    res = agent.predict(q, questions)
    lat = (time.perf_counter() - t0) * 1000.0
    ans = res.get("answers", {})
    i_ans = ans.get("intent", {})
    a_ans = ans.get("ambiguity", {})
    r_ans = ans.get("risk", {})
    print(f"\nQuery: '{q}' [Latency: {lat:.1f}ms]")
    print(f"  -> Intent:    {i_ans.get('choice')} (conf: {i_ans.get('confidence', 0):.2f})")
    print(f"  -> Ambiguity: {a_ans.get('choice')} (conf: {a_ans.get('confidence', 0):.2f})")
    print(f"  -> Risk:      {r_ans.get('choice')} (conf: {r_ans.get('confidence', 0):.2f})")
