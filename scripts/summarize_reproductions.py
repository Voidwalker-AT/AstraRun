import json
import pathlib

def main():
    data = json.load(open("docs/audit/F0_25F5_FAILURE_REPRODUCTION.json", encoding="utf-8"))
    fails = [d for d in data if d["isolated_reproduction"] == "FAILS"]
    succs = [d for d in data if d["isolated_reproduction"] == "SUCCEEDS"]
    print(f"Total: {len(data)}, Isolated FAILS: {len(fails)}, Isolated SUCCEEDS: {len(succs)}")
    print("\n--- Isolated FAILS ---")
    for d in fails:
        print(f"[{d['index']:02d}] {d['test_id']}")
        print(f"     Summary: {d['error_summary'][:100]}")
    print("\n--- Isolated SUCCEEDS ---")
    for d in succs:
        print(f"[{d['index']}] {d['test_id']}")

if __name__ == "__main__":
    main()
