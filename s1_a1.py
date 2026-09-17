import paramiko

def run_ssh(ssh, cmd, label=""):
    if label: print(f"\n--- {label} ---")
    stdin, stdout, stderr = ssh.exec_command(f"cd /opt/project-alpha && {cmd}")
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if out: print(out)
    if err and 'warning' not in err.lower(): print("ERR:", err)
    return out

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

# A1.1 Count files needing update
run_ssh(ssh, 'find tests/ -name "test_*.py" -type f -exec grep -l "from core.config import V2Config" {} \\; | wc -l', "A1.1: Count files with V2Config import")
run_ssh(ssh, 'find tests/ -name "test_*.py" -type f -exec grep -l "from core.config import V2Config" {} \\;', "A1.1: List files")

# A1.2 Execute bulk rename
run_ssh(ssh, "find tests/ -name 'test_*.py' -type f -exec sed -i 's/from core.config import V2Config/from core.config import AppConfig/g' {} \\;", "A1.2: Bulk rename V2Config -> AppConfig imports")
run_ssh(ssh, "find tests/ -name 'test_*.py' -type f -exec sed -i 's/V2Config()/AppConfig()/g' {} \\;", "A1.2: Bulk rename V2Config() -> AppConfig() calls")

# A1.3 Verify
run_ssh(ssh, 'grep -r "from core.config import V2Config" tests/ 2>/dev/null || echo "No old imports found (good)"', "A1.3: Verify no old imports")
run_ssh(ssh, 'grep -r "from core.config import AppConfig" tests/ 2>/dev/null | wc -l', "A1.3: Count new imports")

# A1.4 Run a quick test to confirm no breakage
run_ssh(ssh, '.venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v 2>&1 | tail -20', "A1.4: Run indicator tests")

# A1.5 Commit
run_ssh(ssh, 'git add -A && git commit -m "Refactor: Update test imports from V2Config to AppConfig" && git log --oneline -1', "A1.5: Commit")

ssh.close()

