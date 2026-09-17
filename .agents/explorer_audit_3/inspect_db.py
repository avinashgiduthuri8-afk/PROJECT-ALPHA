import paramiko
import json

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_cmd = '''
/opt/project-alpha/.venv/bin/python3 -c "
import sqlite3
import json
from datetime import datetime, timezone

db_path = 'file:/opt/project-alpha/data/project_alpha.db?mode=ro'
conn = sqlite3.connect(db_path, uri=True)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. List all tables
cur.execute(\\"SELECT name FROM sqlite_master WHERE type='table'\\")
tables = [row['name'] for row in cur.fetchall()]
print('TABLES:', tables)

# 2. Check signals table schema
cur.execute(\\"PRAGMA table_info(signals)\\")
columns = cur.fetchall()
print('\\nSIGNALS COLUMNS:')
for col in columns:
    print(dict(col))

# 3. Total signals count
cur.execute(\\"SELECT count(*) as cnt FROM signals\\")
total_cnt = cur.fetchone()['cnt']
print(f'\\nTOTAL SIGNALS: {total_cnt}')

# 4. Current UTC time on VPS
now_utc = datetime.now(timezone.utc).isoformat()
print(f'CURRENT UTC: {now_utc}')

# 5. Top 5 most recent signals
cur.execute(\\"SELECT * FROM signals ORDER BY generated_at DESC LIMIT 5\\")
recent = cur.fetchall()
print(f'\\n5 MOST RECENT SIGNALS:')
for r in recent:
    rd = dict(r)
    payload_str = rd.get('raw_payload')
    payload = None
    if payload_str:
        try:
            payload = json.loads(payload_str)
        except:
            payload = payload_str[:100]
    print('---')
    print(f\\\"ID: {rd.get('id')}, Coin: {rd.get('coin')}, Pair: {rd.get('pair')}, Score: {rd.get('score')}\\\")
    print(f\\\"Generated At: {rd.get('generated_at')}, Expires At: {rd.get('expires_at')}\\\")
    print(f\\\"Source Bot: {rd.get('source_bot')}, Opportunity: {rd.get('opportunity_type')}\\\")
    if isinstance(payload, dict):
        print('Payload Keys:', list(payload.keys()))
        if 'indicators' in payload:
            print('Found indicators in raw_payload:', json.dumps(payload['indicators'], indent=2))
        else:
            print('Sample payload (first 10 keys/values):', {k: payload[k] for k in list(payload.keys())[:10]})

conn.close()
"
'''
    stdin, stdout, stderr = ssh.exec_command(py_cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    print("STDOUT:")
    print(out)
    if err:
        print("STDERR:")
        print(err)

    ssh.close()

if __name__ == '__main__':
    main()
