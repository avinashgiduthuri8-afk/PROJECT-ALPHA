import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = r"""
import os

with open('/opt/project-alpha/data/config_override.json', 'r') as f:
    print("config_override.json:\n", f.read())

environ = open('/proc/71891/environ', 'rb').read().split(b'\\x00')
for line in environ:
    s = line.decode('utf-8', errors='replace')
    if any(k in s.upper() for k in ['KEY', 'TOKEN', 'AUTH', 'ADMIN', 'SECRET']):
        # mask sensitive parts
        parts = s.split('=', 1)
        k = parts[0]
        v = parts[1] if len(parts) > 1 else ''
        masked_v = v[:4] + '...' + v[-4:] if len(v) > 8 else '***'
        print(f"{k}={masked_v}")
"""
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_script)
    stdin.channel.shutdown_write()
    print("STDOUT:\n", stdout.read().decode('utf-8', errors='replace'))
    print("STDERR:\n", stderr.read().decode('utf-8', errors='replace'))
    ssh.close()

if __name__ == '__main__':
    main()
