import json
import httpx
from pathlib import Path
from astrarun.cognition.supervisor import ModelSupervisor
from astrarun.cognition.models import ModelRole

s = ModelSupervisor.get_instance()
ok = s.start_server(
    'qwen2.5-coder',
    r'E:\AI_Models\GGUF\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf',
    8089,
    ModelRole.DEEP,
    ngl=0,
    ctx_size=2048,
    timeout=20.0
)
print("Server ready:", ok)

resp = httpx.post(
    "http://127.0.0.1:8089/v1/chat/completions",
    json={
        "model": "qwen2.5-coder",
        "messages": [
            {"role": "system", "content": "You are AstraRun's reasoning core. Output strictly valid JSON."},
            {"role": "user", "content": "Provide a simple JSON object with keys 'status' and 'model'."}
        ],
        "temperature": 0.1,
        "max_tokens": 100
    },
    timeout=10.0
)
print("HTTP status:", resp.status_code)
content = resp.json()["choices"][0]["message"]["content"]
print("Model Output:\n", content)

s.stop_all_servers()
print("Server stopped cleanly.")
