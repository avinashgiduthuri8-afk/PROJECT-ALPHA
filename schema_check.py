import paramiko

script = """
import sqlite3

def print_schema(cur, table):
    print(f"\\n--- {table} ---")
    cur.execute(f"PRAGMA table_info({table})")
    for r in cur.fetchall():
        print(r)

conn = sqlite3.connect('/opt/project-alpha/data/project_alpha.db')
cur = conn.cursor()

print_schema(cur, 'signals')
print_schema(cur, 'ai_analyses')
print_schema(cur, 'decision_divergences')
print_schema(cur, 'orders')
print_schema(cur, 'positions')
conn.close()
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

sftp = ssh.open_sftp()
with sftp.file('/tmp/task_schema.py', 'w') as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && .venv/bin/python3 /tmp/task_schema.py")
print(stdout.read().decode('utf-8').strip())

ssh.close()

