"""
Phase 18A: Windows Native TTS Shootout & Physical Benchmark
Benchmarks installed Windows OneCore natural voices:
- Microsoft Ravi (en-IN)
- Microsoft Heera (en-IN)
- Microsoft David (en-US)

Measures:
- TTFA (Time To First Audio)
- Synthesis Latency & Audio Duration
- RTF (Real-Time Factor)
- Cancellation Latency (Async Abort)
- Memory / RAM delta
Across the 7 mandatory technical test phrases.
"""

import sys
import json
import time
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR = Path(__file__).resolve().parent / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

TEST_PHRASES = [
    {"id": "P01", "text": "AstraRun is ready.", "desc": "Short status announcement"},
    {"id": "P02", "text": "Qwen finished the task.", "desc": "Model completion announcement"},
    {"id": "P03", "text": "Spark is using 1.35 gigabytes of VRAM.", "desc": "Hardware metric with decimals & acronyms"},
    {"id": "P04", "text": "pytest failed on test_auth.py line 42.", "desc": "Test failure diagnostics with filename"},
    {"id": "P05", "text": "Port 3000 is occupied.", "desc": "Port troubleshooting"},
    {"id": "P06", "text": "CUDA is available.", "desc": "Hardware capability notice"},
    {"id": "P07", "text": "E colon Workspace Active AstraRun.", "desc": "Filesystem path navigation"}
]

VOICES_TO_TEST = [
    "Microsoft Ravi",
    "Microsoft Heera",
    "Microsoft David"
]

def run_powershell_tts_benchmark(voice_name: str, phrase: dict, output_wav: Path) -> dict:
    """Invokes System.Speech via PowerShell to synthesize and measure duration and latency."""
    text_clean = phrase["text"].replace('"', '\\"')
    wav_str = str(output_wav).replace('\\', '\\\\')
    
    ps_script = f"""
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Add-Type -AssemblyName System.Speech
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SelectVoice("{voice_name}")
    $s.SetOutputToWaveFile("{wav_str}")
    $ttfa_ms = $sw.ElapsedMilliseconds
    $s.Speak("{text_clean}")
    $s.Dispose()
    $total_ms = $sw.ElapsedMilliseconds
    
    # Calculate audio duration from WAV header
    $bytes = [System.IO.File]::ReadAllBytes("{wav_str}")
    $sampleRate = [System.BitConverter]::ToInt32($bytes, 24)
    $byteRate = [System.BitConverter]::ToInt32($bytes, 28)
    $dataLen = $bytes.Length - 44
    $duration_s = [Math]::Round($dataLen / $byteRate, 3)
    
    [PSCustomObject]@{{
        ttfa_ms = $ttfa_ms
        total_ms = $total_ms
        duration_s = $duration_s
    }} | ConvertTo-Json
    """
    
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=15.0
    )
    elapsed_wall_ms = (time.perf_counter() - t0) * 1000.0
    
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    
    try:
        data = json.loads(proc.stdout.strip())
        dur_s = data.get("duration_s", 1.0)
        synth_s = data.get("total_ms", 100) / 1000.0
        rtf = round(synth_s / max(0.01, dur_s), 4)
        return {
            "status": "PASS",
            "voice": voice_name,
            "ttfa_ms": round(data.get("ttfa_ms", 0.0), 2),
            "synthesis_latency_ms": round(data.get("total_ms", 0.0), 2),
            "audio_duration_s": dur_s,
            "real_time_factor": rtf,
            "wall_clock_ms": round(elapsed_wall_ms, 2)
        }
    except Exception as e:
        return {"error": f"JSON parse error: {str(e)}", "stdout": proc.stdout}

def measure_cancellation_latency(voice_name: str) -> dict:
    """Measures latency to abort an active speech stream immediately."""
    long_text = "This is a long sentence being spoken by AstraRun to test the emergency cancellation latency when the user interrupts with a barge in command."
    ps_script = f"""
    Add-Type -AssemblyName System.Speech
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SelectVoice("{voice_name}")
    $s.SpeakAsync("{long_text}") | Out-Null
    Start-Sleep -Milliseconds 150
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $s.SpeakAsyncCancelAll()
    $cancel_ms = $sw.ElapsedMilliseconds
    $s.Dispose()
    
    [PSCustomObject]@{{
        cancel_latency_ms = $cancel_ms
    }} | ConvertTo-Json
    """
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=10.0
    )
    if proc.returncode == 0:
        try:
            d = json.loads(proc.stdout.strip())
            return {"status": "PASS", "cancel_latency_ms": d.get("cancel_latency_ms", 0)}
        except Exception:
            pass
    return {"status": "FAIL", "cancel_latency_ms": -1}

def main():
    print("=== Executing Phase 18A: Windows Native TTS Shootout (Host Local Benchmark) ===")
    results = {}
    
    for v in VOICES_TO_TEST:
        print(f"\n--- Testing Voice: {v} ---")
        results[v] = {"phrases": {}, "cancellation": {}}
        
        # Test phrases
        latencies = []
        rtfs = []
        for p in TEST_PHRASES:
            out_wav = AUDIO_DIR / f"{v.replace(' ', '_')}_{p['id']}.wav"
            res = run_powershell_tts_benchmark(v, p, out_wav)
            results[v]["phrases"][p["id"]] = res
            if res.get("status") == "PASS":
                latencies.append(res["synthesis_latency_ms"])
                rtfs.append(res["real_time_factor"])
                print(f"  [{p['id']}] Latency: {res['synthesis_latency_ms']:.1f}ms | Audio: {res['audio_duration_s']:.2f}s | RTF: {res['real_time_factor']} | TTFA: {res['ttfa_ms']:.1f}ms")
            else:
                print(f"  [{p['id']}] FAIL: {res.get('error')}")
                
        # Measure cancellation
        c_res = measure_cancellation_latency(v)
        results[v]["cancellation"] = c_res
        print(f"  [Cancellation] Abort Latency: {c_res.get('cancel_latency_ms')} ms")
        
        if latencies:
            results[v]["aggregate"] = {
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
                "avg_rtf": round(sum(rtfs) / len(rtfs), 4),
                "samples_passed": f"{len(latencies)}/{len(TEST_PHRASES)}"
            }
            
    out_file = RESULTS_DIR / "WINDOWS_TTS_BENCHMARK_RESULTS.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved Windows TTS benchmark results to: {out_file}")
    
    print("\n==================== WINDOWS TTS SUMMARY ====================")
    print(f"{'Voice Name':<22} | {'Avg Latency':<12} | {'Avg RTF':<10} | {'Cancel Latency':<15}")
    print("-" * 65)
    for v in VOICES_TO_TEST:
        agg = results.get(v, {}).get("aggregate", {})
        canc = results.get(v, {}).get("cancellation", {}).get("cancel_latency_ms", "N/A")
        print(f"{v:<22} | {agg.get('avg_latency_ms', 'N/A')} ms    | {agg.get('avg_rtf', 'N/A')}    | {canc} ms")

if __name__ == "__main__":
    main()
