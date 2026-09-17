import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = """
import os

paths = [
    '/opt/project-alpha/scanner/indicators.py',
    '/opt/project-alpha/scanner/research/indicators.py',
    '/opt/project-alpha/v2/scanner/indicators.py',
    '/opt/project-alpha/scanner/market_context.py',
    '/opt/project-alpha/scanner/service.py'
]

for p in paths:
    print(f"{p}: exists={os.path.exists(p)}")
"""
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_script)
    stdin.channel.shutdown_write()
    print("STDOUT:\n", stdout.read().decode('utf-8', errors='replace'))
    print("STDERR:\n", stderr.read().decode('utf-8', errors='replace'))
    ssh.close()

if __name__ == '__main__':
    main()
