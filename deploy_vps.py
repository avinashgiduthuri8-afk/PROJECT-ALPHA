import paramiko

hostname = "148.113.9.103"
port = 20069
username = "root"
password = "SMT6SiQU2nIUMj0V"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

print(f"Connecting to VPS {hostname}:{port}...")
client.connect(hostname, port=port, username=username, password=password, timeout=15)
print("Connected successfully!")


def run_ssh_cmd(cmd):
    print(f"\n--- Executing: {cmd} ---")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        print(f"[STDOUT]\n{out}")
    if err:
        print(f"[STDERR]\n{err}")
    return out, err


# Find project directory
out, _ = run_ssh_cmd(
    "find / -maxdepth 3 -name 'PROJECT-ALPHA' 2>/dev/null || find / -name 'PROJECT-ALPHA' 2>/dev/null"
)
project_dir = out.strip().split("\n")[0] if out.strip() else ""

if not project_dir:
    print("PROJECT-ALPHA directory not found immediately. Checking root dir...")
    out, _ = run_ssh_cmd("ls -la")
    project_dir = "/root/PROJECT-ALPHA"  # default guess

print(f"Target Project Directory: {project_dir}")

# Git Pull
run_ssh_cmd(f"cd {project_dir} && git status")
run_ssh_cmd(f"cd {project_dir} && git pull origin main")

# Check how it's running
out_docker, _ = run_ssh_cmd("docker ps")
out_pm2, _ = run_ssh_cmd("pm2 list")
out_ps, _ = run_ssh_cmd("ps aux | grep app.py | grep -v grep")

if "docker" in out_docker and "PROJECT-ALPHA" in out_docker or "compose" in out_docker:
    print("Detected Docker environment. Restarting docker-compose...")
    run_ssh_cmd(
        f"cd {project_dir} && docker-compose down && docker-compose up -d --build"
    )
elif "app.py" in out_pm2 or "alpha" in out_pm2:
    print("Detected PM2 environment. Restarting PM2...")
    run_ssh_cmd("pm2 restart all")
else:
    print("Restarting raw python app process...")
    run_ssh_cmd("pkill -f 'python app.py' || true")
    run_ssh_cmd(f"cd {project_dir} && nohup python3 app.py > app.log 2>&1 &")

print("\nDeployment execution completed!")
client.close()
