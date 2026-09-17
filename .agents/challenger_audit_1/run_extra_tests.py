import json
import paramiko

SCRIPT = """
import numpy as np
import pandas as pd
import json

from scanner.research.indicators import (
    compute_ema,
    compute_rsi,
    compute_macd,
    compute_bollinger,
    compute_atr,
    compute_rvol,
    compute_sma,
    last_valid,
)

extra_results = {}

# Test E1: Negative Prices
p_neg = np.array([-50.0 + i * 2.0 for i in range(40)])
try:
    r_neg = compute_rsi(p_neg, 14)
    m_neg, s_neg, h_neg = compute_macd(p_neg, 12, 26, 9)
    e_neg = compute_ema(p_neg, 20)
    extra_results["E1_negative_prices"] = {
        "pass": bool(np.isfinite(r_neg[14:]).all() and np.isfinite(e_neg[19:]).all() and np.isfinite(h_neg[33:]).all()),
        "rsi_final": float(r_neg[-1]),
        "macd_final": float(m_neg[-1])
    }
except Exception as ex:
    extra_results["E1_negative_prices"] = {"pass": False, "error": str(ex)}

# Test E2: Mixed Float32 / Float64 / Int inputs
p_int = np.arange(10, 50)
try:
    r_int = compute_rsi(p_int, 14)
    m_int, s_int, h_int = compute_macd(p_int, 12, 26, 9)
    e_int = compute_ema(p_int, 20)
    extra_results["E2_integer_input_types"] = {
        "pass": bool(isinstance(r_int, np.ndarray) and isinstance(e_int, np.ndarray)),
        "rsi_final": float(r_int[-1])
    }
except Exception as ex:
    extra_results["E2_integer_input_types"] = {"pass": False, "error": str(ex)}

# Test E3: Python List as input (does np.diff / np.mean handle or throw?)
try:
    p_list = [10.0 + i for i in range(30)]
    r_list = compute_rsi(p_list, 14)
    extra_results["E3_python_list_input"] = {
        "pass": True,
        "rsi_len": len(r_list),
        "rsi_final": float(r_list[-1])
    }
except Exception as ex:
    extra_results["E3_python_list_input"] = {"pass": False, "error": str(ex)}

# Test E4: Pytest indicator suite execution
import subprocess
res = subprocess.run(
    ["/opt/project-alpha/.venv/bin/pytest", "tests/test_indicator_calculations.py", "-v"],
    cwd="/opt/project-alpha",
    env={"PYTHONPATH": ".", "PATH": "/usr/local/bin:/usr/bin:/bin"},
    capture_output=True,
    text=True
)
extra_results["E4_pytest_indicators"] = {
    "returncode": res.returncode,
    "stdout": res.stdout,
    "stderr": res.stderr,
    "pass": res.returncode == 0
}

print("=== BEGIN EXTRA JSON ===")
print(json.dumps(extra_results, indent=2))
print("=== END EXTRA JSON ===")
"""

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)
    
    remote_path = "/tmp/test_extra_adversarial.py"
    sftp = client.open_sftp()
    with sftp.file(remote_path, 'w') as f:
        f.write(SCRIPT)
    sftp.close()

    cmd = f"cd /opt/project-alpha && PYTHONPATH=. /opt/project-alpha/.venv/bin/python3 {remote_path}"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    client.exec_command(f"rm -f {remote_path}")
    client.close()

    if "=== BEGIN EXTRA JSON ===" in out:
        json_str = out.split("=== BEGIN EXTRA JSON ===")[1].split("=== END EXTRA JSON ===")[0].strip()
        data = json.loads(json_str)
        with open("extra_adversarial_results.json", "w") as f:
            json.dump(data, f, indent=2)
        print("Extra test results saved.")
        print("Pytest output:\n", data.get("E4_pytest_indicators", {}).get("stdout"))
    else:
        print("Raw output:\n", out)
        if err:
            print("STDERR:\n", err)

if __name__ == '__main__':
    main()
