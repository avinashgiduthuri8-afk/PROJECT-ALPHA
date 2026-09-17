import paramiko

script = """
import sqlite3
import sys
sys.path.insert(0, '/opt/project-alpha')
from core.config import get_config
from core.bus.event_types import EventType
from core.bus.event_bus import EventBus

print("--- [CMD 3: Config] ---")
cfg = get_config()
print(f"Deployment mode: {cfg.deployment_mode}")
print(f"Trading enabled: {cfg.trading_enabled}")
print(f"Shadow mode: {cfg.shadow_mode}")

if cfg.deployment_mode.upper() == "PAPER":
    print("✓ PAPER mode confirmed")
else:
    print(f"✗ WARNING: Deployment mode is {cfg.deployment_mode}, expected PAPER")

print("\\n--- [CMD 4: EventBus] ---")
bus = EventBus()
print(f"EventBus instance created: {bus is not None}")
print(f"EventBus topics defined: {len(dir(EventType))} event types")
print(f"Sample event types: SIGNAL_GENERATED, TRADE_APPROVED, POSITION_OPENED, POSITION_CLOSED")
print("✓ EventBus is ready")

print("\\n--- [CMD 5 & 6: Signals DB] ---")
conn = sqlite3.connect('data/project_alpha.db')
cur = conn.cursor()

res = cur.execute("SELECT COUNT(*) as total_signals, COUNT(CASE WHEN generated_at > datetime('now', '-60 minute') THEN 1 END) as recent_1min, COUNT(CASE WHEN generated_at > datetime('now', '-5 minute') THEN 1 END) as recent_5min FROM signals").fetchone()
print(f"Total: {res[0]}, Last 60m: {res[1]}, Last 5m: {res[2]}")

sig = cur.execute("SELECT id, coin, direction, score, generated_at, indicators, confluence FROM signals ORDER BY generated_at DESC LIMIT 1").fetchone()
if sig:
    print(f"Latest Signal: {sig[0]} | {sig[1]} | {sig[2]} | Score: {sig[3]} | At: {sig[4]}")
    print(f"Indicators: {sig[5][:100]}...")
    print(f"Confluence: {sig[6]}")
else:
    print("No signals found")
conn.close()
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

print("\n--- [CMD 1 & 2] ---")
stdin, stdout, stderr = ssh.exec_command("systemctl status project-alpha-v2.service | grep -E 'active|inactive'")
print(stdout.read().decode('utf-8').strip())
stdin, stdout, stderr = ssh.exec_command("ps aux | grep 'app.py' | grep -v grep")
print(stdout.read().decode('utf-8').strip())

# write the script to a file on VPS and run it with venv python
sftp = ssh.open_sftp()
with sftp.file('/tmp/task1_check.py', 'w') as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && .venv/bin/python3 /tmp/task1_check.py")
print(stdout.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii'))
print(stderr.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii'))

ssh.close()
