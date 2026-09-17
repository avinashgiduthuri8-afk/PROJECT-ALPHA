import json
import os
import sys
import paramiko

REMOTE_SCRIPT = """
import json
import numpy as np
import pandas as pd
import math
import sys

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

results = {
    "Phase_3_RSI": {},
    "Phase_4_MACD": {},
    "Phase_5_EMA50": {},
    "Causality_LookAhead": {},
    "Overall_Verdict": "PENDING"
}

# ==============================================================================
# PHASE 3: RSI ADVERSARIAL STRESS TESTING
# ==============================================================================
rsi_tests = {}

# Test 3.1: Monotonic Uptrend (overbought > 70)
p_up = np.array([10.0 + i * 2.0 for i in range(30)])
r_up = compute_rsi(p_up, 14)
rsi_tests["3.1_monotonic_uptrend"] = {
    "input_len": len(p_up),
    "output_len": len(r_up),
    "initial_nans": int(np.isnan(r_up[:14]).sum()),
    "first_valid_idx": 14,
    "first_valid_val": float(r_up[14]),
    "final_rsi": float(r_up[-1]),
    "is_overbought_gt_70": bool(r_up[-1] > 70.0),
    "is_100": bool(abs(r_up[-1] - 100.0) < 1e-9),
    "pass": bool(r_up[-1] > 70.0 and np.isnan(r_up[:14]).all())
}

# Test 3.2: Monotonic Downtrend (oversold < 30)
p_down = np.array([100.0 - i * 2.0 for i in range(30)])
r_down = compute_rsi(p_down, 14)
rsi_tests["3.2_monotonic_downtrend"] = {
    "input_len": len(p_down),
    "output_len": len(r_down),
    "initial_nans": int(np.isnan(r_down[:14]).sum()),
    "first_valid_idx": 14,
    "first_valid_val": float(r_down[14]),
    "final_rsi": float(r_down[-1]),
    "is_oversold_lt_30": bool(r_down[-1] < 30.0),
    "is_0": bool(abs(r_down[-1] - 0.0) < 1e-9),
    "pass": bool(r_down[-1] < 30.0 and np.isnan(r_down[:14]).all())
}

# Test 3.3: Constant Series (Zero Variance / Div-by-zero stress)
constant_tests = {}
for const_val in [0.0, 1.0, 50.0, 1e-8, 1e8]:
    p_const = np.full(30, const_val)
    r_const = compute_rsi(p_const, 14)
    c_valid = r_const[14:]
    constant_tests[f"const_{const_val}"] = {
        "nan_count": int(np.isnan(r_const).sum()),
        "first_valid": float(r_const[14]),
        "all_valid_finite": bool(np.isfinite(c_valid).all()),
        "val_is_100": bool(all(abs(v - 100.0) < 1e-6 for v in c_valid))
    }
rsi_tests["3.3_constant_series"] = {
    "details": constant_tests,
    "pass": all(v["all_valid_finite"] for v in constant_tests.values())
}

# Test 3.4: Single Large Spike Stress
p_spike = np.full(40, 100.0)
p_spike[20] = 10000.0  # 100x spike
r_spike = compute_rsi(p_spike, 14)
rsi_tests["3.4_single_large_spike"] = {
    "max_val": float(np.nanmax(r_spike)),
    "min_val": float(np.nanmin(r_spike)),
    "within_0_100": bool(0.0 <= np.nanmin(r_spike) and np.nanmax(r_spike) <= 100.0),
    "all_valid_finite": bool(np.isfinite(r_spike[14:]).all()),
    "pass": bool(0.0 <= np.nanmin(r_spike) and np.nanmax(r_spike) <= 100.0 and np.isfinite(r_spike[14:]).all())
}

# Test 3.5: Series Length Boundaries 0 to 20
length_boundary_tests = {}
all_len_pass = True
for L in range(0, 21):
    prices_L = np.linspace(50.0, 100.0, L) if L > 0 else np.array([])
    r_L = compute_rsi(prices_L, 14)
    expected_len = L
    if L < 15:
        # All must be NaN
        is_all_nan = bool(np.isnan(r_L).all()) if L > 0 else (len(r_L) == 0)
        length_boundary_tests[f"len_{L}"] = {
            "len": len(r_L),
            "all_nan": is_all_nan,
            "pass": is_all_nan and len(r_L) == L
        }
        if not (is_all_nan and len(r_L) == L):
            all_len_pass = False
    else:
        # First 14 are NaN, index 14 onwards are valid floats
        nans_14 = bool(np.isnan(r_L[:14]).all())
        valid_tail = bool(np.isfinite(r_L[14:]).all())
        bounds_ok = bool((r_L[14:] >= 0.0).all() and (r_L[14:] <= 100.0).all())
        p_ok = nans_14 and valid_tail and bounds_ok and len(r_L) == L
        length_boundary_tests[f"len_{L}"] = {
            "len": len(r_L),
            "first_14_nan": nans_14,
            "valid_tail": valid_tail,
            "bounds_0_100": bounds_ok,
            "pass": p_ok
        }
        if not p_ok:
            all_len_pass = False

rsi_tests["3.5_length_boundaries_0_to_20"] = {
    "details": length_boundary_tests,
    "pass": all_len_pass
}

# Test 3.6: Random Walk Invariant Test (100 synthetic series bounded in [0, 100])
np.random.seed(42)
random_walk_passes = 0
for _ in range(100):
    returns = np.random.normal(0.001, 0.03, 80)
    sim_prices = 100.0 * np.exp(np.cumsum(returns))
    r_sim = compute_rsi(sim_prices, 14)
    valid_sim = r_sim[14:]
    if np.isfinite(valid_sim).all() and (valid_sim >= 0.0).all() and (valid_sim <= 100.0).all():
        random_walk_passes += 1

rsi_tests["3.6_monte_carlo_bounds_invariants"] = {
    "iterations": 100,
    "passes": random_walk_passes,
    "pass": random_walk_passes == 100
}

phase_3_overall_pass = all(t["pass"] for t in rsi_tests.values())
results["Phase_3_RSI"] = {
    "status": "PASS" if phase_3_overall_pass else "FAIL",
    "tests": rsi_tests
}


# ==============================================================================
# PHASE 4: MACD ADVERSARIAL STRESS TESTING
# ==============================================================================
macd_tests = {}

# Test 4.1: Standard 40 Bars DataFrame Verification
p_40 = np.array([100.0 + (i % 5) * 2.0 + i for i in range(40)])
macd_40, signal_40, hist_40 = compute_macd(p_40, fast=12, slow=26, signal_period=9)
df_40 = pd.DataFrame({"macd": macd_40, "signal": signal_40, "hist": hist_40})

macd_tests["4.1_dataframe_40_3_format"] = {
    "is_dataframe": isinstance(df_40, pd.DataFrame),
    "shape": list(df_40.shape),
    "expected_shape": [40, 3],
    "columns": list(df_40.columns),
    "expected_columns": ["macd", "signal", "hist"],
    "final_macd": float(df_40.iloc[-1]["macd"]),
    "final_signal": float(df_40.iloc[-1]["signal"]),
    "final_hist": float(df_40.iloc[-1]["hist"]),
    "non_null_final_values": bool(
        not pd.isna(df_40.iloc[-1]["macd"]) and
        not pd.isna(df_40.iloc[-1]["signal"]) and
        not pd.isna(df_40.iloc[-1]["hist"])
    ),
    "pass": bool(
        isinstance(df_40, pd.DataFrame) and
        list(df_40.shape) == [40, 3] and
        list(df_40.columns) == ["macd", "signal", "hist"] and
        not pd.isna(df_40.iloc[-1]["macd"]) and
        not pd.isna(df_40.iloc[-1]["signal"]) and
        not pd.isna(df_40.iloc[-1]["hist"])
    )
}

# Test 4.2: Exact Identity hist == macd - signal across all bars
valid_mask = ~np.isnan(signal_40)
diffs = np.abs(hist_40[valid_mask] - (macd_40[valid_mask] - signal_40[valid_mask]))
max_diff = float(np.max(diffs)) if len(diffs) > 0 else 0.0
all_close = bool(np.allclose(hist_40[valid_mask], macd_40[valid_mask] - signal_40[valid_mask], atol=1e-9))
all_nan_aligned = bool(np.array_equal(np.isnan(signal_40), np.isnan(hist_40)))

macd_tests["4.2_exact_identity_hist_equals_macd_minus_signal"] = {
    "valid_bars_count": int(valid_mask.sum()),
    "max_discrepancy": max_diff,
    "allclose_1e_9": all_close,
    "nan_mask_aligned": all_nan_aligned,
    "pass": bool(all_close and all_nan_aligned and valid_mask.sum() > 0)
}

# Test 4.3: Boundary Length Progression (0, 1, 12, 25, 26, 33, 34, 35, 60)
boundary_lengths = [0, 1, 12, 25, 26, 33, 34, 35, 60]
boundary_macd_results = {}
all_boundary_macd_pass = True

for L in boundary_lengths:
    p_L = np.linspace(100.0, 200.0, L) if L > 0 else np.array([])
    m_L, s_L, h_L = compute_macd(p_L, 12, 26, 9)
    df_L = pd.DataFrame({"macd": m_L, "signal": s_L, "hist": h_L})

    if L < 26:
        # All columns must be NaN
        c_pass = bool(len(df_L) == L and np.isnan(m_L).all() and np.isnan(s_L).all() and np.isnan(h_L).all()) if L > 0 else (len(df_L) == 0)
    elif 26 <= L < 34:
        # macd has valid values from index 25, but signal and hist must be all NaN
        macd_valid_count = int((~np.isnan(m_L)).sum())
        sig_all_nan = bool(np.isnan(s_L).all())
        hist_all_nan = bool(np.isnan(h_L).all())
        c_pass = bool(len(df_L) == L and macd_valid_count == (L - 25) and sig_all_nan and hist_all_nan)
    else: # L >= 34
        # First valid signal at index 33 (which is 25 + 9 - 1)
        first_sig_idx = int(np.where(~np.isnan(s_L))[0][0])
        sig_valid = bool(first_sig_idx == 33)
        identity_ok = bool(np.allclose(h_L[33:], m_L[33:] - s_L[33:], atol=1e-9))
        c_pass = bool(len(df_L) == L and sig_valid and identity_ok)

    boundary_macd_results[f"len_{L}"] = {
        "shape": list(df_L.shape),
        "pass": c_pass
    }
    if not c_pass:
        all_boundary_macd_pass = False

macd_tests["4.3_boundary_lengths_warmup"] = {
    "details": boundary_macd_results,
    "pass": all_boundary_macd_pass
}

# Test 4.4: Constant Price Series MACD (Mathematical Flatness)
p_flat = np.full(50, 150.0)
m_flat, s_flat, h_flat = compute_macd(p_flat, 12, 26, 9)
flat_tail_m = m_flat[33:]
flat_tail_s = s_flat[33:]
flat_tail_h = h_flat[33:]
macd_tests["4.4_constant_series_flatness"] = {
    "max_abs_macd": float(np.max(np.abs(flat_tail_m))),
    "max_abs_signal": float(np.max(np.abs(flat_tail_s))),
    "max_abs_hist": float(np.max(np.abs(flat_tail_h))),
    "pass": bool(
        np.allclose(flat_tail_m, 0.0, atol=1e-9) and
        np.allclose(flat_tail_s, 0.0, atol=1e-9) and
        np.allclose(flat_tail_h, 0.0, atol=1e-9)
    )
}

phase_4_overall_pass = all(t["pass"] for t in macd_tests.values())
results["Phase_4_MACD"] = {
    "status": "PASS" if phase_4_overall_pass else "FAIL",
    "tests": macd_tests
}


# ==============================================================================
# PHASE 5: EMA50 ADVERSARIAL STRESS TESTING
# ==============================================================================
ema_tests = {}

# Test 5.1: Insufficient Data (< 50 bars)
insufficient_results = {}
all_insuff_pass = True
for L in [0, 1, 10, 49]:
    p_ins = np.linspace(10.0, 50.0, L) if L > 0 else np.array([])
    e_ins = compute_ema(p_ins, period=50)
    lv_ins = last_valid(e_ins)
    calc_list = calculate_ema(list(p_ins), period=50)

    is_all_nan = bool(np.isnan(e_ins).all()) if L > 0 else (len(e_ins) == 0)
    lv_is_zero = bool(lv_ins == 0.0)
    calc_is_empty = bool(calc_list == [])

    c_pass = is_all_nan and lv_is_zero and calc_is_empty and len(e_ins) == L
    insufficient_results[f"len_{L}"] = {
        "len": len(e_ins),
        "all_nan": is_all_nan,
        "last_valid_zero": lv_is_zero,
        "calc_ema_empty": calc_is_empty,
        "pass": c_pass
    }
    if not c_pass:
        all_insuff_pass = False

ema_tests["5.1_insufficient_data_lt_50"] = {
    "details": insufficient_results,
    "pass": all_insuff_pass
}

# Test 5.2: Exactly 50 bars (Seed condition matches exact arithmetic mean)
p_50 = np.array([100.0 + i for i in range(50)])
e_50 = compute_ema(p_50, period=50)
calc_50 = calculate_ema(list(p_50), period=50)

expected_sma_50 = float(np.mean(p_50[:50]))
actual_seed_val = float(e_50[49])
first_49_nan = bool(np.isnan(e_50[:49]).all())
seed_exact_match = bool(abs(actual_seed_val - expected_sma_50) < 1e-12)
calc_ema_match = bool(len(calc_50) == 1 and abs(calc_50[0] - expected_sma_50) < 1e-12)

ema_tests["5.2_boundary_seed_matches_sma_exact"] = {
    "input_len": len(p_50),
    "output_len": len(e_50),
    "first_49_are_nan": first_49_nan,
    "expected_sma_mean": expected_sma_50,
    "actual_seed_at_49": actual_seed_val,
    "diff": abs(actual_seed_val - expected_sma_50),
    "seed_matches_exact": seed_exact_match,
    "calc_ema_list_len": len(calc_50),
    "calc_ema_matches": calc_ema_match,
    "pass": bool(first_49_nan and seed_exact_match and calc_ema_match)
}

# Test 5.3: Length >= 50 (Recursive Smoothing Check for 100 bars)
p_100 = np.array([50.0 + 0.5 * i + 5.0 * math.sin(i / 5.0) for i in range(100)])
e_100 = compute_ema(p_100, period=50)
calc_100 = calculate_ema(list(p_100), period=50)

# Manually verify recursive Wilder formula step-by-step
k = 2.0 / (50 + 1)
manual_ema = np.full(100, np.nan)
manual_ema[49] = np.mean(p_100[:50])
for i in range(50, 100):
    manual_ema[i] = p_100[i] * k + manual_ema[i - 1] * (1.0 - k)

step_diffs = np.abs(e_100[49:] - manual_ema[49:])
max_step_diff = float(np.max(step_diffs))
all_steps_match = bool(max_step_diff < 1e-12)
all_subsequent_valid = bool(np.isfinite(e_100[49:]).all())
calc_ema_subsequent_match = bool(np.allclose(calc_100, e_100[49:], atol=1e-12))

ema_tests["5.3_length_100_recursive_step_verification"] = {
    "output_len": len(e_100),
    "valid_elements_count": int(np.isfinite(e_100).sum()),
    "expected_valid_elements": 51,
    "max_discrepancy_vs_manual": max_step_diff,
    "all_steps_match_1e_12": all_steps_match,
    "all_subsequent_finite": all_subsequent_valid,
    "calc_ema_matches_compute_ema": calc_ema_subsequent_match,
    "final_value": float(e_100[-1]),
    "pass": bool(all_steps_match and all_subsequent_valid and calc_ema_subsequent_match)
}

phase_5_overall_pass = all(t["pass"] for t in ema_tests.values())
results["Phase_5_EMA50"] = {
    "status": "PASS" if phase_5_overall_pass else "FAIL",
    "tests": ema_tests
}


# ==============================================================================
# PHASE 6: LOOK-AHEAD & CAUSALITY INVARIANT VERIFICATION
# ==============================================================================
causality_tests = {}

np.random.seed(1337)
N = 60
base_prices = 100.0 + np.cumsum(np.random.normal(0.1, 1.0, N))
base_high = base_prices + np.abs(np.random.normal(0.5, 0.2, N))
base_low = base_prices - np.abs(np.random.normal(0.5, 0.2, N))
base_close = base_prices + np.random.normal(0.0, 0.2, N)

# Base indicator calculations on historical window [0..N-1]
base_ema12 = compute_ema(base_prices, 12)
base_ema50 = compute_ema(base_prices, 50)
base_rsi = compute_rsi(base_prices, 14)
base_macd, base_sig, base_hist = compute_macd(base_prices, 12, 26, 9)
base_bb_u, base_bb_m, base_bb_l = compute_bollinger(base_prices, 20, 2.0)
base_atr = compute_atr(base_high, base_low, base_close, 14)

def compare_causality(arr_base, arr_future, name):
    sub = arr_future[:N]
    nan_match = np.array_equal(np.isnan(arr_base), np.isnan(sub))
    if not nan_match:
        return False, f"{name}: NaN mask changed"
    valid = ~np.isnan(arr_base)
    if not np.allclose(arr_base[valid], sub[valid], atol=1e-12):
        max_err = np.max(np.abs(arr_base[valid] - sub[valid]))
        return False, f"{name}: values altered by future (max err={max_err})"
    return True, "Identical"

scenarios = {
    "scenario_1_massive_moonshot_spike": {
        "future_prices": np.array([1000.0, 5000.0, 10000.0]),
        "future_high": np.array([1050.0, 5100.0, 10200.0]),
        "future_low": np.array([950.0, 4900.0, 9800.0]),
        "future_close": np.array([1000.0, 5000.0, 10000.0]),
    },
    "scenario_2_catastrophic_flash_crash": {
        "future_prices": np.array([1.0, 0.1, 0.01]),
        "future_high": np.array([2.0, 0.2, 0.02]),
        "future_low": np.array([0.5, 0.05, 0.005]),
        "future_close": np.array([1.0, 0.1, 0.01]),
    },
    "scenario_3_extreme_volatility_50_bars": {
        "future_prices": 100.0 + np.random.normal(0, 50.0, 50),
        "future_high": 150.0 + np.random.normal(0, 50.0, 50),
        "future_low": 50.0 + np.random.normal(0, 50.0, 50),
        "future_close": 100.0 + np.random.normal(0, 50.0, 50),
    },
    "scenario_4_flat_line_50_bars": {
        "future_prices": np.full(50, 100.0),
        "future_high": np.full(50, 101.0),
        "future_low": np.full(50, 99.0),
        "future_close": np.full(50, 100.0),
    },
    "scenario_5_single_incremental_bar": {
        "future_prices": np.array([105.0]),
        "future_high": np.array([106.0]),
        "future_low": np.array([104.0]),
        "future_close": np.array([105.0]),
    }
}

all_causality_pass = True
for sc_name, sc_data in scenarios.items():
    ext_prices = np.concatenate([base_prices, sc_data["future_prices"]])
    ext_high = np.concatenate([base_high, sc_data["future_high"]])
    ext_low = np.concatenate([base_low, sc_data["future_low"]])
    ext_close = np.concatenate([base_close, sc_data["future_close"]])

    fut_ema12 = compute_ema(ext_prices, 12)
    fut_ema50 = compute_ema(ext_prices, 50)
    fut_rsi = compute_rsi(ext_prices, 14)
    fut_macd, fut_sig, fut_hist = compute_macd(ext_prices, 12, 26, 9)
    fut_bb_u, fut_bb_m, fut_bb_l = compute_bollinger(ext_prices, 20, 2.0)
    fut_atr = compute_atr(ext_high, ext_low, ext_close, 14)

    checks = [
        compare_causality(base_ema12, fut_ema12, "EMA12"),
        compare_causality(base_ema50, fut_ema50, "EMA50"),
        compare_causality(base_rsi, fut_rsi, "RSI14"),
        compare_causality(base_macd, fut_macd, "MACD_line"),
        compare_causality(base_sig, fut_sig, "MACD_signal"),
        compare_causality(base_hist, fut_hist, "MACD_hist"),
        compare_causality(base_bb_u, fut_bb_u, "BB_upper"),
        compare_causality(base_bb_m, fut_bb_m, "BB_mid"),
        compare_causality(base_bb_l, fut_bb_l, "BB_lower"),
        compare_causality(base_atr, fut_atr, "ATR14"),
    ]

    sc_pass = all(c[0] for c in checks)
    if not sc_pass:
        all_causality_pass = False
    causality_tests[sc_name] = {
        "pass": sc_pass,
        "failures": [c[1] for c in checks if not c[0]]
    }

results["Causality_LookAhead"] = {
    "status": "PASS" if all_causality_pass else "FAIL",
    "tests": causality_tests
}

overall_verdict = "APPROVE" if (phase_3_overall_pass and phase_4_overall_pass and phase_5_overall_pass and all_causality_pass) else "REJECT"
results["Overall_Verdict"] = overall_verdict

print("=== BEGIN JSON OUTPUT ===")
print(json.dumps(results, indent=2))
print("=== END JSON OUTPUT ===")
"""

