import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V')

def run(cmd, desc):
    print(f"\n=== {desc} ===")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print("STDOUT:\n" + out)
    if err:
        print("STDERR:\n" + err)
    return out, err

# Fix symlinks in .venv
run("ln -sf /usr/bin/python3 /opt/project-alpha/.venv/bin/python3 && ln -sf /usr/bin/python3 /opt/project-alpha/.venv/bin/python && chmod +x /opt/project-alpha/.venv/bin/*", "Fix .venv python symlinks")

# Kill any leftover process on port 5001
run("fuser -k 5001/tcp || true", "Free port 5001")

# Restart service
run("systemctl restart project-alpha", "Restart project-alpha service")

# Wait 15s for clean initialization
time.sleep(15)

# Verify
run("systemctl status project-alpha --no-pager", "Check service status")
run("tail -n 35 /opt/project-alpha/output.log", "Check recent output log")
client.close()
