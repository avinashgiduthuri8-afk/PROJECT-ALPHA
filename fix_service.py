import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')
commands = [
    "sed -i 's/-m v2.app_v2/app.py/g' /etc/systemd/system/project-alpha-v2.service",
    "systemctl daemon-reload",
    "systemctl stop project-alpha-v2.service",
    "systemctl start project-alpha-v2.service",
    "sleep 3",
    "systemctl status project-alpha-v2.service",
    "ps aux | grep app.py",
    "journalctl -u project-alpha-v2.service -n 50 --no-pager"
]
for c in commands:
    print(f"--- {c} ---")
    stdin, stdout, stderr = ssh.exec_command(c)
    print(stdout.read().decode('utf-8'))
    print(stderr.read().decode('utf-8'))
ssh.close()

