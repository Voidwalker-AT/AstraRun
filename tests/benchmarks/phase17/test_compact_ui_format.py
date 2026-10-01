"""
Phase 17-T: Compact UI Format Retest (@e{id})
Tests Qwen2.5-Coder-1.5B and Spark-X2.5-1.7B across 3 conditions:
Condition A: Zero-shot baseline
Condition B: 20-token concise system instruction defining @e{id}
Condition C: Two few-shot examples
"""

import sys
import json
import urllib.request
import subprocess
import time
from pathlib import Path

LLAMA_SERVER_QWEN = Path(r"E:\OllamaApp\lib\ollama\llama-server.exe")
LLAMA_SERVER_SPARK = Path(r"E:\AI_Runtimes\llama.cpp-spark\llama-server.exe")
GGUF_DIR = Path(r"E:\AI_Models\GGUF")
RESULTS_DIR = Path(__file__).resolve().parent / "results"

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

PROMPT = "The UI tree contains: @e14 Button 'Connect' [100, 200, 80, 30]. Emit a JSON action to click this button: {\"action\": \"click\", \"target\": \"@e{id}\"}."

CONDITIONS = {
    "A_ZERO_SHOT": {
        "messages": [
            {"role": "user", "content": PROMPT}
        ]
    },
    "B_SYSTEM_INSTRUCTION": {
        "messages": [
            {
                "role": "system",
                "content": "Target UI elements by their exact compact index '@e{id}' (e.g. '@e14'). Never alter or omit the '@e' prefix."
            },
            {"role": "user", "content": PROMPT}
        ]
    },
    "C_FEW_SHOT": {
        "messages": [
            {
                "role": "system",
                "content": "Target UI elements by their exact compact index '@e{id}'. Output JSON only."
            },
            {"role": "user", "content": "The UI tree contains: @e3 Button 'Submit'. Click it."},
            {"role": "assistant", "content": '{"action": "click", "target": "@e3"}'},
            {"role": "user", "content": "The UI tree contains: @e19 Checkbox 'Remember'. Click it."},
            {"role": "assistant", "content": '{"action": "click", "target": "@e19"}'},
            {"role": "user", "content": PROMPT}
        ]
    }
}

class ServerManager:
    def __init__(self, cfg: dict, port: int = 8089):
        self.cfg = cfg
        self.port = port
        self.proc = None

    def start(self):
        cmd = [
            str(self.cfg["server"]),
            "-m", str(self.cfg["path"]),
            "-c", "2048",
            "-ngl", "99",
            "--port", str(self.port),
            "--host", "127.0.0.1"
        ]
        cmd.extend(self.cfg["extra_args"])
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 20.0:
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

    def generate(self, messages: list) -> str:
        url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
        payload = {"messages": messages, "max_tokens": 128, "temperature": 0.0, "seed": 42}
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        msg = body.get("choices", [{}])[0].get("message", {})
        return msg.get("content", "") or msg.get("reasoning_content", "")

def main():
    print("=== Executing Phase 17-T: Compact UI Format Retest (@e{id}) ===")
    results = {}

    for model_cfg in MODELS:
        m_id = model_cfg["model_id"]
        print(f"\n--- Testing Model: {model_cfg['name']} ---")
        srv = ServerManager(model_cfg, port=8089)
        if not srv.start():
            print(f"  Failed to start server for {m_id}")
            continue

        results[m_id] = {}
        try:
            for cond_name, cond_data in CONDITIONS.items():
                out = srv.generate(cond_data["messages"])
                passed = "@e14" in out
                print(f"  [{'PASS' if passed else 'FAIL'}] {cond_name}:")
                print(f"      Output: {out.strip()[:100]}")
                results[m_id][cond_name] = {
                    "passed": passed,
                    "output": out.strip()
                }
        finally:
            srv.stop()
            time.sleep(1.0)

    out_file = RESULTS_DIR / "COMPACT_UI_RETEST_RESULTS.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved Compact UI results to: {out_file}")

if __name__ == "__main__":
    main()
