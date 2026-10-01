"""
Phase 17-S: Minimal Spark Smoke Test
Tests:
1. Model loading on GPU (-ngl 99)
2. /health check
3. /v1/chat/completions endpoint
4. Tokenization & Generation performance
"""

import sys
import os
import time
import json
import subprocess
import urllib.request
from pathlib import Path

RUNTIME_SERVER = Path(r"E:\AI_Runtimes\llama.cpp-spark\llama-server.exe")
MODEL_PATH = Path(r"E:\AI_Models\GGUF\Spark-X2.5-1.7B-Q4_K_M.gguf")
PORT = 8089

def query_gpu_vram():
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True
        )
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def main():
    print(f"=== Starting Spark-X2.5-1.7B Smoke Test ===")
    print(f"Server: {RUNTIME_SERVER}")
    print(f"Model:  {MODEL_PATH}")
    
    vram_before = query_gpu_vram()
    print(f"VRAM baseline: {vram_before:.1f} MB")
    
    cmd = [
        str(RUNTIME_SERVER),
        "-m", str(MODEL_PATH),
        "-c", "2048",
        "-ngl", "99",
        "--port", str(PORT),
        "--host", "127.0.0.1"
    ]
    
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for /health
    ready = False
    for _ in range(60):
        time.sleep(0.5)
        try:
            req = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1.0)
            if req.status == 200:
                ready = True
                break
        except Exception:
            pass
            
    cold_load_sec = time.perf_counter() - t0
    
    if not ready:
        print("FAILED: Server did not become ready.")
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=3)
        print("STDERR:")
        print(stderr.decode("utf-8", errors="replace"))
        sys.exit(1)
        
    vram_after_load = query_gpu_vram()
    print(f"Server READY in {cold_load_sec:.2f}s!")
    print(f"VRAM after load: {vram_after_load:.1f} MB (Delta: +{vram_after_load - vram_before:.1f} MB)")
    
    # Test /v1/chat/completions
    url = f"http://127.0.0.1:{PORT}/v1/chat/completions"
    payload = {
        "messages": [
            {"role": "system", "content": "You are a precise tool execution agent."},
            {"role": "user", "content": "Return a JSON object with key 'status' set to 'ok'."}
        ],
        "temperature": 0.0,
        "max_tokens": 64
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    t_req = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    lat_sec = time.perf_counter() - t_req
    
    print("\n=== Response Received ===")
    print(f"Status code: 200 (in {lat_sec:.3f}s)")
    message = body.get("choices", [{}])[0].get("message", {})
    content = message.get("content", "")
    print(f"Content: {content}")
    timings = body.get("timings", {})
    print(f"Timings: {json.dumps(timings, indent=2)}")
    
    # Terminate server
    proc.terminate()
    proc.wait(timeout=5)
    time.sleep(1.0)
    vram_after_term = query_gpu_vram()
    print(f"VRAM after termination: {vram_after_term:.1f} MB (Residual Delta: {vram_after_term - vram_before:.1f} MB)")
    print("\n=== SMOKE TEST PASSED ===")

if __name__ == "__main__":
    main()
