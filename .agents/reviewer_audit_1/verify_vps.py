import base64
import hashlib
import json
import os
import sys
import paramiko

def run_ssh_command(client, cmd, input_data=None):
    stdin, stdout, stderr = client.exec_command(cmd)
    if input_data:
        stdin.write(input_data)
        stdin.channel.shutdown_write()
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    code = stdout.channel.recv_exit_status()
    return code, out, err

def main():
    host = "148.113.9.103"
    port = 20069
    user = "root"
    password = "SMT6SiQU2nIUMj0V"

    print("Connecting to VPS...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=user, password=password, timeout=15)
    print("Connected successfully.\n")

    # Adversarial Stress-Testing Script to run remotely
    stress_script = """
import numpy as np
import json
import math
from scanner.research.indicators import (
    compute_ema, compute_rsi, compute_macd, compute_bollinger,
    compute_atr, compute_rvol, compute_sma, last_valid
)

report = {}

# 1. Adversarial Look-Ahead Invariance Stress Test
np.random.seed(42)
T1 = 80
T2 = 120
p_initial = 100.0 + np.cumsum(np.random.normal(0, 1.5, T1))
p_future = np.zeros(T2)
p_future[:T1] = p_initial.copy()
# Inject extreme future shock in bars 80..119 (wild volatility)
p_future[T1:] = p_future[T1-1] + np.cumsum(np.random.normal(5.0, 10.0, T2 - T1))

# EMA
ema_init = compute_ema(p_initial, period=20)
ema_fut = compute_ema(p_future, period=20)
report['ema_lookahead_clean'] = bool(np.allclose(ema_init, ema_fut[:T1], equal_nan=True))

# RSI
rsi_init = compute_rsi(p_initial, period=14)
rsi_fut = compute_rsi(p_future, period=14)
report['rsi_lookahead_clean'] = bool(np.allclose(rsi_init, rsi_fut[:T1], equal_nan=True))

# Bollinger Bands
u_init, m_init, l_init = compute_bollinger(p_initial, period=20, std_dev=2.0)
u_fut, m_fut, l_fut = compute_bollinger(p_future, period=20, std_dev=2.0)
report['bollinger_upper_clean'] = bool(np.allclose(u_init, u_fut[:T1], equal_nan=True))
report['bollinger_mid_clean'] = bool(np.allclose(m_init, m_fut[:T1], equal_nan=True))
report['bollinger_lower_clean'] = bool(np.allclose(l_init, l_fut[:T1], equal_nan=True))

# MACD
macd_init, sig_init, h_init = compute_macd(p_initial, fast=12, slow=26, signal_period=9)
macd_fut, sig_fut, h_fut = compute_macd(p_future, fast=12, slow=26, signal_period=9)
report['macd_line_clean'] = bool(np.allclose(macd_init, macd_fut[:T1], equal_nan=True))
report['macd_signal_clean'] = bool(np.allclose(sig_init, sig_fut[:T1], equal_nan=True))
report['macd_hist_clean'] = bool(np.allclose(h_init, h_fut[:T1], equal_nan=True))

# ATR
h_initial = p_initial + np.random.uniform(0.5, 2.0, T1)
l_initial = p_initial - np.random.uniform(0.5, 2.0, T1)
c_initial = p_initial.copy()

h_future = np.zeros(T2)
l_future = np.zeros(T2)
c_future = np.zeros(T2)
h_future[:T1] = h_initial
l_future[:T1] = l_initial
c_future[:T1] = c_initial
h_future[T1:] = p_future[T1:] + np.random.uniform(5.0, 20.0, T2 - T1)
l_future[T1:] = p_future[T1:] - np.random.uniform(5.0, 20.0, T2 - T1)
c_future[T1:] = p_future[T1:]

atr_init = compute_atr(h_initial, l_initial, c_initial, period=14)
atr_fut = compute_atr(h_future, l_future, c_future, period=14)
report['atr_clean'] = bool(np.allclose(atr_init, atr_fut[:T1], equal_nan=True))

# SMA
sma_init = compute_sma(p_initial, period=10)
sma_fut = compute_sma(p_future, period=10)
report['sma_clean'] = bool(np.allclose(sma_init, sma_fut[:T1], equal_nan=True))

# 2. Warm-up Exact NaN Count Verification
N = 60
p_test = np.linspace(100, 200, N)
h_test = p_test + 1.0
l_test = p_test - 1.0
c_test = p_test

warmup = {}
# EMA(10): first 9 NaN
ema_res = compute_ema(p_test, 10)
warmup['ema_10_nan_count'] = int(np.isnan(ema_res).sum())
warmup['ema_10_first_valid'] = int(np.where(~np.isnan(ema_res))[0][0])

# RSI(14): first 14 NaN
rsi_res = compute_rsi(p_test, 14)
warmup['rsi_14_nan_count'] = int(np.isnan(rsi_res).sum())
warmup['rsi_14_first_valid'] = int(np.where(~np.isnan(rsi_res))[0][0])

# Bollinger(20): first 19 NaN
u, m, l = compute_bollinger(p_test, 20)
warmup['bb_20_nan_count'] = int(np.isnan(m).sum())
warmup['bb_20_first_valid'] = int(np.where(~np.isnan(m))[0][0])

# ATR(14): first 14 NaN
atr_res = compute_atr(h_test, l_test, c_test, 14)
warmup['atr_14_nan_count'] = int(np.isnan(atr_res).sum())
warmup['atr_14_first_valid'] = int(np.where(~np.isnan(atr_res))[0][0])

# MACD(12, 26, 9):
macd_l, macd_s, macd_h = compute_macd(p_test, 12, 26, 9)
warmup['macd_line_nan_count'] = int(np.isnan(macd_l).sum())
warmup['macd_line_first_valid'] = int(np.where(~np.isnan(macd_l))[0][0])
warmup['macd_signal_nan_count'] = int(np.isnan(macd_s).sum())
warmup['macd_signal_first_valid'] = int(np.where(~np.isnan(macd_s))[0][0])
warmup['macd_hist_nan_count'] = int(np.isnan(macd_h).sum())
warmup['macd_hist_first_valid'] = int(np.where(~np.isnan(macd_h))[0][0])

# SMA(10): first 9 NaN
sma_res = compute_sma(p_test, 10)
warmup['sma_10_nan_count'] = int(np.isnan(sma_res).sum())
warmup['sma_10_first_valid'] = int(np.where(~np.isnan(sma_res))[0][0])

report['warmup_analysis'] = warmup

# 3. Edge Cases & Hostile Inputs
edge = {}
# Empty arrays
empty_arr = np.array([], dtype=float)
edge['empty_ema_len'] = len(compute_ema(empty_arr, 10))
edge['empty_rsi_len'] = len(compute_rsi(empty_arr, 14))
em_m, em_s, em_h = compute_macd(empty_arr)
edge['empty_macd_lens'] = [len(em_m), len(em_s), len(em_h)]
em_u, em_mi, em_lo = compute_bollinger(empty_arr, 20)
edge['empty_bb_lens'] = [len(em_u), len(em_mi), len(em_lo)]
edge['empty_atr_len'] = len(compute_atr(empty_arr, empty_arr, empty_arr, 14))
edge['empty_rvol'] = compute_rvol(empty_arr, 20)
edge['empty_last_valid'] = last_valid(empty_arr)

# Single-element array
single = np.array([50.0])
edge['single_ema_is_nan'] = bool(np.isnan(compute_ema(single, 10)[0]))
edge['single_rsi_is_nan'] = bool(np.isnan(compute_rsi(single, 14)[0]))
s_m, s_s, s_h = compute_macd(single)
edge['single_macd_is_nan'] = bool(np.isnan(s_m[0]) and np.isnan(s_s[0]) and np.isnan(s_h[0]))
edge['single_rvol'] = compute_rvol(single, 20)
edge['single_last_valid'] = last_valid(single)

# Constant array (zero variance)
c_arr = np.full(50, 100.0)
c_rsi = compute_rsi(c_arr, 14)
edge['flat_rsi_value'] = float(last_valid(c_rsi))
cu, cm, cl = compute_bollinger(c_arr, 20)
edge['flat_bb_zero_spread'] = bool(np.allclose(cu[25:], cm[25:]) and np.allclose(cm[25:], cl[25:]))

# All zeros volume
zeros_vol = np.zeros(50)
edge['zeros_rvol'] = compute_rvol(zeros_vol, 20)

report['edge_cases'] = edge

print("STRESS_OUTPUT_START")
print(json.dumps(report, indent=2))
print("STRESS_OUTPUT_END")
"""

    b64_script = base64.b64encode(stress_script.encode('utf-8')).decode('ascii')
    cmd = f"cd /opt/project-alpha && .venv/bin/python3 -c \"import base64; exec(base64.b64decode('{b64_script}').decode('utf-8'))\""
    
    print("Executing Stress Test via base64 encoded payload...")
    c_s, o_s, e_s = run_ssh_command(client, cmd)
    print(f"Exit code: {c_s}")
    if e_s:
        print(f"Stderr: {e_s}")
    
    if "STRESS_OUTPUT_START" in o_s:
        json_text = o_s.split("STRESS_OUTPUT_START")[1].split("STRESS_OUTPUT_END")[0].strip()
        parsed = json.loads(json_text)
        print("Adversarial Stress Test Output Successfully Parsed:")
        print(json.dumps(parsed, indent=2))
    else:
        print("Raw Output:")
        print(o_s)

    client.close()

if __name__ == "__main__":
    main()
