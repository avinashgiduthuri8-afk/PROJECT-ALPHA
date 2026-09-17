import paramiko
import time

host = '148.113.9.103'
port = 20069
username = 'root'
password = 'SMT6SiQU2nIUMj0V'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, port, username, password)

def run_cmd(cmd):
    print(f"\n--- Running: {cmd} ---")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    if out:
        print(out.strip()[:2000])  # limit output just in case
    if err:
        print("STDERR:", err.strip()[:1000])

# 1. Check running python processes and systemd services
run_cmd("ps aux | grep -i python")
run_cmd("systemctl list-units | grep -i alpha")
run_cmd("systemctl status project-alpha-v2.service")

# 2. Find application logs and check around Sep 11
run_cmd("journalctl -u project-alpha-v2.service --since '2026-09-11 13:00:00' --until '2026-09-11 14:00:00' | tail -n 50")
run_cmd("journalctl -u project-alpha-v2.service --since '2026-09-13 00:00:00' --until '2026-09-13 12:00:00' | grep -i 'exception\\|error\\|traceback' | tail -n 50")
run_cmd("journalctl -u project-alpha-v2.service -n 100")

# 4. Check DB path of the running processes
run_cmd("lsof -c python3 | grep -i '\\.db'")

# 5. Check system resources (disk/memory) around stall time or current
run_cmd("df -h")
run_cmd("free -m")
run_cmd("dmesg -T | grep -i 'out of memory' | tail -n 10")
run_cmd("grep -i 'out of memory' /var/log/syslog | tail -n 10")

ssh.close()
