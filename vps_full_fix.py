import paramiko
import time

host = '148.113.9.103'
port = 20069
username = 'root'
password = 'SMT6SiQU2nIUMj0V'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, port, username, password)

def run_cmd(cmd):
    print(f"\n--- [CMD] {cmd} ---")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    ret = stdout.channel.recv_exit_status()
    if out:
        print(out.strip())
    if err:
        print(err.strip())
    return ret, out, err

print("=== Phase 1: Pre-flight Checks ===")
run_cmd("cd /opt/project-alpha && pwd")
run_cmd("cd /opt/project-alpha && git status")
run_cmd("cd /opt/project-alpha && git log --oneline -1")
run_cmd("systemctl status project-alpha-v2.service | grep Active")
run_cmd("ls -lh /opt/project-alpha/v2/data/alpha_v2.db")
run_cmd("ls -lh /opt/project-alpha/data/project_alpha.db 2>&1 | grep -E 'No such|project_alpha.db'")

print("\n=== Phase 2: Backup Verification ===")
run_cmd("ls -lh /opt/project-alpha/backups/alpha_v2.db.bak.20260917_103108")
run_cmd("sqlite3 /opt/project-alpha/backups/alpha_v2.db.bak.20260917_103108 'SELECT COUNT(*) as trade_count FROM trades;' 2>&1 || echo 'Query failed or table missing'")
run_cmd("sqlite3 /opt/project-alpha/backups/alpha_v2.db.bak.20260917_103108 '.tables'")

print("\n=== Phase 3: Stop the Service Gracefully ===")
run_cmd("systemctl stop project-alpha-v2.service")
time.sleep(5)
run_cmd("systemctl status project-alpha-v2.service | grep -i 'inactive\\|stopped'")
run_cmd("ps aux | grep 'v2.app_v2' | grep -v grep || echo 'Process confirmed stopped'")

print("\n=== Phase 4: Create Canonical Data Directory ===")
run_cmd("mkdir -p /opt/project-alpha/data")
run_cmd("ls -ld /opt/project-alpha/data")

print("\n=== Phase 5: Migrate the Legacy Database ===")
run_cmd("cp /opt/project-alpha/v2/data/alpha_v2.db /opt/project-alpha/data/project_alpha.db")
run_cmd("ls -lh /opt/project-alpha/data/project_alpha.db")
run_cmd("md5sum /opt/project-alpha/v2/data/alpha_v2.db /opt/project-alpha/data/project_alpha.db")

print("\n=== Phase 6: Advance the Repository Code ===")
run_cmd("cd /opt/project-alpha && git log --oneline -1")
run_cmd("cd /opt/project-alpha && git pull origin main")
run_cmd("cd /opt/project-alpha && git log --oneline -1")
run_cmd("cd /opt/project-alpha && git log --oneline | grep -i 'phase\\|market.*parser\\|CoinDCX' | head -5")

print("\n=== Phase 7: Schema Migration Check ===")
run_cmd("cd /opt/project-alpha && ls -la core/repository/migrations/ 2>/dev/null | wc -l || echo 'No migrations dir'")
run_cmd("cd /opt/project-alpha && head -20 core/repository/migrations/*.sql 2>/dev/null | grep -E '^==|CREATE TABLE' || echo 'No sql files'")
run_cmd("cd /opt/project-alpha && .venv/bin/python3 -c \"from core.repository.db import Database; db = Database('data/project_alpha.db'); print('Database initialized successfully')\" 2>&1")

print("\n=== Phase 8: Restart the Service ===")
run_cmd("systemctl start project-alpha-v2.service")
time.sleep(3)
run_cmd("systemctl status project-alpha-v2.service | grep -E 'active|inactive'")
run_cmd("ps aux | grep -E 'v2.app_v2|app.py' | grep -v grep")

print("\n=== Phase 9: Post-Restart Verification ===")
time.sleep(5)
run_cmd("lsof -p $(pgrep -f 'v2.app_v2|app.py') 2>/dev/null | grep '\\.db' | awk '{print $NF}'")
run_cmd("journalctl -u project-alpha-v2.service -n 50 --no-pager | grep -E 'raw_universe|Scanner Funnel|new_signals'")
run_cmd("journalctl -u project-alpha-v2.service -n 100 --no-pager | grep -i 'error\\|exception\\|fail' | head -20")

print("\n=== Phase 10: Final Validation ===")
time.sleep(30)
run_cmd("sqlite3 /opt/project-alpha/data/project_alpha.db \"SELECT COUNT(*) as recent_signals FROM signals WHERE generated_at > datetime('now', '-1 minute');\" 2>&1")
run_cmd("sqlite3 /opt/project-alpha/data/project_alpha.db \"SELECT coin, score, generated_at FROM signals ORDER BY generated_at DESC LIMIT 5;\" 2>&1")

ssh.close()

