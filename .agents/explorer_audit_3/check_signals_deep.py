import paramiko
import json

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = '''
/opt/project-alpha/.venv/bin/python3 -c "
import sqlite3
import json

for db_path in ['/opt/project-alpha/v2/data/alpha_v2.db', '/opt/project-alpha/data/project_alpha.db']:
    print('========================================')
    print('DB PATH:', db_path)
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur = conn.cursor()

    # Check PRAGMA table_info on all tables
    cur.execute(\\"SELECT name FROM sqlite_master WHERE type='table'\\")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        cur.execute(f'PRAGMA table_info({t})')
        cols = [c[1] for c in cur.fetchall()]
        if any('indicator' in c.lower() for c in cols):
            print(f'Table {t} has indicator columns: {cols}')

    # Check signals table raw_payload for 'indicator'
    cur.execute(\\"SELECT id, generated_at, raw_payload FROM signals ORDER BY generated_at DESC LIMIT 5\\")
    rows = cur.fetchall()
    print('\\nLATEST 5 SIGNALS FULL PAYLOAD:')
    for r in rows:
        sig_id, gen_at, raw_str = r
        print(f'--- Signal {sig_id} at {gen_at} ---')
        if raw_str:
            try:
                p = json.loads(raw_str)
                print(json.dumps(p, indent=2))
            except Exception as e:
                print('Error parsing JSON:', e)
        else:
            print('raw_payload is None or empty')

    # Search if ANY signal ever had 'indicators' in raw_payload
    cur.execute(\\"SELECT count(*) FROM signals WHERE raw_payload LIKE '%indicator%'\\")
    cnt_ind = cur.fetchone()[0]
    print(f'Signals containing \\'indicator\\' in raw_payload: {cnt_ind}')

    # Search if ANY signal has rsi, macd, ema
    cur.execute(\\"SELECT count(*) FROM signals WHERE raw_payload LIKE '%rsi%'\\")
    print('Signals with rsi in raw_payload:', cur.fetchone()[0])

    cur.execute(\\"SELECT count(*) FROM signals WHERE raw_payload LIKE '%macd%'\\")
    print('Signals with macd in raw_payload:', cur.fetchone()[0])

    cur.execute(\\"SELECT count(*) FROM signals WHERE raw_payload LIKE '%ema%'\\")
    print('Signals with ema in raw_payload:', cur.fetchone()[0])

    conn.close()
"
'''
    stdin, stdout, stderr = ssh.exec_command(py_script)
    print(stdout.read().decode('utf-8', errors='replace'))
    err = stderr.read().decode('utf-8', errors='replace')
    if err:
        print("ERR:", err)

    ssh.close()

if __name__ == '__main__':
    main()
