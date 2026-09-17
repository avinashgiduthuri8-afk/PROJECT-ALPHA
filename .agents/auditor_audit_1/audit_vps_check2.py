import paramiko
import json

VPS_HOST = "148.113.9.103"
VPS_PORT = 20069
VPS_USER = "root"
VPS_PASS = "SMT6SiQU2nIUMj0V"

remote_script = '''
import sys
import os
import json
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timezone

sys.path.insert(0, "/opt/project-alpha")
from scanner.research.indicators import (
    compute_ema,
    compute_rsi,
    compute_macd,
    compute_bollinger,
    compute_atr,
    compute_rvol,
    last_valid,
)
from scanner.market_context import calculate_ema

results = {}

# 1. Phase 3: RSI Validation
rsi_up = compute_rsi(np.array([10.0 + i * 2.0 for i in range(30)]))
rsi_down = compute_rsi(np.array([100.0 - i * 2.0 for i in range(30)]))
rsi_flat = compute_rsi(np.array([50.0 for _ in range(30)]))
rsi_short = compute_rsi(np.array([10.0, 12.0, 14.0, 16.0]))

results["phase3_rsi"] = {
    "uptrend_final": float(last_valid(rsi_up)),
    "uptrend_overbought_gt_70": bool(last_valid(rsi_up) > 70.0),
    "downtrend_final": float(last_valid(rsi_down)),
    "downtrend_oversold_lt_30": bool(last_valid(rsi_down) < 30.0),
    "flat_final": float(last_valid(rsi_flat)),
    "short_all_nan": bool(np.all(np.isnan(rsi_short))),
}

# 2. Phase 4: MACD Validation
p40 = np.array([100.0 + (i % 5) * 2.0 + i for i in range(40)])
macd, sig, hist = compute_macd(p40)
df = pd.DataFrame({"macd": macd, "signal": sig, "hist": hist})
final_macd = float(df["macd"].iloc[-1])
final_sig = float(df["signal"].iloc[-1])
final_hist = float(df["hist"].iloc[-1])
identity_ok = bool(np.allclose(hist[33:], (macd - sig)[33:]))

p20 = np.array([100.0 + i for i in range(20)])
m20, s20, h20 = compute_macd(p20)

results["phase4_macd"] = {
    "df_shape": list(df.shape),
    "df_columns": list(df.columns),
    "final_macd": final_macd,
    "final_signal": final_sig,
    "final_hist": final_hist,
    "non_null_final": bool(not np.isnan(final_macd) and not np.isnan(final_sig) and not np.isnan(final_hist)),
    "identity_preserved": identity_ok,
    "warmup_macd_nan_count": int(np.sum(np.isnan(macd))),
    "warmup_sig_nan_count": int(np.sum(np.isnan(sig))),
    "short_all_nan": bool(np.all(np.isnan(m20)) and np.all(np.isnan(s20)) and np.all(np.isnan(h20))),
}

# 3. Phase 5: EMA50 Validation
p10 = np.array([100.0 + i for i in range(10)])
p49 = np.array([100.0 + i for i in range(49)])
p50 = np.array([100.0 + i for i in range(50)])
p80 = np.array([100.0 + i for i in range(80)])

ema10 = compute_ema(p10, 50)
ema49 = compute_ema(p49, 50)
ema50 = compute_ema(p50, 50)
ema80 = compute_ema(p80, 50)

calc_ema49 = calculate_ema(list(p49), 50)
calc_ema50 = calculate_ema(list(p50), 50)
calc_ema80 = calculate_ema(list(p80), 50)

results["phase5_ema50"] = {
    "p10_all_nan": bool(np.all(np.isnan(ema10))),
    "p49_all_nan": bool(np.all(np.isnan(ema49))),
    "p49_calc_ema_empty": bool(len(calc_ema49) == 0),
    "p50_first_valid_idx": int(np.where(~np.isnan(ema50))[0][0]),
    "p50_seed_val": float(ema50[49]),
    "p50_expected_seed": float(np.mean(p50[:50])),
    "p50_seed_matches": bool(abs(ema50[49] - np.mean(p50[:50])) < 1e-9),
    "p50_calc_ema_val": float(calc_ema50[0]) if calc_ema50 else None,
    "p80_final_val": float(ema80[-1]),
    "p80_calc_final_val": float(calc_ema80[-1]) if calc_ema80 else None,
    "p80_match": bool(abs(ema80[-1] - calc_ema80[-1]) < 1e-9),
}

# 4. Look-Ahead Bias Invariance Verification
p50_base = np.random.RandomState(42).randn(50).cumsum() + 100
p53_ext = np.append(p50_base, [150.0, 160.0, 170.0])

e50 = compute_ema(p50_base, 10)
e53 = compute_ema(p53_ext, 10)

r50 = compute_rsi(p50_base, 14)
r53 = compute_rsi(p53_ext, 14)

m50, s50, h50 = compute_macd(p50_base)
m53, s53, h53 = compute_macd(p53_ext)

results["look_ahead_invariance"] = {
    "ema_past_unaltered": bool(np.allclose(e50[9:], e53[:50][9:])),
    "rsi_past_unaltered": bool(np.allclose(r50[14:], r53[:50][14:])),
    "macd_past_unaltered": bool(np.allclose(m50[25:], m53[:50][25:])),
    "macd_signal_past_unaltered": bool(np.allclose(s50[33:], s53[:50][33:])),
}

# 5. Database Schema & Inspection
db_paths = ["/opt/project-alpha/v2/data/alpha_v2.db", "/opt/project-alpha/data/project_alpha.db"]
results["db_inspection"] = {}

for p in db_paths:
    if not os.path.exists(p):
        results["db_inspection"][p] = {"exists": False}
        continue
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(signals)")
    cols = [r[1] for r in cur.fetchall()]
    cur.execute("SELECT count(*) FROM signals")
    cnt = cur.fetchone()[0]
    
    cur.execute("SELECT id, coin, pair, score, generated_at, raw_payload FROM signals ORDER BY generated_at DESC LIMIT 5")
    rows = cur.fetchall()
    
    samples = []
    for r in rows:
        payload_data = None
        try:
            payload_data = json.loads(r[5]) if r[5] else None
        except Exception as e:
            payload_data = str(e)
        samples.append({
            "id": r[0],
            "coin": r[1],
            "pair": r[2],
            "score": r[3],
            "generated_at": r[4],
            "payload_indicator_keys": {
                k: payload_data.get(k) for k in ["rsi", "atr_pct", "volume_24h", "volume_ratio", "mtf_alignment", "strategy", "market_state"]
            } if isinstance(payload_data, dict) else None
        })
    conn.close()
    results["db_inspection"][p] = {
        "exists": True,
        "size_bytes": os.path.getsize(p),
        "columns": cols,
        "total_signals": cnt,
        "latest_5_signals": samples
    }

print(json.dumps(results))
'''

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS, timeout=15)

    # Write remote execution script
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/forensic_check2.py", "w") as f:
        f.write(remote_script)
    sftp.close()

    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3 /tmp/forensic_check2.py")
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    exit_code = stdout.channel.recv_exit_status()

    # Clean up remote script
    ssh.exec_command("rm -f /tmp/forensic_check2.py")
    ssh.close()

    with open(r"c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\auditor_audit_1\vps_check_2.json", "w") as f:
        f.write(out if exit_code == 0 else json.dumps({"exit_code": exit_code, "err": err, "out": out}, indent=2))

    print(f"Check 2 finished with exit code {exit_code}")

if __name__ == "__main__":
    main()
