import paramiko
import base64

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V')

script = """import sqlite3
conn = sqlite3.connect('/opt/project-alpha/v2/data/alpha_v2.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT count(*) FROM positions")
print("Total Positions:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM positions WHERE coin='USELESS'")
print("USELESS Positions:", cur.fetchone()[0])
cur.execute("SELECT * FROM positions ORDER BY entry_time DESC LIMIT 5")
for r in cur.fetchall():
    print(dict(r))
conn.close()
"""
encoded = base64.b64encode(script.encode()).decode()
client.exec_command(f'echo "{encoded}" | base64 -d > /tmp/check.py')
stdin, stdout, stderr = client.exec_command('/opt/project-alpha/.venv/bin/python3 /tmp/check.py')
print(stdout.read().decode())
print(stderr.read().decode())
client.close()

