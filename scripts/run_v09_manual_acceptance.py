"""Run 25 canonical manual acceptance commands for AstraRun v0.9."""
import time
import json
from astrarun.app import AstraApplication
from astrarun.windows.policy import set_simulated_window_validation

def main():
    set_simulated_window_validation(True)
    commands = [
        "notepad",
        "calc",
        "code",
        "cmd",
        "history",
        "memory",
        "skills",
        "settings",
        "diagnostics",
        "what can you do?",
        "system status",
        "battery status",
        "disk status",
        "audio status",
        "network connections",
        "listening ports",
        "list windows",
        "foreground window",
        "snap left",
        "snap right",
        "maximize window",
        "snap to top left",
        "undo last window move",
        "kill process 1234",
        "format c:"
    ]

    app = AstraApplication()
    results = []

    print("=" * 70)
    print("ASTRARUN v0.9 — 25 MANUAL ACCEPTANCE COMMAND SUITE")
    print("=" * 70)

    for idx, cmd in enumerate(commands, 1):
        t0 = time.perf_counter()
        res = app.handle_request(cmd, origin_window=12345, dry_run=True)
        dt_ms = (time.perf_counter() - t0) * 1000
        
        status = res.type
        route_type = "fast_path" if res.type == "fast_path" else ("command" if res.type == "command" else "nlp")
        detail = (res.message or str(res.data or "") or str(res.risk.value if res.risk else ""))[:45]
        
        entry = {
            "num": idx,
            "command": cmd,
            "type": res.type,
            "success": res.success,
            "message": res.message,
            "detail": detail,
            "latency_ms": round(dt_ms, 3)
        }
        results.append(entry)
        print(f"[{idx:02d}/25] {cmd:26} | {res.type:18} | success={str(res.success):5} | {dt_ms:6.2f} ms | {detail}")

    app.shutdown()
    with open("benchmarks/v09_manual_acceptance_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("=" * 70)
    print("Results saved to benchmarks/v09_manual_acceptance_results.json")

if __name__ == "__main__":
    main()