def run():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting to VPS 148.113.9.103:20069...")
    client.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)
    print("Connected.")

    # Write test script to a temporary file on VPS in /tmp
    remote_test_path = "/tmp/test_adversarial_indicators_challenger.py"
    sftp = client.open_sftp()
    with sftp.file(remote_test_path, 'w') as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    print(f"Uploaded adversarial test harness to {remote_test_path}")

    # Execute with VPS venv python
    cmd = f"cd /opt/project-alpha && PYTHONPATH=. /opt/project-alpha/.venv/bin/python3 {remote_test_path}"
    print(f"Executing: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    
    out = stdout.read().decode()
    err = stderr.read().decode()
    exit_status = stdout.channel.recv_exit_status()
    print(f"Process exit status: {exit_status}")
    if err:
        print("STDERR:\n", err)
    
    # Clean up temp test script
    client.exec_command(f"rm -f {remote_test_path}")
    client.close()

    # Parse and save output
    if "=== BEGIN JSON OUTPUT ===" in out and "=== END JSON OUTPUT ===" in out:
        json_str = out.split("=== BEGIN JSON OUTPUT ===")[1].split("=== END JSON OUTPUT ===")[0].strip()
        data = json.loads(json_str)
        with open("adversarial_test_results.json", "w") as f:
            json.dump(data, f, indent=2)
        print("Test results saved to adversarial_test_results.json")
        print(f"Overall Verdict: {data.get('Overall_Verdict')}")
    else:
        print("Full raw output:\n", out)

if __name__ == '__main__':
    run()
