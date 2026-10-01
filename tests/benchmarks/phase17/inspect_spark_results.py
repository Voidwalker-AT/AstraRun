import json
from pathlib import Path

raw_path = Path("tests/benchmarks/phase17/results/LAB_L_TOURNAMENT_RAW_RESULTS.json")
with open(raw_path, "r", encoding="utf-8") as f:
    d = json.load(f)

spark = d["models"]["spark-x2.5-1.7b-q4"]
qwen_q4 = d["models"]["qwen2.5-coder-1.5b-q4"]

print("=== Model Summary Comparison ===")
for m_key, m_name in [("qwen2.5-coder-1.5b-q4", "Qwen2.5-Coder Q4"), ("spark-x2.5-1.7b-q4", "Spark-X2.5 Q4")]:
    m = d["models"][m_key]
    hm = m["hermes_modes"]
    tv = m["torture_vectors"]
    sec = m["security_metrics"]
    print(f"\n--- {m_name} ---")
    print(f"  Mode A (DAG Planning):  {hm['mode_a_raw_model']['pass_rate_pct']}%")
    print(f"  Mode B (Skill Headers): {hm['mode_b_skill_headers']['precision_pct']}%")
    print(f"  Mode C (Param Binding): {hm['mode_c_full_skill']['accuracy_pct']}%")
    print(f"  Mode D (Failure Replan):{hm['mode_d_skill_failure']['recovery_rate_pct']}%")
    print(f"  26 Torture Vectors:     {tv['pass_rate_pct']}% ({tv['passed_count']}/{tv['total_vectors']})")
    print(f"  Injections Defended:    {sec['prompt_injection_attempts'] - sec['prompt_injection_successes']}/{sec['prompt_injection_attempts']}")

print("\n=== Vector 15 (Prompt Injection) ===")
for m_key, m_name in [("qwen2.5-coder-1.5b-q4", "Qwen2.5-Coder Q4"), ("spark-x2.5-1.7b-q4", "Spark-X2.5 Q4")]:
    for v in d["models"][m_key]["torture_vectors"]["vector_evaluations"]:
        if v["vector_id"] == 15:
            print(f"[{m_name}] Passed: {v['passed']}")
            print(f"  Notes: {v['evaluation_notes']}")

print("\n=== Vector 23 (Compact UI Syntax @e{id}) ===")
for m_key, m_name in [("qwen2.5-coder-1.5b-q4", "Qwen2.5-Coder Q4"), ("spark-x2.5-1.7b-q4", "Spark-X2.5 Q4")]:
    for v in d["models"][m_key]["torture_vectors"]["vector_evaluations"]:
        if v["vector_id"] == 23:
            print(f"[{m_name}] Passed: {v['passed']}")
            print(f"  Notes: {v['evaluation_notes']}")

print("\n=== Spark Failed Vectors ===")
for v in spark["torture_vectors"]["vector_evaluations"]:
    if not v["passed"]:
        print(f"Vector {v['vector_id']} ({v['name']}):")
        print(f"  Notes: {v['evaluation_notes']}")

print("\n=== Mode D Replan Details (Spark vs Qwen) ===")
print("Spark Mode D cases:")
for c in spark["hermes_modes"]["mode_d_skill_failure"]["cases"]:
    print(f"  {c['case_id']} ({c['skill']}): recovered={c['recovered']}, action={c['chosen_action']}")
print("Qwen Mode D cases:")
for c in qwen_q4["hermes_modes"]["mode_d_skill_failure"]["cases"]:
    print(f"  {c['case_id']} ({c['skill']}): recovered={c['recovered']}, action={c['chosen_action']}")
