"""
Phase 17-T: Replan Evaluator Suite v1.1.1
Evaluates Mode-D Skill Failure & Adaptive Replanning based on STRUCTURED DECISION:
- proposed recovery action (extracted from structured payload or action decision)
- whether prohibited failing action is actually re-executed
- whether recovery satisfies the observation
- whether it terminates appropriately
Preserves v1.1.0 results while producing v1.1.1 corrected Mode-D scores.
"""

import sys
import json
import re
import urllib.request
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

BENCHMARK_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BENCHMARK_DIR / "results"
FIXTURES_DIR = BENCHMARK_DIR / "fixtures"

SUITE_V110_PATH = FIXTURES_DIR / "frozen_tournament_suite.json"

LLAMA_SERVER_QWEN = Path(r"E:\OllamaApp\lib\ollama\llama-server.exe")
LLAMA_SERVER_SPARK = Path(r"E:\AI_Runtimes\llama.cpp-spark\llama-server.exe")
GGUF_DIR = Path(r"E:\AI_Models\GGUF")

MODELS = [
    {
        "model_id": "qwen2.5-coder-1.5b-q4",
        "name": "Qwen2.5-Coder-1.5B-Instruct-Q4_K_M",
        "path": GGUF_DIR / "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "server": LLAMA_SERVER_QWEN,
        "extra_args": []
    },
    {
        "model_id": "spark-x2.5-1.7b-q4",
        "name": "Spark-X2.5-1.7B-Q4_K_M",
        "path": GGUF_DIR / "Spark-X2.5-1.7B-Q4_K_M.gguf",
        "server": LLAMA_SERVER_SPARK,
        "extra_args": ["--reasoning", "off"]
    }
]

def extract_json_block(text: str) -> Optional[Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    first_b = text.find("{")
    last_b = text.rfind("}")
    if first_b != -1 and last_b != -1 and last_b > first_b:
        try:
            return json.loads(text[first_b:last_b+1])
        except Exception:
            pass
    return None

class LocalServer:
    def __init__(self, cfg: dict, port: int = 8089):
        self.cfg = cfg
        self.port = port
        self.proc = None

    def start(self):
        cmd = [
            str(self.cfg["server"]),
            "-m", str(self.cfg["path"]),
            "-c", "4096",
            "-ngl", "99",
            "--port", str(self.port),
            "--host", "127.0.0.1"
        ]
        cmd.extend(self.cfg["extra_args"])
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 25.0:
            try:
                req = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1.0)
                if req.status == 200:
                    return True
            except Exception:
                time.sleep(0.3)
        return False

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5.0)
            except Exception:
                self.proc.kill()
            self.proc = None

    def generate(self, messages: List[Dict[str, str]], max_tokens: int = 256) -> str:
        url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "seed": 42,
            "stream": False
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        msg = body.get("choices", [{}])[0].get("message", {})
        content = msg.get("content", "") or msg.get("reasoning_content", "")
        return content

