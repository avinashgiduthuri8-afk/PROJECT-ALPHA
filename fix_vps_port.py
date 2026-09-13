import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("148.113.9.103", port=20069, username="root", password="SMT6SiQU2nIUMj0V", timeout=15)

def run_cmd(cmd):
    print(f"--- {cmd} ---")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    print("[STDOUT]", out)
    print("[STDERR]", err)

# Find and kill process holding port 5001
run_cmd("fuser -k 5001/tcp || true")
run_cmd("netstat -tlpn | grep 5001 || true")

# Launch app using nohup
run_cmd("cd /root/PROJECT-ALPHA && nohup .venv/bin/python app.py > app.log 2>&1 &")

client.close()

