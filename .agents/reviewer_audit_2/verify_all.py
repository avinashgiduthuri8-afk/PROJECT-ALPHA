"""
Independent Verification and Adversarial Stress-Test Script for reviewer_audit_2.
Connects to VPS via Paramiko SSH and validates:
1. Code integrity & git status on VPS
2. Unit tests execution on VPS
3. Phase 3 (RSI) reference validation & adversarial stress testing
4. Phase 4 (MACD) reference validation & adversarial stress testing
5. Phase 5 (EMA50) reference validation & adversarial stress testing
6. Phase 6 (Live SQLite Integration) database topology, logs, payload inspection
"""

import json
import sys
import paramiko

VPS_HOST = "148.113.9.103"
VPS_PORT = 20069
VPS_USER = "root"
VPS_PASS = "SMT6SiQU2nIUMj0V"


def run_ssh_command(client, command, timeout=30):
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8")
    err = stderr.read().decode("utf-8")
    exit_code = stdout.channel.recv_exit_status()
    return exit_code, out, err


def run_remote_python(client, script_content, timeout=30):
    cmd = "cd /opt/project-alpha && PYTHONPATH=. /opt/project-alpha/.venv/bin/python3 -"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    stdin.write(script_content)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8")
    err = stderr.read().decode("utf-8")
    exit_code = stdout.channel.recv_exit_status()
    return exit_code, out, err


