import paramiko
import json

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=30)

    py_validation_script = """
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, '/opt/project-alpha')

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
from scanner.market_context import calculate_ema

results = {}

# ==============================================================================
# PHASE 3: RSI REFERENCE VALIDATION
# ==============================================================================
p3 = {}

# 1. Monotonic uptrend (30 bars, step +2.0)
prices_up = np.array([10.0 + i * 2.0 for i in range(30)])
rsi_up = compute_rsi(prices_up, period=14)
rsi_up_last = last_valid(rsi_up)
p3["monotonic_uptrend"] = {
    "bars": len(prices_up),
    "rsi_final": round(rsi_up_last, 4),
    "is_overbought_gt_70": bool(rsi_up_last > 70.0),
    "status": "PASS" if rsi_up_last > 70.0 else "FAIL"
}

# 2. Realistic noisy uptrend (higher highs, higher lows, 40 bars)
np.random.seed(42)
drift_up = np.linspace(100, 150, 40) + np.sin(np.linspace(0, 3 * np.pi, 40)) * 2.0
rsi_noisy_up = compute_rsi(drift_up, period=14)
rsi_noisy_up_last = last_valid(rsi_noisy_up)
p3["realistic_noisy_uptrend"] = {
    "bars": len(drift_up),
    "rsi_final": round(rsi_noisy_up_last, 4),
    "is_overbought_gt_70": bool(rsi_noisy_up_last > 70.0),
    "status": "PASS" if rsi_noisy_up_last > 70.0 else "FAIL"
}

# 3. Monotonic downtrend (30 bars, step -2.0)
prices_down = np.array([100.0 - i * 2.0 for i in range(30)])
rsi_down = compute_rsi(prices_down, period=14)
rsi_down_last = last_valid(rsi_down)
p3["monotonic_downtrend"] = {
    "bars": len(prices_down),
    "rsi_final": round(rsi_down_last, 4),
    "is_oversold_lt_30": bool(rsi_down_last < 30.0),
    "status": "PASS" if rsi_down_last < 30.0 else "FAIL"
}

# 4. Realistic noisy downtrend (lower highs, lower lows, 40 bars)
drift_down = np.linspace(150, 100, 40) + np.cos(np.linspace(0, 3 * np.pi, 40)) * 2.0
rsi_noisy_down = compute_rsi(drift_down, period=14)
rsi_noisy_down_last = last_valid(rsi_noisy_down)
p3["realistic_noisy_downtrend"] = {
    "bars": len(drift_down),
    "rsi_final": round(rsi_noisy_down_last, 4),
    "is_oversold_lt_30": bool(rsi_noisy_down_last < 30.0),
    "status": "PASS" if rsi_noisy_down_last < 30.0 else "FAIL"
}

# 5. Flat price series (30 bars at 50.0)
prices_flat = np.array([50.0] * 30)
rsi_flat = compute_rsi(prices_flat, period=14)
rsi_flat_last = last_valid(rsi_flat)
p3["flat_price_series"] = {
    "bars": len(prices_flat),
    "rsi_final": round(rsi_flat_last, 4),
    "is_nan": bool(np.isnan(rsi_flat_last)),
    "status": "PASS"
}

# 6. Insufficient data (< 15 bars)
prices_short = np.array([10.0, 11.0, 12.0, 13.0])
rsi_short = compute_rsi(prices_short, period=14)
p3["insufficient_data"] = {
    "bars": len(prices_short),
    "all_nan": bool(np.all(np.isnan(rsi_short))),
    "status": "PASS" if np.all(np.isnan(rsi_short)) else "FAIL"
}

results["Phase_3_RSI"] = p3

# ==============================================================================
# PHASE 4: MACD REFERENCE VALIDATION
# ==============================================================================
p4 = {}

# 1. Standard price series (40 bars)
prices_macd = np.array([100.0 + (i % 5) * 2.0 + i for i in range(40)])
macd_line, signal_line, hist_line = compute_macd(prices_macd, fast=12, slow=26, signal_period=9)

df_macd = pd.DataFrame({
    "macd": macd_line,
    "signal": signal_line,
    "hist": hist_line
})

final_row = df_macd.iloc[-1]
non_null_final = bool(final_row.notna().all())
hist_identity_valid = bool(abs(final_row["hist"] - (final_row["macd"] - final_row["signal"])) < 1e-6)

p4["standard_40_bars"] = {
    "is_dataframe": isinstance(df_macd, pd.DataFrame),
    "columns": list(df_macd.columns),
    "shape": list(df_macd.shape),
    "final_macd": round(float(final_row["macd"]), 6),
    "final_signal": round(float(final_row["signal"]), 6),
    "final_hist": round(float(final_row["hist"]), 6),
    "non_null_final_values": non_null_final,
    "hist_identity_holds": hist_identity_valid,
    "initial_nan_count": {
        "macd": int(df_macd["macd"].isna().sum()),
        "signal": int(df_macd["signal"].isna().sum()),
        "hist": int(df_macd["hist"].isna().sum())
    },
    "status": "PASS" if non_null_final and hist_identity_valid else "FAIL"
}

# 2. Insufficient data (< 34 bars, e.g. 20 bars)
prices_macd_short = np.array([100.0 + i for i in range(20)])
macd_s, sig_s, hist_s = compute_macd(prices_macd_short, fast=12, slow=26, signal_period=9)
df_macd_short = pd.DataFrame({"macd": macd_s, "signal": sig_s, "hist": hist_s})
p4["insufficient_data_20_bars"] = {
    "shape": list(df_macd_short.shape),
    "macd_all_nan": bool(df_macd_short["macd"].isna().all()),
    "signal_all_nan": bool(df_macd_short["signal"].isna().all()),
    "hist_all_nan": bool(df_macd_short["hist"].isna().all()),
    "status": "PASS" if df_macd_short.isna().all().all() else "FAIL"
}

results["Phase_4_MACD"] = p4

# ==============================================================================
# PHASE 5: EMA50 REFERENCE VALIDATION
# ==============================================================================
p5 = {}

# Test scanner.research.indicators.compute_ema (NumPy array based)
# 1. Insufficient data (< 50 candles: 10, 49 candles)
p_10 = np.array([100.0 + i for i in range(10)])
ema50_10 = compute_ema(p_10, period=50)

p_49 = np.array([100.0 + i for i in range(49)])
ema50_49 = compute_ema(p_49, period=50)

p5["compute_ema_less_than_50"] = {
    "bars_10": {
        "len": len(ema50_10),
        "all_nan": bool(np.all(np.isnan(ema50_10))),
        "last_valid": last_valid(ema50_10)
    },
    "bars_49": {
        "len": len(ema50_49),
        "all_nan": bool(np.all(np.isnan(ema50_49))),
        "last_valid": last_valid(ema50_49)
    },
    "status": "PASS" if np.all(np.isnan(ema50_10)) and np.all(np.isnan(ema50_49)) else "FAIL"
}

# 2. Exactly 50 candles (Boundary case)
p_50 = np.array([100.0 + i for i in range(50)])
ema50_50 = compute_ema(p_50, period=50)
expected_seed = np.mean(p_50[:50])
seed_matches = bool(abs(ema50_50[49] - expected_seed) < 1e-9)
first_49_nan = bool(np.all(np.isnan(ema50_50[:49])))

p5["compute_ema_exactly_50"] = {
    "len": len(ema50_50),
    "first_49_nan": first_49_nan,
    "seed_index_49_val": round(float(ema50_50[49]), 6),
    "expected_seed": round(float(expected_seed), 6),
    "seed_matches": seed_matches,
    "last_valid": round(last_valid(ema50_50), 6),
    "status": "PASS" if first_49_nan and seed_matches and not np.isnan(ema50_50[-1]) else "FAIL"
}

# 3. Sufficient data (>= 50 candles: 80, 150 candles)
p_80 = np.array([100.0 + i * 0.5 for i in range(80)])
ema50_80 = compute_ema(p_80, period=50)
p5["compute_ema_80_candles"] = {
    "len": len(ema50_80),
    "final_value": round(float(ema50_80[-1]), 6),
    "final_is_valid": bool(not np.isnan(ema50_80[-1])),
    "status": "PASS" if not np.isnan(ema50_80[-1]) else "FAIL"
}

# Test scanner.market_context.calculate_ema (List based)
list_49 = [100.0 + i for i in range(49)]
calc_ema_49 = calculate_ema(list_49, 50)

list_50 = [100.0 + i for i in range(50)]
calc_ema_50 = calculate_ema(list_50, 50)

list_80 = [100.0 + i * 0.5 for i in range(80)]
calc_ema_80 = calculate_ema(list_80, 50)

p5["calculate_ema_market_context"] = {
    "bars_49_returns_empty": bool(calc_ema_49 == []),
    "bars_50_len": len(calc_ema_50),
    "bars_50_val": round(float(calc_ema_50[-1]), 6) if calc_ema_50 else None,
    "bars_80_len": len(calc_ema_80),
    "bars_80_val": round(float(calc_ema_80[-1]), 6) if calc_ema_80 else None,
    "status": "PASS" if calc_ema_49 == [] and len(calc_ema_50) == 1 and len(calc_ema_80) == 31 else "FAIL"
}

results["Phase_5_EMA50"] = p5

print(json.dumps(results, indent=2))
"""

    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_validation_script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    print("STDOUT:\n", out)
    if err:
        print("STDERR:\n", err)
    ssh.close()

if __name__ == '__main__':
    main()
