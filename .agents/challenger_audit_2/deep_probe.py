import paramiko
import json

def run_deep_probe():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=30)
    
    remote_code = r'''
import sqlite3
import json
import os
import subprocess
from datetime import datetime, timezone

res = {}

# 1. Inspect systemd service file
try:
    with open("/etc/systemd/system/project-alpha-v2.service", "r") as f:
        res["systemd_service_file"] = f.read()
except Exception as e:
    res["systemd_service_file"] = str(e)

# 2. Check systemd environment or .env
try:
    if os.path.exists("/opt/project-alpha/.env"):
        with open("/opt/project-alpha/.env", "r") as f:
            env_lines = [l.strip() for l in f.readlines() if not l.startswith("#") and len(l.strip()) > 0]
            # Redact passwords/tokens
            safe_lines = []
            for l in env_lines:
                if any(sec in l.lower() for sec in ["token", "key", "secret", "password"]):
                    parts = l.split("=", 1)
                    safe_lines.append(f"{parts[0]}=REDACTED")
                else:
                    safe_lines.append(l)
            res["env_file"] = safe_lines
except Exception as e:
    res["env_file"] = str(e)

# 3. Check journalctl errors in the last 1 hour
try:
    p = subprocess.run(["journalctl", "-u", "project-alpha-v2.service", "--since", "1 hour ago", "-p", "err", "--no-pager"], capture_output=True, text=True)
    res["journalctl_err_priority"] = p.stdout.strip().splitlines()
except Exception as e:
    res["journalctl_err_priority"] = str(e)

# 4. Check all 14 signals generated today in alpha_v2.db
try:
    conn = sqlite3.connect("file:/opt/project-alpha/v2/data/alpha_v2.db?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, coin, pair, score, generated_at, raw_payload FROM signals WHERE generated_at >= '2026-09-17T00:00:00' ORDER BY generated_at ASC")
    today_rows = cur.fetchall()
    
    today_audit = []
    for r in today_rows:
        sig = {
            "id": r["id"],
            "coin": r["coin"],
            "pair": r["pair"],
            "score": r["score"],
            "generated_at": r["generated_at"],
            "payload_valid": False
        }
        raw_s = r["raw_payload"]
        if raw_s:
            try:
                p_json = json.loads(raw_s)
                sig["payload_valid"] = True
                sig["rsi"] = p_json.get("rsi")
                sig["atr_pct"] = p_json.get("atr_pct")
                sig["volume_24h"] = p_json.get("volume_24h")
                sig["volume_ratio"] = p_json.get("volume_ratio")
                sig["mtf_alignment"] = p_json.get("mtf_alignment")
                sig["score_in_payload"] = p_json.get("score")
                sig["strategy"] = p_json.get("strategy")
                sig["bot"] = p_json.get("bot")
            except Exception as e:
                sig["payload_error"] = str(e)
        today_audit.append(sig)
    res["signals_today_all_14"] = today_audit
    conn.close()
except Exception as e:
    res["signals_today_error"] = str(e)

# 5. Check if data/project_alpha.db has any open file handles
try:
    p = subprocess.run(["lsof", "/opt/project-alpha/data/project_alpha.db"], capture_output=True, text=True)
    res["lsof_project_alpha_db"] = p.stdout.strip()
except Exception as e:
    res["lsof_project_alpha_db"] = str(e)

try:
    p = subprocess.run(["lsof", "/opt/project-alpha/v2/data/alpha_v2.db"], capture_output=True, text=True)
    res["lsof_alpha_v2_db"] = p.stdout.strip()
except Exception as e:
    res["lsof_alpha_v2_db"] = str(e)

# 6. Check production health endpoint
try:
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:5001/health")
    with urllib.request.urlopen(req, timeout=5) as resp:
        res["health_endpoint"] = {"status": resp.getcode(), "body": json.loads(resp.read().decode())}
except Exception as e:
    res["health_endpoint"] = str(e)

print("===DEEP_PROBE_START===")
print(json.dumps(res, indent=2))
print("===DEEP_PROBE_END===")
'''
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(remote_code)
    stdin.channel.shutdown_write()
    
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    
    if "===DEEP_PROBE_START===" in out:
        raw_json = out.split("===DEEP_PROBE_START===")[1].split("===DEEP_PROBE_END===")[0].strip()
        parsed = json.loads(raw_json)
        with open("c:/Users/ASUS/Documents/GitHub/PROJECT-ALPHA/.agents/challenger_audit_2/deep_probe_results.json", "w") as f:
            json.dump(parsed, f, indent=2)
        print("[+] Deep probe results saved successfully.")
        print(json.dumps(parsed, indent=2)[:3000])
    else:
        print("[!] Full Output:\n", out)
        if err:
            print("[!] Stderr:\n", err)
            
    ssh.close()

if __name__ == "__main__":
    run_deep_probe()
