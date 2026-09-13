import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("148.113.9.103", port=20069, username="root", password="SMT6SiQU2nIUMj0V", timeout=15)

def run_cmd(cmd):
    print(f"\n--- {cmd} ---")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    if out:
        print(f"[STDOUT]\n{out}")
    if err:
        print(f"[STDERR]\n{err}")

# Update dependencies inside .venv
run_cmd("cd /root/PROJECT-ALPHA && .venv/bin/pip install -r requirements.txt")

# Stop old processes
run_cmd("pkill -f 'app.py' || true")
time.sleep(2)

# Start via .venv python
run_cmd("cd /root/PROJECT-ALPHA && nohup .venv/bin/python app.py > app.log 2>&1 &")
time.sleep(3)

# Inspect log & process status
run_cmd("ps aux | grep app.py | grep -v grep")
run_cmd("tail -n 25 /root/PROJECT-ALPHA/app.log")

client.close()

