import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = """
import sqlite3
for db in ['/opt/project-alpha/v2/data/alpha_v2.db', '/opt/project-alpha/data/project_alpha.db']:
    conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    cur = conn.cursor()
    cur.execute("SELECT id, coin, generated_at, raw_payload FROM signals WHERE raw_payload LIKE '%indicator%'")
    rows = cur.fetchall()
    print(db, 'Matches count:', len(rows))
    for r in rows:
        print(r[0], r[1], r[2], r[3])
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
