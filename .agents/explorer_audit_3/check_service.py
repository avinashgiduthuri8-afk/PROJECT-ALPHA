import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    def run(cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        return stdout.read().decode('utf-8', errors='replace').strip()

    print("=== Service Definition ===")
    print(run('systemctl cat project-alpha-v2.service'))

    print("\n=== Recent Service Logs ===")
    print(run('journalctl -u project-alpha-v2.service -n 40 --no-pager'))

    print("\n=== Database files list ===")
    print(run('ls -la /opt/project-alpha/data/ /opt/project-alpha/v2/data/ 2>/dev/null'))

    py_db_check = '''
/opt/project-alpha/.venv/bin/python3 -c "
import sqlite3
import json
from datetime import datetime, timezone

for path in ['/opt/project-alpha/data/project_alpha.db', '/opt/project-alpha/v2/data/alpha_v2.db']:
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        cur = conn.cursor()
        print(f'=== DB: {path} ===')
        cur.execute(\\"SELECT name FROM sqlite_master WHERE type=\'table\'\\")
        tables = [r[0] for r in cur.fetchall()]
        print('Tables:', tables)
        if 'signals' in tables:
            cur.execute(\\"SELECT count(*) FROM signals\\")
            print('Signals count:', cur.fetchone()[0])
            cur.execute(\\"SELECT id, coin, pair, score, generated_at, raw_payload FROM signals ORDER BY generated_at DESC LIMIT 3\\")
            rows = cur.fetchall()
            print('Top 3 recent signals:')
            for row in rows:
                print(' ', row[0], row[1], row[2], row[3], row[4])
                if row[5]:
                    try:
                        p = json.loads(row[5])
                        print('   payload keys:', list(p.keys()))
                        if 'indicators' in p:
                            print('   indicators found:', p['indicators'])
                    except Exception as e:
                        print('   payload parse error:', e)
        conn.close()
    except Exception as e:
        print(f'Error reading {path}: {e}')
"
'''
    print("\n=== DB Comparison Check ===")
    print(run(py_db_check))

    ssh.close()

if __name__ == '__main__':
    main()
