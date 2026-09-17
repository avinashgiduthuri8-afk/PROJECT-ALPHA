import paramiko
import json

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=30)

    py_script = """
import sqlite3
import json
from datetime import datetime, timezone, timedelta

results = {}

now_utc = datetime.now(timezone.utc)
five_mins_ago = now_utc - timedelta(minutes=5)
results["query_time_utc"] = now_utc.isoformat()
results["window_5m_start_utc"] = five_mins_ago.isoformat()

db_targets = {
    "project_alpha_db": "/opt/project-alpha/data/project_alpha.db",
    "alpha_v2_db": "/opt/project-alpha/v2/data/alpha_v2.db"
}

for label, db_path in db_targets.items():
    res = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()
    
    # 1. Total count
    cur.execute("SELECT count(*) FROM signals")
    res["total_signals"] = cur.fetchone()[0]
    
    # 2. Most recent signal
    cur.execute("SELECT id, coin, pair, score, generated_at, raw_payload FROM signals ORDER BY generated_at DESC LIMIT 1")
    latest_row = cur.fetchone()
    if latest_row:
        sig_id, coin, pair, score, gen_at, raw_payload_str = latest_row
        res["latest_signal"] = {
            "id": sig_id,
            "coin": coin,
            "pair": pair,
            "score": score,
            "generated_at": gen_at
        }
        try:
            gen_dt = datetime.fromisoformat(gen_at)
            diff_seconds = (now_utc - gen_dt).total_seconds()
            res["latest_signal"]["seconds_ago"] = round(diff_seconds, 1)
            res["latest_signal"]["minutes_ago"] = round(diff_seconds / 60.0, 2)
        except Exception as e:
            res["latest_signal"]["dt_parse_error"] = str(e)
            
        # Parse payload
        if raw_payload_str:
            try:
                payload = json.loads(raw_payload_str)
                res["latest_signal"]["payload_keys"] = list(payload.keys())
                
                # Check indicator fields
                res["latest_signal"]["indicator_fields"] = {
                    "rsi": payload.get("rsi"),
                    "rsi_is_valid": payload.get("rsi") is not None and isinstance(payload.get("rsi"), (int, float)),
                    "atr_pct": payload.get("atr_pct"),
                    "atr_pct_is_valid": payload.get("atr_pct") is not None and isinstance(payload.get("atr_pct"), (int, float)),
                    "volume_24h": payload.get("volume_24h"),
                    "volume_24h_is_valid": payload.get("volume_24h") is not None and isinstance(payload.get("volume_24h"), (int, float)),
                    "volume_ratio": payload.get("volume_ratio"),
                    "volume_ratio_is_valid": payload.get("volume_ratio") is not None and isinstance(payload.get("volume_ratio"), (int, float)),
                    "mtf_alignment": payload.get("mtf_alignment"),
                    "mtf_alignment_is_valid": payload.get("mtf_alignment") is not None,
                    "mtf_timeframes": payload.get("mtf_timeframes"),
                    "macd_in_payload": "macd" in payload,
                    "ema_in_payload": any("ema" in k for k in payload.keys()),
                    "indicators_key_in_payload": "indicators" in payload
                }
                res["latest_signal"]["full_payload"] = payload
            except Exception as e:
                res["latest_signal"]["payload_parse_error"] = str(e)
    else:
        res["latest_signal"] = None

    # 3. Signals in last 5 minutes
    # We check ISO timestamp string comparison and programmatic datetime parsing
    cur.execute("SELECT id, coin, pair, score, generated_at FROM signals WHERE generated_at >= ?", (five_mins_ago.isoformat(),))
    rows_5m = cur.fetchall()
    res["signals_last_5m_count"] = len(rows_5m)
    res["signals_last_5m"] = [
        {"id": r[0], "coin": r[1], "pair": r[2], "score": r[3], "generated_at": r[4]}
        for r in rows_5m
    ]
    
    # 4. Also check last 1 hour
    one_hour_ago = now_utc - timedelta(hours=1)
    cur.execute("SELECT id, coin, pair, score, generated_at FROM signals WHERE generated_at >= ?", (one_hour_ago.isoformat(),))
    rows_1h = cur.fetchall()
    res["signals_last_1h_count"] = len(rows_1h)
    res["signals_last_1h"] = [
        {"id": r[0], "coin": r[1], "pair": r[2], "score": r[3], "generated_at": r[4]}
        for r in rows_1h
    ]

    # 5. Check all signals generated today
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    cur.execute("SELECT count(*) FROM signals WHERE generated_at >= ?", (today_start,))
    res["signals_today_count"] = cur.fetchone()[0]

    conn.close()
    results[label] = res

# 6. Check recent system journal logs for scanner polls in last 5 minutes
import subprocess
try:
    log_cmd = ["journalctl", "-u", "project-alpha-v2.service", "--since", "5 minutes ago", "--no-pager"]
    proc = subprocess.run(log_cmd, capture_output=True, text=True)
    lines = proc.stdout.strip().splitlines()
    scanner_poll_lines = [l for l in lines if "scanner" in l.lower()]
    results["scanner_logs_last_5m"] = {
        "total_log_lines_last_5m": len(lines),
        "scanner_lines_last_5m": len(scanner_poll_lines),
        "sample_scanner_lines": scanner_poll_lines[-6:] if scanner_poll_lines else []
    }
except Exception as e:
    results["scanner_logs_last_5m"] = {"error": str(e)}

print(json.dumps(results, indent=2))
"""
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    print("STDOUT:\n", out)
    if err:
        print("STDERR:\n", err)
    ssh.close()

if __name__ == '__main__':
    main()
