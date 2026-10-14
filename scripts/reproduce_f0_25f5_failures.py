import xml.etree.ElementTree as ET
import subprocess
import json
import pathlib
import sys
import os

def resolve_nodeid(classname, name):
    parts = classname.split(".")
    # Case 1: tests.cognitive_spine.test_acceptance_3d_vis -> tests/cognitive_spine/test_acceptance_3d_vis.py
    if len(parts) >= 3:
        p1 = pathlib.Path(parts[0]) / parts[1] / f"{parts[2]}.py"
        if p1.exists():
            class_part = "::".join(parts[3:])
            if class_part:
                return f"{p1.as_posix()}::{class_part}::{name}", p1.as_posix()
            else:
                return f"{p1.as_posix()}::{name}", p1.as_posix()

    # Case 2: tests.test_generality_and_plugin.TestDynamicPluginDiscovery -> tests/test_generality_and_plugin.py::TestDynamicPluginDiscovery::name
    if len(parts) >= 2:
        p2 = pathlib.Path(parts[0]) / f"{parts[1]}.py"
        if p2.exists():
            class_part = "::".join(parts[2:])
            if class_part:
                return f"{p2.as_posix()}::{class_part}::{name}", p2.as_posix()
            else:
                return f"{p2.as_posix()}::{name}", p2.as_posix()

    # Case 3: fallback
    p3 = pathlib.Path(f"{'/'.join(parts)}.py")
    return f"{p3.as_posix()}::{name}", p3.as_posix()

def main():
    junit_path = pathlib.Path("docs/audit/junit_f0_25f4.xml")
    if not junit_path.exists():
        print(f"Error: {junit_path} does not exist.")
        sys.exit(1)

    tree = ET.parse(junit_path)
    root = tree.getroot()
    failed_testcases = []
    for tc in root.iter("testcase"):
        fail = tc.find("failure")
        err = tc.find("error")
        if fail is not None or err is not None:
            failed_testcases.append(tc)

    print(f"Found {len(failed_testcases)} failed testcases in {junit_path}.")

    results = []
    python_exe = sys.executable

    for idx, tc in enumerate(failed_testcases, 1):
        name = tc.attrib.get("name")
        classname = tc.attrib.get("classname")
        
        fail_node = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
        original_msg = fail_node.attrib.get("message", "") if fail_node is not None else ""
        original_text = fail_node.text if fail_node is not None else ""

        nodeid, file_path = resolve_nodeid(classname, name)
        print(f"[{idx}/{len(failed_testcases)}] Testing {nodeid}...")

        # Run isolated pytest
        cmd = [python_exe, "-m", "pytest", nodeid, "-v", "--tb=short", "--no-header"]
        
        run1 = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        run2 = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())

        repeatable = (run1.returncode == run2.returncode)
        isolated_status = "FAILS" if run1.returncode != 0 else "SUCCEEDS"

        output = run1.stdout + "\n" + run1.stderr
        last_lines = [l for l in output.splitlines() if l.strip()]
        error_summary = ""
        for line in reversed(last_lines):
            if "Error:" in line or "FAILED" in line or "AssertionError" in line:
                error_summary = line.strip()
                break

        prod_paths = []
        for line in output.splitlines():
            if "src/astrarun" in line.replace("\\", "/"):
                prod_paths.append(line.strip())

        results.append({
            "index": idx,
            "test_id": nodeid,
            "test_file": file_path,
            "test_name": name,
            "classname": classname,
            "original_message": original_msg[:300],
            "isolated_reproduction": isolated_status,
            "returncode_run1": run1.returncode,
            "returncode_run2": run2.returncode,
            "repeatable": repeatable,
            "error_summary": error_summary,
            "production_call_paths": prod_paths[:5],
            "output_tail": "\n".join(last_lines[-15:])
        })

    out_file = pathlib.Path("docs/audit/F0_25F5_FAILURE_REPRODUCTION.json")
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Reproduction results for {len(results)} tests written to {out_file}")

if __name__ == "__main__":
    main()
