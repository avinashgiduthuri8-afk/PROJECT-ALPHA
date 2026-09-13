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

run_cmd("cd /root/PROJECT-ALPHA && .venv/bin/python app.py")

client.close()

