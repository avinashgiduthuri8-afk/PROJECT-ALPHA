import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = """
import hashlib

path = '/opt/project-alpha/scanner/research/indicators.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.splitlines()
print(f"File: {path}")
print(f"Line count: {len(lines)}")
print(f"Char count: {len(content)}")
print(f"MD5: {hashlib.md5(content.encode('utf-8')).hexdigest()}")
"""
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_script)
    stdin.channel.shutdown_write()
    print("STDOUT:\n", stdout.read().decode('utf-8', errors='replace'))
    print("STDERR:\n", stderr.read().decode('utf-8', errors='replace'))
    ssh.close()

if __name__ == '__main__':
    main()
