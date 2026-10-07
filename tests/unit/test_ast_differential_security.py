"""Differential AST Security Tests for AstraRun 1.0.

Verifies that ASTInspector and ASTCodePolicy enforce identical security decisions
across a comprehensive corpus of safe computational scripts and adversarial attack vectors.
Zero semantic divergence permitted between tools.ast_inspector and security.policies.
"""

import pytest
from astrarun.security.models import ActionGateVerdict
from astrarun.security.policies import ASTCodePolicy
from astrarun.tools.ast_inspector import ASTInspector


SAFE_SCRIPTS = [
    # 1. Pathlib and JSON file operations
    """
import json
from pathlib import Path

p = Path("output.json")
p.write_text(json.dumps({"status": "ok", "count": 42}))
""",
    # 2. CSV processing and statistics
    """
import csv
import statistics

data = [10.5, 20.3, 30.8, 15.2]
mean_val = statistics.mean(data)
with open("stats.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "value"])
    writer.writerow(["mean", mean_val])
""",
    # 3. Platform and safe os queries (os.cpu_count)
    """
import os
import platform

cores = os.cpu_count()
system = platform.system()
print(f"System: {system}, Cores: {cores}")
""",
    # 4. Math, time, and numerical calculations
    """
import math
import time

t0 = time.time()
res = [math.sqrt(i) for i in range(100)]
elapsed = time.time() - t0
""",
    # 5. Numpy array operations
    """
import numpy as np

arr = np.linspace(0, 10, 50)
total = np.sum(arr * 2.5)
""",
    # 6. Matplotlib Agg headless plotting
    """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.figure()
plt.plot([1, 2, 3], [4, 5, 6])
plt.savefig("plot.png")
plt.close()
""",
    # 7. Environment variable reading (governed output directory)
    """
import os
from pathlib import Path

out_dir = Path(os.environ.get("ASTRARUN_OUTPUT_DIR", "."))
(out_dir / "deliverable.txt").write_text("Completed successfully")
""",
]


ADVERSARIAL_SCRIPTS = [
    # 1. Raw socket connection
    ("""
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", 80))
""", "socket"),

    # 2. Subprocess execution
    ("""
import subprocess
subprocess.run(["cmd.exe", "/c", "dir"])
""", "subprocess"),

    # 3. ctypes kernel call
    ("""
import ctypes
ctypes.windll.kernel32.ExitProcess(0)
""", "ctypes"),

    # 4. Windows registry mutation
    ("""
import winreg
key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software")
""", "winreg"),

    # 5. Dynamic code evaluation via eval
    ("""
cmd = "print('hacked')"
eval(cmd)
""", "eval"),

    # 6. Dynamic code execution via exec
    ("""
payload = "x = 10"
exec(payload)
""", "exec"),

    # 7. Dynamic import via __import__
    ("""
mod = __import__("subprocess")
mod.Popen("calc.exe")
""", "__import__"),

    # 8. Command execution via os.system
    ("""
import os
os.system("whoami")
""", "os.system"),

    # 9. Pipe execution via os.popen
    ("""
import os
f = os.popen("netstat -an")
print(f.read())
""", "os.popen"),

    # 10. Direct import of protected Trust Kernel modules
    ("""
from astrarun.security.trust_kernel import mutate_trust
mutate_trust()
""", "Trust Kernel"),
]


def test_safe_scripts_differential_agreement():
    inspector = ASTInspector()
    policy = ASTCodePolicy(inspector=inspector)

    for idx, script in enumerate(SAFE_SCRIPTS, 1):
        # 1. Inspector verdict
        ast_res = inspector.inspect(script)
        assert ast_res.is_safe, f"Safe script #{idx} falsely rejected by ASTInspector: {ast_res.violations}"

        # 2. Policy verdict
        verdict, reason, risk = policy.evaluate_code(script)
        assert verdict == ActionGateVerdict.ALLOW, f"Safe script #{idx} falsely rejected by ASTCodePolicy: {reason}"


def test_adversarial_scripts_differential_agreement():
    inspector = ASTInspector()
    policy = ASTCodePolicy(inspector=inspector)

    for idx, (script, expected_primitive) in enumerate(ADVERSARIAL_SCRIPTS, 1):
        # 1. Inspector verdict
        ast_res = inspector.inspect(script)
        assert not ast_res.is_safe, f"Hostile script #{idx} ({expected_primitive}) was not rejected by ASTInspector!"

        # 2. Policy verdict
        verdict, reason, risk = policy.evaluate_code(script)
        assert verdict in (ActionGateVerdict.DENY, ActionGateVerdict.REQUIRE_CONFIRMATION), (
            f"Hostile script #{idx} ({expected_primitive}) was ALLOWED by ASTCodePolicy: {reason}"
        )