def evaluate_replan_v111(server: LocalServer, mode_d_cases: list) -> dict:
    cases_result = []
    successful_recoveries = 0

    for case in mode_d_cases:
        sys_msg = (
            "You are AstraRun's failure recovery engine.\n"
            "A step in the procedural skill failed with an error payload.\n"
            "Formulate an adaptive recovery action. Do NOT repeat the exact failing action in a blind loop.\n"
            "Output format: `{\"diagnosis\": \"<reason>\", \"recovery_action\": \"<action>\"}`"
        )
        user_msg = f"Skill '{case['skill']}' failed with error: {json.dumps(case['error_payload'])}"
        out = server.generate([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}], max_tokens=128)
        
        parsed = extract_json_block(out)
        rec_action = ""
        diagnosis = ""
        if isinstance(parsed, dict):
            rec_action = str(parsed.get("recovery_action", "")).strip()
            diagnosis = str(parsed.get("diagnosis", "")).strip()
        else:
            rec_action = out.strip()

        prohibited_action = case["prohibited_action"].lower()
        allowed_actions = [a.lower() for a in case.get("allowed_actions", [case.get("expected_recovery_action", "")])]

        # STRUCTURED DECISION EVALUATION:
        # 1. Prohibited action re-execution check ONLY applies to the proposed action decision, NOT diagnostic prose.
        re_executed_prohibited = False
        action_lower = rec_action.lower()
        
        # Check if the chosen action is predominantly the prohibited action
        if prohibited_action in action_lower:
            # Check if it was preceded by an allowed negation or alternative phrase (e.g. "do not execute X", "replace X with Y")
            # If the action itself IS the prohibited action:
            clean_action = re.sub(r"[^a-z0-9_]", " ", action_lower).split()
            if prohibited_action in clean_action and not any(allowed in action_lower for allowed in allowed_actions):
                re_executed_prohibited = True

        # 2. Recovery satisfies observation (normalized token check)
        norm_action = re.sub(r"[^a-z0-9]", " ", action_lower)
        action_tokens = set(norm_action.split())
        satisfies_observation = False
        for allowed in allowed_actions:
            norm_allowed = re.sub(r"[^a-z0-9]", " ", allowed)
            allowed_tokens = set(w for w in norm_allowed.split() if len(w) > 2)
            if norm_allowed in norm_action or allowed in action_lower:
                satisfies_observation = True
                break
            # Key action keywords match
            if allowed_tokens and len(allowed_tokens.intersection(action_tokens)) >= min(2, len(allowed_tokens)):
                satisfies_observation = True
                break

        # 3. Appropriate termination / non-infinite-loop
        terminates_appropriately = not re_executed_prohibited and (satisfies_observation or "abort" in action_lower or "skip" in action_lower or "enable" in action_lower or "request" in action_lower)

        recovery_ok = satisfies_observation and not re_executed_prohibited and terminates_appropriately
        if recovery_ok:
            successful_recoveries += 1

        cases_result.append({
            "case_id": case["id"],
            "skill": case["skill"],
            "injected_error": case["error_payload"]["code"],
            "raw_output": out,
            "parsed_recovery_action": rec_action,
            "parsed_diagnosis": diagnosis,
            "re_executed_prohibited": re_executed_prohibited,
            "satisfies_observation": satisfies_observation,
            "recovery_ok": recovery_ok
        })

    return {
        "pass_rate_pct": round((successful_recoveries / len(mode_d_cases)) * 100.0, 2),
        "successful_recoveries": successful_recoveries,
        "total_cases": len(mode_d_cases),
        "cases": cases_result
    }

def main():
    print("=== Executing Phase 17-T: Mode-D Structured Replan Evaluator (Suite v1.1.1) ===")
    with open(SUITE_V110_PATH, "r", encoding="utf-8") as f:
        suite = json.load(f)
    mode_d_cases = suite["hermes_modes"]["mode_d_skill_failure"]

    results = {}
    for model_cfg in MODELS:
        m_id = model_cfg["model_id"]
        print(f"\nEvaluating Replan v1.1.1 for: {model_cfg['name']}...")
        srv = LocalServer(model_cfg, port=8089)
        ready = srv.start()
        if not ready:
            print(f"  [ERROR] Server failed to start for {m_id}")
            results[m_id] = {"status": "FAIL_TO_START"}
            continue
        try:
            res = evaluate_replan_v111(srv, mode_d_cases)
            results[m_id] = res
            print(f"  --> Pass Rate (v1.1.1 Structured): {res['pass_rate_pct']}% ({res['successful_recoveries']}/{res['total_cases']})")
            for c in res["cases"]:
                status = "PASS" if c["recovery_ok"] else "FAIL"
                print(f"      [{status}] {c['case_id']} ({c['skill']}): {c['parsed_recovery_action'][:80]}")
        finally:
            srv.stop()
            time.sleep(1.0)

    out_file = RESULTS_DIR / "REPLAN_V111_RESULTS.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved v1.1.1 Replan results to: {out_file}")

if __name__ == "__main__":
    main()
