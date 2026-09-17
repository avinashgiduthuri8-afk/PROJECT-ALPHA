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

# ═══════════════════════════════════════════════════════════
# Phase D1: Full Repository Audit
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'echo "=== Python files with v2 imports ===" && grep -r "from v2\\|import v2" --include="*.py" . | grep -v __pycache__ | grep -v ".pyc" || echo "None found"', "D1: Check v2 imports")

run_ssh(ssh, 'echo "=== V2_* env vars still in active code ===" && grep -r "V2_" --include="*.py" core/ scanner/ execution/ telegram/ dashboard/ background/ | grep -v "LEGACY_FIELD_MAP" | grep -v "v2_" | head -10 || echo "Only in legacy map (ok)"', "D1: Check V2_ env vars")

run_ssh(ssh, 'echo "=== Remaining CSS v2 classes ===" && grep -rn "\\.v2-" dashboard/ 2>/dev/null || echo "None found"', "D1: Check CSS classes")

run_ssh(ssh, 'echo "=== Remaining test_v2_ file names ===" && ls tests/test_v2_*.py 2>/dev/null || echo "All renamed"', "D1: Check test filenames")

# D1.2 Run tests
run_ssh(ssh, '.venv/bin/python3 -m pytest tests/test_indicator_calculations.py tests/test_scanner_funnel.py -v 2>&1 | tail -30', "D1.2: Run indicator & scanner tests")

# D1.3 Verify app starts
run_ssh(ssh, '.venv/bin/python3 -c "from core.config import AppConfig; from core.bus.event_bus import EventBus; print(\'Core imports successful\')"', "D1.3: Verify core imports")

# ═══════════════════════════════════════════════════════════
# Phase D2: Final Summary
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'git log --oneline | head -12', "D2: All commits")

ssh.close()
print("\n=== Phase D Complete ===")