def main():
    print(f"Connecting to VPS {VPS_HOST}:{VPS_PORT}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=VPS_HOST,
            port=VPS_PORT,
            username=VPS_USER,
            password=VPS_PASS,
            timeout=15,
        )
        print("Connected successfully.\n")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    results = {}

    # --- 1. VPS Git Status & Repo Integrity ---
    print("=== 1. Checking Git Status & Repo Integrity on VPS ===")
    code, out, err = run_ssh_command(
        client, "cd /opt/project-alpha && git status --short"
    )
    results["git_status"] = {"code": code, "out": out.strip(), "err": err.strip()}
    print(f"Git status:\n{out if out.strip() else '[clean]'}\n")

    # --- 2. Unit Test Execution on VPS ---
    print("=== 2. Running Indicator Unit Tests on VPS ===")
    code, out, err = run_ssh_command(
        client,
        "cd /opt/project-alpha && PYTHONPATH=. .venv/bin/pytest tests/test_indicator_calculations.py -v",
    )
    results["pytest"] = {"code": code, "out": out.strip(), "err": err.strip()}
    print(f"Pytest exit code: {code}")
    print(out)
    if err:
        print("Pytest stderr:", err)

    # --- 3. Remote Python Script for Phases 3, 4, 5 and Adversarial Tests ---
    print("=== 3. Executing Reference & Adversarial Tests on VPS ===")
    remote_test_script = """
import numpy as np
import pandas as pd
import json

from scanner.research.indicators import (
    compute_ema, compute_rsi, compute_macd, compute_bollinger, compute_atr, compute_rvol, last_valid
)
from scanner.market_context import calculate_ema

output = {}

# --- PHASE 3: RSI TESTS ---
p3 = {}
# Monotonic uptrend
up_prices = np.array([10.0 + i * 2.0 for i in range(30)])
rsi_up = compute_rsi(up_prices, period=14)
p3["up_final"] = float(rsi_up[-1])
p3["up_overbought"] = bool(rsi_up[-1] > 70.0)

# Realistic noisy uptrend
noisy_up = np.array([10.0 + i * 1.5 + np.sin(i) * 2.0 for i in range(40)])
rsi_noisy_up = compute_rsi(noisy_up, period=14)
p3["noisy_up_final"] = float(rsi_noisy_up[-1])
p3["noisy_up_overbought"] = bool(rsi_noisy_up[-1] > 70.0)

# Monotonic downtrend
down_prices = np.array([100.0 - i * 2.0 for i in range(30)])
rsi_down = compute_rsi(down_prices, period=14)
p3["down_final"] = float(rsi_down[-1])
p3["down_oversold"] = bool(rsi_down[-1] < 30.0)

# Realistic noisy downtrend
noisy_down = np.array([100.0 - i * 1.5 + np.sin(i) * 2.0 for i in range(40)])
rsi_noisy_down = compute_rsi(noisy_down, period=14)
p3["noisy_down_final"] = float(rsi_noisy_down[-1])
p3["noisy_down_oversold"] = bool(rsi_noisy_down[-1] < 30.0)

# Flat prices (zero variance)
flat_prices = np.array([50.0] * 30)
rsi_flat = compute_rsi(flat_prices, period=14)
p3["flat_final"] = float(rsi_flat[-1])
p3["flat_no_crash"] = not np.isnan(rsi_flat[-1])

# Insufficient data
short_prices = np.array([10.0, 11.0, 12.0, 13.0])
rsi_short = compute_rsi(short_prices, period=14)
p3["short_len"] = len(rsi_short)
p3["short_all_nan"] = bool(np.all(np.isnan(rsi_short)))

# ADVERSARIAL RSI TESTS:
adv_rsi = {}
# All zeros
zeros = np.zeros(30)
rsi_zeros = compute_rsi(zeros, 14)
adv_rsi["zeros_final"] = float(rsi_zeros[-1])
adv_rsi["zeros_no_crash"] = not np.isnan(rsi_zeros[-1])

# Exact boundary len = 15 (period + 1)
b15 = np.array([10.0 + i for i in range(15)])
rsi_b15 = compute_rsi(b15, 14)
adv_rsi["b15_len"] = len(rsi_b15)
adv_rsi["b15_nan_count"] = int(np.sum(np.isnan(rsi_b15)))
adv_rsi["b15_valid_last"] = float(rsi_b15[-1])

# Zero length
rsi_empty = compute_rsi(np.array([]), 14)
adv_rsi["empty_len"] = len(rsi_empty)

p3["adversarial"] = adv_rsi
output["phase_3_rsi"] = p3


# --- PHASE 4: MACD TESTS ---
p4 = {}
prices_40 = np.array([100.0 + (i % 5) * 2.0 + i for i in range(40)])
macd, signal, hist = compute_macd(prices_40, fast=12, slow=26, signal_period=9)
df = pd.DataFrame({"macd": macd, "signal": signal, "hist": hist})

p4["shape"] = list(df.shape)
p4["columns"] = list(df.columns)
p4["final_macd"] = round(float(macd[-1]), 6)
p4["final_signal"] = round(float(signal[-1]), 6)
p4["final_hist"] = round(float(hist[-1]), 6)
p4["non_null_final"] = bool(not np.isnan(macd[-1]) and not np.isnan(signal[-1]) and not np.isnan(hist[-1]))

# Mathematical identity across valid rows
valid_mask = ~np.isnan(hist)
p4["identity_holds"] = bool(np.allclose(hist[valid_mask], macd[valid_mask] - signal[valid_mask], atol=1e-6))
p4["macd_nan_count"] = int(np.sum(np.isnan(macd)))
p4["signal_nan_count"] = int(np.sum(np.isnan(signal)))
p4["hist_nan_count"] = int(np.sum(np.isnan(hist)))

# Insufficient data (< 34 bars)
p_20 = np.array([100.0 + i for i in range(20)])
m20, s20, h20 = compute_macd(p_20)
p4["short_20_all_signal_nan"] = bool(np.all(np.isnan(s20)))

# ADVERSARIAL MACD TESTS:
adv_macd = {}
# Constant price series (flat)
flat_40 = np.full(40, 100.0)
m_flat, s_flat, h_flat = compute_macd(flat_40)
adv_macd["flat_final_macd"] = float(m_flat[-1])
adv_macd["flat_final_signal"] = float(s_flat[-1])
adv_macd["flat_final_hist"] = float(h_flat[-1])
adv_macd["flat_converges_to_zero"] = bool(abs(m_flat[-1]) < 1e-9 and abs(s_flat[-1]) < 1e-9)

# Exact boundary len = 34 (slow 26 + signal 9 - 1 = 34)
p_34 = np.array([100.0 + i for i in range(34)])
m34, s34, h34 = compute_macd(p_34)
adv_macd["len34_signal_nan_count"] = int(np.sum(np.isnan(s34)))
adv_macd["len34_final_signal_valid"] = bool(not np.isnan(s34[-1]))

# len = 33 (just below valid signal)
p_33 = np.array([100.0 + i for i in range(33)])
m33, s33, h33 = compute_macd(p_33)
adv_macd["len33_signal_nan_count"] = int(np.sum(np.isnan(s33)))

p4["adversarial"] = adv_macd
output["phase_4_macd"] = p4


# --- PHASE 5: EMA50 TESTS ---
p5 = {}
# Insufficient data
p10 = np.array([100.0 + i for i in range(10)])
ema10 = compute_ema(p10, 50)
calc_ema10 = calculate_ema(list(p10), 50)
p5["len10_all_nan"] = bool(np.all(np.isnan(ema10)))
p5["len10_last_valid_zero"] = bool(last_valid(ema10) == 0.0)
p5["len10_calc_ema_empty"] = bool(calc_ema10 == [])

p49 = np.array([100.0 + i for i in range(49)])
ema49 = compute_ema(p49, 50)
calc_ema49 = calculate_ema(list(p49), 50)
p5["len49_all_nan"] = bool(np.all(np.isnan(ema49)))
p5["len49_calc_ema_empty"] = bool(calc_ema49 == [])

# Exact boundary (50 candles)
p50 = np.array([100.0 + i for i in range(50)])
ema50 = compute_ema(p50, 50)
calc_ema50 = calculate_ema(list(p50), 50)
expected_seed = float(np.mean(p50[:50]))
p50_first49_nan = bool(np.all(np.isnan(ema50[:49])))
p50_seed_match = bool(abs(ema50[49] - expected_seed) < 1e-9)
p5["len50_first49_nan"] = p50_first49_nan
p5["len50_seed_value"] = float(ema50[49])
p5["len50_expected_seed"] = expected_seed
p5["len50_seed_match"] = p50_seed_match
p5["len50_calc_ema_val"] = float(calc_ema50[0]) if calc_ema50 else None

# Sufficient data (80 candles)
p80 = np.array([100.0 + i for i in range(80)])
ema80 = compute_ema(p80, 50)
calc_ema80 = calculate_ema(list(p80), 50)
p5["len80_valid_count"] = int(np.sum(~np.isnan(ema80)))
p5["len80_final_val"] = round(float(ema80[-1]), 6)
p5["len80_calc_ema_final"] = round(float(calc_ema80[-1]), 6) if calc_ema80 else None
p5["len80_implementations_match"] = bool(np.allclose(ema80[49:], calc_ema80, atol=1e-6))

# ADVERSARIAL EMA TESTS:
adv_ema = {}
# Empty input
adv_ema["empty_compute_len"] = len(compute_ema(np.array([]), 50))
adv_ema["empty_calc_len"] = len(calculate_ema([], 50))

# 1000 bars constant prices
const_1000 = np.full(1000, 42.0)
ema_const = compute_ema(const_1000, 50)
adv_ema["const_final"] = float(ema_const[-1])
adv_ema["const_exact"] = bool(abs(ema_const[-1] - 42.0) < 1e-9)

p5["adversarial"] = adv_ema
output["phase_5_ema50"] = p5

print("JSON_START")
print(json.dumps(output, indent=2))
print("JSON_END")
"""
    code, out, err = run_remote_python(client, remote_test_script)
    results["ref_tests"] = {"code": code, "out": out, "err": err}
    if "JSON_START" in out and "JSON_END" in out:
        json_str = out.split("JSON_START")[1].split("JSON_END")[0].strip()
        parsed_ref = json.loads(json_str)
        print("Reference and Adversarial Validation Results:")
        print(json.dumps(parsed_ref, indent=2))
        results["parsed_ref"] = parsed_ref
    else:
        print("Failed to parse JSON output from remote tests:")
        print(out)
        print(err)

    # --- 4. Deep SQLite Database & Live Process State ---
    print("\n=== 4. Checking Live SQLite Databases & Process State on VPS ===")
    db_script = """
import sqlite3
import os
import json
from datetime import datetime, timezone

db_paths = [
    "/opt/project-alpha/data/project_alpha.db",
    "/opt/project-alpha/v2/data/alpha_v2.db"
]

db_info = {}

for p in db_paths:
    info = {"exists": os.path.exists(p)}
    if info["exists"]:
        info["size_bytes"] = os.path.getsize(p)
        try:
            conn = sqlite3.connect(p)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            info["tables"] = tables
            
            if "signals" in tables:
                cur.execute("PRAGMA table_info('signals')")
                info["signals_columns"] = [r[1] for r in cur.fetchall()]
                cur.execute("SELECT COUNT(*) FROM signals")
                info["total_signals"] = cur.fetchone()[0]
                
                # Latest signals
                cur.execute("SELECT id, coin, pair, score, generated_at, raw_payload FROM signals ORDER BY generated_at DESC LIMIT 3")
                latest = []
                for row in cur.fetchall():
                    raw_parsed = None
                    if row[5]:
                        try:
                            raw_parsed = json.loads(row[5])
                        except Exception as ex:
                            raw_parsed = str(ex)
                    latest.append({
                        "id": row[0],
                        "coin": row[1],
                        "pair": row[2],
                        "score": row[3],
                        "generated_at": row[4],
                        "raw_payload": raw_parsed
                    })
                info["latest_signals"] = latest
                
                # Count in last 5 min, 1h, 24h relative to utc now
                now_utc = datetime.now(timezone.utc)
                # Parse timestamps
                cur.execute("SELECT generated_at FROM signals")
                all_ts = cur.fetchall()
                c_5m, c_1h, c_24h, c_today = 0, 0, 0, 0
                today_str = now_utc.strftime("%Y-%m-%d")
                for (ts_str,) in all_ts:
                    if ts_str:
                        if ts_str.startswith(today_str):
                            c_today += 1
                        try:
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            diff_s = (now_utc - dt).total_seconds()
                            if diff_s <= 300:
                                c_5m += 1
                            if diff_s <= 3600:
                                c_1h += 1
                            if diff_s <= 86400:
                                c_24h += 1
                        except Exception:
                            pass
                info["signals_last_5m"] = c_5m
                info["signals_last_1h"] = c_1h
                info["signals_last_24h"] = c_24h
                info["signals_today"] = c_today
            conn.close()
        except Exception as e:
            info["error"] = str(e)
    db_info[p] = info

print("DB_JSON_START")
print(json.dumps(db_info, indent=2))
print("DB_JSON_END")
"""
    code, out, err = run_remote_python(client, db_script)
    if "DB_JSON_START" in out and "DB_JSON_END" in out:
        db_json_str = out.split("DB_JSON_START")[1].split("DB_JSON_END")[0].strip()
        parsed_db = json.loads(db_json_str)
        print("Database Status:")
        print(json.dumps(parsed_db, indent=2))
        results["db_status"] = parsed_db
    else:
        print("Failed to parse DB JSON:")
        print(out)
        print(err)

    # --- 5. Systemd Service Journal Logs ---
    print("\n=== 5. Checking Scanner Scheduler & Confluence Logs (Last 10 Min) ===")
    code, out, err = run_ssh_command(
        client,
        "journalctl -u project-alpha-v2.service --since '10 minutes ago' --no-pager | grep -E 'scanner|confluence' | tail -n 25",
    )
    print(out)
    results["journal_logs"] = out

    client.close()
    print("\nAll independent checks finished.")

    # Save results locally for analysis
    with open("c:/Users/ASUS/Documents/GitHub/PROJECT-ALPHA/.agents/reviewer_audit_2/audit_results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
