import paramiko

remote_code = """
import numpy as np
from scanner.research.indicators import compute_ema, compute_rsi, compute_macd, compute_bollinger, compute_atr, compute_rvol

# 1. Look-ahead check: does future data affect past indicator values?
np.random.seed(42)
prices_base = np.random.uniform(100, 200, 50)
prices_extended = np.append(prices_base, [999.0, 1000.0, 1001.0])

ema_base = compute_ema(prices_base, 10)
ema_ext = compute_ema(prices_extended, 10)[:50]
ema_causal = bool(np.allclose(ema_base, ema_ext, equal_nan=True))

rsi_base = compute_rsi(prices_base, 14)
rsi_ext = compute_rsi(prices_extended, 14)[:50]
rsi_causal = bool(np.allclose(rsi_base, rsi_ext, equal_nan=True))

bb_u_b, bb_m_b, bb_l_b = compute_bollinger(prices_base, 20)
bb_u_e, bb_m_e, bb_l_e = compute_bollinger(prices_extended, 20)
bb_causal = bool(np.allclose(bb_u_b, bb_u_e[:50], equal_nan=True))

high_base = prices_base + 2.0
low_base = prices_base - 2.0
high_ext = prices_extended + 2.0
low_ext = prices_extended - 2.0
atr_base = compute_atr(high_base, low_base, prices_base, 14)
atr_ext = compute_atr(high_ext, low_ext, prices_extended, 14)[:50]
atr_causal = bool(np.allclose(atr_base, atr_ext, equal_nan=True))

macd_b, sig_b, hist_b = compute_macd(prices_base, 12, 26, 9)
macd_e, sig_e, hist_e = compute_macd(prices_extended, 12, 26, 9)
macd_causal = bool(np.allclose(macd_b, macd_e[:50], equal_nan=True))
sig_causal = bool(np.allclose(sig_b, sig_e[:50], equal_nan=True))

print("=== LOOK-AHEAD CAUSALITY CHECK ===")
print(f"EMA causal: {ema_causal}")
print(f"RSI causal: {rsi_causal}")
print(f"Bollinger causal: {bb_causal}")
print(f"ATR causal: {atr_causal}")
print(f"MACD line causal: {macd_causal}")
print(f"MACD signal causal: {sig_causal}")

# 2. Warm-up check:
print("\\n=== WARM-UP CHECK ===")
print(f"EMA(10) nan count: {int(np.isnan(ema_base).sum())} (expected 9)")
print(f"RSI(14) nan count: {int(np.isnan(rsi_base).sum())} (expected 14)")
print(f"BB(20) nan count: {int(np.isnan(bb_u_b).sum())} (expected 19)")
print(f"ATR(14) nan count: {int(np.isnan(atr_base).sum())} (expected 14)")
print(f"MACD line nan count: {int(np.isnan(macd_b).sum())} (expected 25)")
print(f"MACD signal nan count: {int(np.isnan(sig_b).sum())} (expected {25 + 8})")

# 3. Edge cases:
print("\\n=== EDGE CASES CHECK ===")
print(f"Empty array EMA: {compute_ema(np.array([]), 5).tolist()}")
print(f"Single value EMA: {compute_ema(np.array([10.0]), 5).tolist()}")
print(f"Zero variance RVOL (all 0 vol): {compute_rvol(np.zeros(25), 20)}")
print(f"Zero volume handled safely: {compute_rvol(np.zeros(25), 20) == 1.0}")
"""

host = "148.113.9.103"
port = 20069
user = "root"
password = "SMT6SiQU2nIUMj0V"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(hostname=host, port=port, username=user, password=password, timeout=15)
    cmd = f"cd /opt/project-alpha && .venv/bin/python3 -c '{remote_code}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    print(out)
    if err:
        print("STDERR:", err)
finally:
    client.close()
