import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = """
import os
import glob

print("Listing tests matching indicator or v2 on VPS:")
tests = glob.glob('/opt/project-alpha/tests/*indicator*') + glob.glob('/opt/project-alpha/tests/*coin_research*')
for t in tests:
    print(t)

for p in ['/opt/project-alpha/tests/test_v2_indicators.py', '/opt/project-alpha/tests/test_indicator_calculations.py']:
    print(p, 'exists:', os.path.exists(p))
"""
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_script)
    stdin.channel.shutdown_write()
    print("STDOUT:\n", stdout.read().decode('utf-8', errors='replace'))
    print("STDERR:\n", stderr.read().decode('utf-8', errors='replace'))
    ssh.close()

if __name__ == '__main__':
    main()
