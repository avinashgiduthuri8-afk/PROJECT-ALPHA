import paramiko

def run_ssh(ssh, cmd, label=""):
    if label: print(f"\n--- {label} ---")
    stdin, stdout, stderr = ssh.exec_command(f"cd /opt/project-alpha && {cmd}")
    out = stdout.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii')
    err = stderr.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii')
    if out: print(out)
    if err and 'warning' not in err.lower() and 'committer' not in err.lower(): print("ERR:", err)
    return out

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

run_ssh(ssh, 'grep -r "from v2\\|import v2" --include="*.py" . | grep -v __pycache__ | grep -v ".pyc" | head -5 || echo "None found"', "D1: v2 imports")
run_ssh(ssh, 'ls tests/test_v2_*.py 2>/dev/null || echo "All renamed"', "D1: test_v2_ files")
run_ssh(ssh, '.venv/bin/python3 -c "from core.config import AppConfig; from core.bus.event_bus import EventBus; print(\'Core imports successful\')"', "D1: Core imports")
run_ssh(ssh, 'git log --oneline | head -12', "D2: All commits")

ssh.close()

