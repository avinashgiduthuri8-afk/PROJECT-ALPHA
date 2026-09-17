import paramiko
import json
import sys

def run_adversarial_verification():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    print("[*] Connecting to VPS 148.113.9.103:20069...")
    ssh.connect(
        hostname='148.113.9.103',
        port=20069,
        username='root',
        password='SMT6SiQU2nIUMj0V',
        timeout=30
    )
    print("[+] Connected successfully.")

    remote_code = r'''
import sqlite3
import json
import os
import sys
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

report = {}

# 1. Host time
now_utc = datetime.now(timezone.utc)
five_mins_ago = now_utc - timedelta(minutes=5)
fifteen_mins_ago = now_utc - timedelta(minutes=15)
one_hour_ago = now_utc - timedelta(hours=1)
today_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

report["vps_time_utc"] = now_utc.isoformat()
report["window_5m_start_utc"] = five_mins_ago.isoformat()
report["window_today_start_utc"] = today_start_utc.isoformat()

# 2. Inspect databases
dbs = {
    "project_alpha_db": "/opt/project-alpha/data/project_alpha.db",
    "alpha_v2_db": "/opt/project-alpha/v2/data/alpha_v2.db"
}

db_results = {}
for name, path in dbs.items():
    db_info = {
        "path": path,
        "exists": os.path.exists(path),
        "size_bytes": os.path.getsize(path) if os.path.exists(path) else None,
        "mtime_utc": datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat() if os.path.exists(path) else None
    }
    
    if os.path.exists(path):
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Check tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        db_info["tables"] = tables
        
        if "signals" in tables:
            # Columns
            cur.execute("PRAGMA table_info(signals)")
            cols = [r["name"] for r in cur.fetchall()]
            db_info["signals_columns"] = cols
            
            # Total count
            cur.execute("SELECT count(*) FROM signals")
            total_count = cur.fetchone()[0]
            db_info["total_signals"] = total_count
            
            # Latest signal
            cur.execute("SELECT * FROM signals ORDER BY generated_at DESC LIMIT 10")
            recent_rows = cur.fetchall()
            
            if recent_rows:
                latest_r = recent_rows[0]
                db_info["latest_signal_timestamp"] = latest_r["generated_at"]
                
                # Signals in last 5 minutes
                cur.execute("SELECT count(*) FROM signals WHERE generated_at >= ?", (five_mins_ago.isoformat(),))
                db_info["signals_last_5m_count"] = cur.fetchone()[0]
                
                # Signals in last 15 minutes
                cur.execute("SELECT count(*) FROM signals WHERE generated_at >= ?", (fifteen_mins_ago.isoformat(),))
                db_info["signals_last_15m_count"] = cur.fetchone()[0]
                
                # Signals in last 1 hour
                cur.execute("SELECT count(*) FROM signals WHERE generated_at >= ?", (one_hour_ago.isoformat(),))
                db_info["signals_last_1h_count"] = cur.fetchone()[0]
                
                # Signals today
                cur.execute("SELECT count(*) FROM signals WHERE generated_at >= ?", (today_start_utc.isoformat(),))
                db_info["signals_today_count"] = cur.fetchone()[0]
                
                # Audit recent signals' raw_payload
                audited_signals = []
                for row in recent_rows:
                    sig_id = row["id"]
                    coin = row["coin"]
                    pair = row["pair"]
                    score_col = row["score"]
                    gen_at = row["generated_at"]
                    raw_str = row["raw_payload"]
                    
                    sig_audit = {
                        "id": sig_id,
                        "coin": coin,
                        "pair": pair,
                        "score_col": score_col,
                        "generated_at": gen_at,
                        "raw_payload_present": raw_str is not None and len(raw_str.strip()) > 0,
                        "json_parse_ok": False,
                        "field_checks": {},
                        "errors": []
                    }
                    
                    if raw_str:
                        try:
                            payload = json.loads(raw_str)
                            sig_audit["json_parse_ok"] = True
                            
                            # Fields to verify: rsi, atr_pct, volume_24h, volume_ratio, mtf_alignment, score
                            # rsi
                            rsi_val = payload.get("rsi")
                            rsi_valid = rsi_val is not None and isinstance(rsi_val, (int, float)) and 0.0 <= rsi_val <= 100.0
                            sig_audit["field_checks"]["rsi"] = {"value": rsi_val, "valid": rsi_valid}
                            if not rsi_valid:
                                sig_audit["errors"].append(f"rsi invalid: {rsi_val}")
                                
                            # atr_pct
                            atr_val = payload.get("atr_pct")
                            atr_valid = atr_val is not None and isinstance(atr_val, (int, float)) and atr_val > 0
                            sig_audit["field_checks"]["atr_pct"] = {"value": atr_val, "valid": atr_valid}
                            if not atr_valid:
                                sig_audit["errors"].append(f"atr_pct invalid: {atr_val}")
                                
                            # volume_24h
                            vol_val = payload.get("volume_24h")
                            vol_valid = vol_val is not None and isinstance(vol_val, (int, float)) and vol_val >= 0
                            sig_audit["field_checks"]["volume_24h"] = {"value": vol_val, "valid": vol_valid}
                            if not vol_valid:
                                sig_audit["errors"].append(f"volume_24h invalid: {vol_val}")
                                
                            # volume_ratio
                            vr_val = payload.get("volume_ratio")
                            vr_valid = vr_val is not None and isinstance(vr_val, (int, float)) and vr_val >= 0
                            sig_audit["field_checks"]["volume_ratio"] = {"value": vr_val, "valid": vr_valid}
                            if not vr_valid:
                                sig_audit["errors"].append(f"volume_ratio invalid: {vr_val}")
                                
                            # mtf_alignment
                            mtf_val = payload.get("mtf_alignment")
                            mtf_valid = mtf_val is not None and (isinstance(mtf_val, bool) or isinstance(mtf_val, str))
                            sig_audit["field_checks"]["mtf_alignment"] = {"value": mtf_val, "valid": mtf_valid}
                            if not mtf_valid:
                                sig_audit["errors"].append(f"mtf_alignment invalid: {mtf_val}")
                                
                            # score
                            score_val = payload.get("score")
                            score_valid = score_val is not None and isinstance(score_val, (int, float)) and score_val >= 0
                            sig_audit["field_checks"]["score"] = {"value": score_val, "valid": score_valid}
                            if not score_valid:
                                sig_audit["errors"].append(f"score invalid: {score_val}")
                                
                        except Exception as ex:
                            sig_audit["json_parse_ok"] = False
                            sig_audit["errors"].append(f"JSON decode failed: {str(ex)}")
                    else:
                        sig_audit["errors"].append("raw_payload is empty or null")
                        
                    audited_signals.append(sig_audit)
                    
                db_info["audited_recent_signals"] = audited_signals
            else:
                db_info["audited_recent_signals"] = []
                db_info["latest_signal_timestamp"] = None
        conn.close()
    db_results[name] = db_info

report["databases"] = db_results

# 3. Service status & Journalctl logs
journal_res = {}
try:
    cmd_journal = ["journalctl", "-u", "project-alpha-v2.service", "-n", "50", "--no-pager"]
    p = subprocess.run(cmd_journal, capture_output=True, text=True)
    raw_journal = p.stdout.strip().splitlines()
    journal_res["line_count"] = len(raw_journal)
    
    # Check for error patterns
    error_lines = [line for line in raw_journal if any(err in line.lower() for err in ["error", "exception", "traceback", "failed", "critical"])]
    scanner_lines = [line for line in raw_journal if "scanner" in line.lower()]
    
    journal_res["error_lines_count"] = len(error_lines)
    journal_res["error_lines"] = error_lines
    journal_res["scanner_lines_count"] = len(scanner_lines)
    journal_res["last_10_scanner_lines"] = scanner_lines[-10:] if scanner_lines else []
    journal_res["last_5_raw_lines"] = raw_journal[-5:] if raw_journal else []
except Exception as ex:
    journal_res["error"] = str(ex)

report["journalctl"] = journal_res

# 4. HTTP API Endpoint query: /api/v2/scanner/coins
api_res = {}
url = "http://127.0.0.1:5001/api/v2/scanner/coins"
req = urllib.request.Request(url, headers={"X-API-Key": "alpha-prod-key"})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        status_code = resp.getcode()
        body = resp.read().decode("utf-8")
        api_res["status_code"] = status_code
        data = json.loads(body)
        
        # Analyze structure
        if isinstance(data, list):
            api_res["type"] = "list"
            api_res["total_candidates"] = len(data)
            if data:
                sample = data[0]
                api_res["sample_keys"] = list(sample.keys())
                api_res["sample_candidate"] = sample
                
                # Check indicator fields across all returned coins
                invalid_coins = []
                for c in data:
                    c_errs = []
                    if "rsi" not in c or c["rsi"] is None:
                        c_errs.append("missing or null rsi")
                    if "volume_24h" not in c or c["volume_24h"] is None:
                        c_errs.append("missing or null volume_24h")
                    if "volume_ratio" not in c or c["volume_ratio"] is None:
                        c_errs.append("missing or null volume_ratio")
                    if "mtf_alignment" not in c:
                        c_errs.append("missing mtf_alignment")
                    if "confluence_score" not in c:
                        c_errs.append("missing confluence_score")
                    if c_errs:
                        invalid_coins.append({"coin": c.get("coin") or c.get("symbol"), "errors": c_errs})
                api_res["invalid_coins_count"] = len(invalid_coins)
                api_res["invalid_coins"] = invalid_coins
        elif isinstance(data, dict):
            api_res["type"] = "dict"
            api_res["keys"] = list(data.keys())
            api_res["data"] = data
except urllib.error.HTTPError as e:
    api_res["status_code"] = e.code
    api_res["error"] = e.read().decode("utf-8", errors="replace")
except Exception as e:
    api_res["error"] = str(e)

report["api_scanner_coins"] = api_res

# 5. Query /api/v2/scanner/signals
signals_api_res = {}
url_sig = "http://127.0.0.1:5001/api/v2/scanner/signals"
req_sig = urllib.request.Request(url_sig, headers={"X-API-Key": "alpha-prod-key"})
try:
    with urllib.request.urlopen(req_sig, timeout=10) as resp:
        signals_api_res["status_code"] = resp.getcode()
        body_sig = resp.read().decode("utf-8")
        data_sig = json.loads(body_sig)
        signals_api_res["response_type"] = type(data_sig).__name__
        if isinstance(data_sig, list):
            signals_api_res["count"] = len(data_sig)
            if data_sig:
                signals_api_res["sample"] = data_sig[0]
        elif isinstance(data_sig, dict):
            signals_api_res["keys"] = list(data_sig.keys())
            signals_api_res["sample"] = data_sig
except Exception as e:
    signals_api_res["error"] = str(e)

report["api_scanner_signals"] = signals_api_res

print("===JSON_REPORT_START===")
print(json.dumps(report, indent=2))
print("===JSON_REPORT_END===")
'''
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(remote_code)
    stdin.channel.shutdown_write()
    
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    
    if err:
        print("[!] Stderr:", err)
    
    if "===JSON_REPORT_START===" in out:
        raw_json = out.split("===JSON_REPORT_START===")[1].split("===JSON_REPORT_END===")[0].strip()
        parsed = json.loads(raw_json)
        with open("c:/Users/ASUS/Documents/GitHub/PROJECT-ALPHA/.agents/challenger_audit_2/verification_results.json", "w") as f:
            json.dump(parsed, f, indent=2)
        print("[+] Saved verification_results.json successfully.")
        print(json.dumps(parsed, indent=2)[:3000]) # Print first 3000 chars
    else:
        print("[!] Full Output:\n", out)
        
    ssh.close()

if __name__ == "__main__":
    run_adversarial_verification()
