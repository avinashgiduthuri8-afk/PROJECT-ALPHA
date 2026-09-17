import paramiko

script = """
import sqlite3
conn = sqlite3.connect('/opt/project-alpha/data/project_alpha.db')
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM decision_divergences WHERE detected_at > '2026-09-17'")
print(cur.fetchone()[0])
conn.close()
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')
sftp = ssh.open_sftp()
with sftp.file('/tmp/task_risk_today.py', 'w') as f: f.write(script)
sftp.close()
stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && .venv/bin/python3 /tmp/task_risk_today.py")
print("CHECKS TODAY:", stdout.read().decode('utf-8').strip())
ssh.close()

