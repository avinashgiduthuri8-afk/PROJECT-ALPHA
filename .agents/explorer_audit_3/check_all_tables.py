import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = """
import sqlite3
import json

for db in ['/opt/project-alpha/v2/data/alpha_v2.db', '/opt/project-alpha/data/project_alpha.db']:
    conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    cur = conn.cursor()
    print(f'=== DB: {db} ===')
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        cur.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cur.fetchall()]
        cur.execute(f"SELECT count(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"Table {t} ({cnt} rows): {cols}")
        if cnt > 0:
            cur.execute(f"SELECT * FROM {t} LIMIT 1")
            sample = cur.fetchone()
            sample_str = str(sample)[:120]
            # check if indicator/rsi/macd/ema anywhere in sample
            # print(f"   Sample: {sample_str}")
    conn.close()
"""
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_script)
    stdin.channel.shutdown_write()
    print("STDOUT:\n", stdout.read().decode('utf-8', errors='replace'))
    print("STDERR:\n", stderr.read().decode('utf-8', errors='replace'))
    ssh.close()

if __name__ == '__main__':
    main()
