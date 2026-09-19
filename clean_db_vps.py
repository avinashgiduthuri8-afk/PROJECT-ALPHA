import paramiko
import base64

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V')

script = """import sqlite3
import json

conn = sqlite3.connect('/opt/project-alpha/v2/data/alpha_v2.db')
cur = conn.cursor()

# Delete fake coins entirely
cur.execute("DELETE FROM positions WHERE coin IN ('USELESS', 'C')")
cur.execute("DELETE FROM signals WHERE coin IN ('USELESS', 'C')")

# Force close all other currently open positions so capital frees up
cur.execute("UPDATE positions SET status='CLOSED', exit_price=current_price, exit_reason='ADMIN_RESET', closed_at=datetime('now') WHERE status != 'CLOSED'")

conn.commit()
conn.close()
"""
encoded = base64.b64encode(script.encode()).decode()
client.exec_command(f'echo "{encoded}" | base64 -d > /tmp/clean_db.py')
stdin, stdout, stderr = client.exec_command('/opt/project-alpha/.venv/bin/python3 /tmp/clean_db.py')
print(stdout.read().decode())
print(stderr.read().decode())
client.close()

