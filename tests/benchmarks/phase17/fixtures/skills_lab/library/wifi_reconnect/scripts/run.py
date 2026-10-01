"""
AstraRun Procedural Skill: wifi_reconnect
Safe standalone execution script. Reads args from JSON and outputs structured result.
"""
import sys
import json
import time
from pathlib import Path

def main():
    args_file = None
    dry_run = False
    simulate_fail = False

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--args" and i + 2 < len(sys.argv):
            args_file = sys.argv[i + 2]
        elif arg == "--simulate-error":
            simulate_fail = True

    params = {
        "ssid": "campus-guest",
        "target_host": "8.8.8.8",
        "timeout_seconds": 15
    }

    if args_file and Path(args_file).exists():
        with open(args_file, "r", encoding="utf-8") as f:
            user_args = json.load(f)
            params.update(user_args)
            if user_args.get("simulate_adapter_disabled"):
                simulate_fail = True

    if simulate_fail:
        err_res = {
            "status": "ERROR",
            "code": "ADAPTER_DISABLED",
            "message": "Wi-Fi interface 'Wi-Fi' is disabled in system control",
            "recommended_action": "enable_adapter",
            "interface": "Wi-Fi"
        }
        print(json.dumps(err_res))
        sys.exit(2)

    if dry_run:
        res = {
            "status": "DRY_RUN_SUCCESS",
            "skill": "wifi_reconnect",
            "validated_parameters": params
        }
        print(json.dumps(res))
        sys.exit(0)

    # Simulated successful connection & verification
    time.sleep(0.05)
    res = {
        "status": "SUCCESS",
        "skill": "wifi_reconnect",
        "connected_ssid": params["ssid"],
        "assigned_ip": "10.12.4.88",
        "ping_host": params["target_host"],
        "ping_latency_ms": 14.2,
        "packet_loss_percent": 0.0
    }
    print(json.dumps(res))
    sys.exit(0)

if __name__ == "__main__":
    main()
