import json
import os
import sys
import paramiko

VPS_HOST = "148.113.9.103"
VPS_PORT = 20069
VPS_USER = "root"
VPS_PASS = "SMT6SiQU2nIUMj0V"

def run_ssh_command(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    code = stdout.channel.recv_exit_status()
    return code, out, err

def main():
    print("Connecting to VPS via SSH...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS, timeout=15)
    print("Connected successfully.")

    results = {}

    # 1. Remote Git Status and Diffs
    print("Executing Git checks...")
    code, out, err = run_ssh_command(ssh, "cd /opt/project-alpha && git status --porcelain")
    results['git_status_opt'] = {"code": code, "out": out.strip(), "err": err.strip()}

    code, out, err = run_ssh_command(ssh, "cd /opt/project-alpha && git diff")
    results['git_diff_opt'] = {"code": code, "out": out.strip(), "err": err.strip()}

    code, out, err = run_ssh_command(ssh, "cd /opt/project-alpha && git log -1 --oneline")
    results['git_log_opt'] = {"code": code, "out": out.strip(), "err": err.strip()}

    code, out, err = run_ssh_command(ssh, "cd /root/PROJECT-ALPHA && git status --porcelain")
    results['git_status_root'] = {"code": code, "out": out.strip(), "err": err.strip()}

    code, out, err = run_ssh_command(ssh, "cd /root/PROJECT-ALPHA && git diff")
    results['git_diff_root'] = {"code": code, "out": out.strip(), "err": err.strip()}

    code, out, err = run_ssh_command(ssh, "cd /root/PROJECT-ALPHA && git log -1 --oneline")
    results['git_log_root'] = {"code": code, "out": out.strip(), "err": err.strip()}

    # 2. File and Checksum Checks
    print("Executing File and Checksum checks...")
    code, out, err = run_ssh_command(ssh, "wc -l /opt/project-alpha/scanner/research/indicators.py")
    results['wc_indicators'] = {"code": code, "out": out.strip()}

    code, out, err = run_ssh_command(ssh, "sha256sum /opt/project-alpha/scanner/research/indicators.py")
    results['sha256_indicators'] = {"code": code, "out": out.strip()}

    code, out, err = run_ssh_command(ssh, "test -f /opt/project-alpha/scanner/indicators.py && echo EXISTS || echo NOT_FOUND")
    results['check_legacy_indicators'] = {"code": code, "out": out.strip()}

    code, out, err = run_ssh_command(ssh, "test -f /opt/project-alpha/tests/test_v2_indicators.py && echo EXISTS || echo NOT_FOUND")
    results['check_legacy_test'] = {"code": code, "out": out.strip()}

    code, out, err = run_ssh_command(ssh, "sha256sum /opt/project-alpha/tests/test_indicator_calculations.py")
    results['sha256_tests'] = {"code": code, "out": out.strip()}

    # 3. Unit Test Suite Execution on VPS
    print("Executing Test Suite on VPS...")
    # 3a. Direct pytest execution (expect collection error)
    code, out, err = run_ssh_command(ssh, "cd /opt/project-alpha && .venv/bin/pytest tests/test_indicator_calculations.py -v")
    results['pytest_direct'] = {"code": code, "out": out.strip(), "err": err.strip()}

    # 3b. Module-level execution (expect 6 passed)
    code, out, err = run_ssh_command(ssh, "cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v")
    results['pytest_module'] = {"code": code, "out": out.strip(), "err": err.strip()}

    # 3c. Research indicator tests
    code, out, err = run_ssh_command(ssh, "cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_v2_coin_research.py -k 'computation or bands or atr' -v")
    results['pytest_research'] = {"code": code, "out": out.strip(), "err": err.strip()}

    # 4. Manual Reference Validation Python Script on VPS
    print("Executing Manual Reference Validation Python script on VPS...")
    ref_validation_script = """
import sys
sys.path.insert(0, '/opt/project-alpha')
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
    last_valid,
)
from scanner.market_context import calculate_ema

out = {}

# --- Phase 3: RSI Validation ---
# Monotonic uptrend
p_up = np.array([10.0 + 2.0 * i for i in range(30)])
rsi_up = compute_rsi(p_up, 14)
# Monotonic downtrend
p_down = np.array([100.0 - 2.0 * i for i in range(30)])
rsi_down = compute_rsi(p_down, 14)
# Flat prices
p_flat = np.array([50.0] * 30)
rsi_flat = compute_rsi(p_flat, 14)
# Insufficient
p_short = np.array([10.0, 12.0, 14.0, 16.0])
rsi_short = compute_rsi(p_short, 14)

out['rsi'] = {
    'uptrend_final': float(last_valid(rsi_up)),
    'uptrend_overbought_gt_70': bool(last_valid(rsi_up) > 70.0),
    'downtrend_final': float(last_valid(rsi_down)),
    'downtrend_oversold_lt_30': bool(last_valid(rsi_down) < 30.0),
    'flat_final': float(last_valid(rsi_flat)),
    'flat_non_nan': bool(not np.isnan(last_valid(rsi_flat))),
    'short_all_nan': bool(np.isnan(rsi_short).all()),
    'warmup_nan_count': int(np.isnan(rsi_up[:14]).sum())
}

# --- Phase 4: MACD Validation ---
p_macd = np.array([100.0 + (i % 5) * 2.0 + i for i in range(40)])
macd, signal, hist = compute_macd(p_macd, 12, 26, 9)
df = pd.DataFrame({'macd': macd, 'signal': signal, 'hist': hist})
final_macd = float(df['macd'].iloc[-1])
final_signal = float(df['signal'].iloc[-1])
final_hist = float(df['hist'].iloc[-1])

valid_mask = ~df['signal'].isna()
diff_identity = np.abs(df['hist'][valid_mask] - (df['macd'][valid_mask] - df['signal'][valid_mask]))
max_diff = float(diff_identity.max())

out['macd'] = {
    'shape': list(df.shape),
    'columns': list(df.columns),
    'final_macd': final_macd,
    'final_signal': final_signal,
    'final_hist': final_hist,
    'all_final_non_null': bool(not df.iloc[-1].isna().any()),
    'identity_max_discrepancy': max_diff,
    'identity_holds_exact': bool(max_diff < 1e-6),
    'macd_nan_count': int(df['macd'].isna().sum()),
    'signal_nan_count': int(df['signal'].isna().sum()),
    'hist_nan_count': int(df['hist'].isna().sum())
}

# --- Phase 5: EMA50 Validation ---
p_ema_10 = np.array([100.0 + i for i in range(10)])
p_ema_49 = np.array([100.0 + i for i in range(49)])
p_ema_50 = np.array([100.0 + i for i in range(50)])
p_ema_80 = np.array([100.0 + i for i in range(80)])

ema_10 = compute_ema(p_ema_10, 50)
ema_49 = compute_ema(p_ema_49, 50)
ema_50 = compute_ema(p_ema_50, 50)
ema_80 = compute_ema(p_ema_80, 50)

calc_ema_49 = calculate_ema(list(p_ema_49), 50)
calc_ema_50 = calculate_ema(list(p_ema_50), 50)
calc_ema_80 = calculate_ema(list(p_ema_80), 50)

sma_seed_50 = float(np.mean(p_ema_50[:50]))

out['ema50'] = {
    'lt50_all_nan': bool(np.isnan(ema_49).all()),
    'lt50_calc_ema_empty': bool(len(calc_ema_49) == 0),
    'exact50_seed_val': float(ema_50[49]),
    'exact50_sma_seed': sma_seed_50,
    'exact50_seed_matches': bool(abs(ema_50[49] - sma_seed_50) < 1e-9),
    'exact50_calc_ema': [float(x) for x in calc_ema_50],
    'gt50_final_val': float(ema_80[-1]),
    'gt50_calc_ema_final': float(calc_ema_80[-1]),
    'gt50_matches_calc_ema': bool(abs(ema_80[-1] - calc_ema_80[-1]) < 1e-9)
}

# --- Look-Ahead Invariance Verification ---
np.random.seed(42)
p_base = np.cumsum(np.random.randn(60)) + 100.0
p_ext = np.append(p_base, [200.0, 50.0, 500.0]) # extreme shocks in future

rsi_base = compute_rsi(p_base, 14)
rsi_ext = compute_rsi(p_ext, 14)[:60]
rsi_lookahead = bool(np.allclose(rsi_base, rsi_ext, equal_nan=True, atol=1e-12))

ema_base = compute_ema(p_base, 20)
ema_ext = compute_ema(p_ext, 20)[:60]
ema_lookahead = bool(np.allclose(ema_base, ema_ext, equal_nan=True, atol=1e-12))

m_base, s_base, h_base = compute_macd(p_base)
m_ext, s_ext, h_ext = compute_macd(p_ext)
macd_lookahead = bool(
    np.allclose(m_base, m_ext[:60], equal_nan=True, atol=1e-12) and
    np.allclose(s_base, s_ext[:60], equal_nan=True, atol=1e-12) and
    np.allclose(h_base, h_ext[:60], equal_nan=True, atol=1e-12)
)

out['lookahead'] = {
    'rsi_clean': rsi_lookahead,
    'ema_clean': ema_lookahead,
    'macd_clean': macd_lookahead
}

print(json.dumps(out))
"""
    # Write script to remote /tmp/ref_audit.py and execute
    sftp = ssh.open_sftp()
    with sftp.file('/tmp/ref_audit.py', 'w') as f:
        f.write(ref_validation_script)
    sftp.close()

    code, out, err = run_ssh_command(ssh, "cd /opt/project-alpha && .venv/bin/python3 /tmp/ref_audit.py")
    try:
        results['ref_validation'] = json.loads(out.strip())
    except Exception as e:
        results['ref_validation'] = {"code": code, "raw_out": out, "err": err, "parse_error": str(e)}

    # 5. Live SQLite & Process Inspection
    print("Executing Live SQLite and Systemd checks...")
    code, out, err = run_ssh_command(ssh, "systemctl status project-alpha-v2.service --no-pager")
    results['service_status'] = {"code": code, "out": out.strip()}

    code, out, err = run_ssh_command(ssh, "lsof /opt/project-alpha/v2/data/alpha_v2.db")
    results['lsof_db'] = {"code": code, "out": out.strip()}

    db_inspect_script = """
import sqlite3
import json
from datetime import datetime, timezone

db_path = '/opt/project-alpha/v2/data/alpha_v2.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get total signals count
cur.execute("SELECT count(*) as c, max(generated_at) as max_gen FROM signals")
row = cur.fetchone()
total_signals = row['c']
max_generated_at = row['max_gen']

# Count today
cur.execute("SELECT count(*) as c FROM signals WHERE generated_at LIKE '2026-09-17%'")
count_today = cur.fetchone()['c']

# Get latest 5 signals
cur.execute("SELECT id, coin, pair, market_state, score, generated_at, raw_payload FROM signals ORDER BY generated_at DESC LIMIT 5")
recent_signals = []
for r in cur.fetchall():
    payload_str = r['raw_payload']
    payload = json.loads(payload_str) if payload_str else {}
    recent_signals.append({
        'id': r['id'],
        'coin': r['coin'],
        'pair': r['pair'],
        'market_state': r['market_state'],
        'score': r['score'],
        'generated_at': r['generated_at'],
        'rsi': payload.get('rsi'),
        'atr_pct': payload.get('atr_pct'),
        'volume_24h': payload.get('volume_24h'),
        'volume_ratio': payload.get('volume_ratio'),
        'mtf_alignment': payload.get('mtf_alignment'),
        'mtf_timeframes': payload.get('mtf_timeframes'),
        'strategy': payload.get('strategy')
    })

# Check legacy DB
legacy_db_path = '/opt/project-alpha/data/project_alpha.db'
leg_conn = sqlite3.connect(legacy_db_path)
leg_cur = leg_conn.cursor()
leg_cur.execute("SELECT count(*), max(generated_at) FROM signals")
leg_row = leg_cur.fetchone()

print(json.dumps({
    'active_db': {
        'path': db_path,
        'total_signals': total_signals,
        'max_generated_at': max_generated_at,
        'count_today': count_today,
        'recent_signals': recent_signals
    },
    'legacy_db': {
        'path': legacy_db_path,
        'total_signals': leg_row[0],
        'max_generated_at': leg_row[1]
    }
}))
"""
    sftp = ssh.open_sftp()
    with sftp.file('/tmp/db_audit.py', 'w') as f:
        f.write(db_inspect_script)
    sftp.close()

    code, out, err = run_ssh_command(ssh, "/opt/project-alpha/.venv/bin/python3 /tmp/db_audit.py")
    try:
        results['db_audit'] = json.loads(out.strip())
    except Exception as e:
        results['db_audit'] = {"code": code, "raw_out": out, "err": err, "parse_error": str(e)}

    # Journalctl logs
    code, out, err = run_ssh_command(ssh, "journalctl -u project-alpha-v2.service -n 25 --no-pager")
    results['journalctl'] = {"code": code, "out": out.strip()}

    # Clean up temp scripts
    run_ssh_command(ssh, "rm -f /tmp/ref_audit.py /tmp/db_audit.py")

    ssh.close()
    print("SSH connection closed.")

    out_file = "c:\\Users\\ASUS\\Documents\\GitHub\\PROJECT-ALPHA\\.agents\\victory_auditor_1\\independent_audit_results.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f"Results written to {out_file}")

if __name__ == '__main__':
    main()
