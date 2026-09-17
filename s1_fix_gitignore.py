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

# Fix: Remove .venv, backups, large db files from git tracking
run_ssh(ssh, 'git rm -r --cached .venv/ 2>/dev/null; git rm -r --cached backups/ 2>/dev/null; git rm --cached project_alpha_v2.db 2>/dev/null; git rm --cached _debug_inspect.py 2>/dev/null; git rm --cached scratch_check_tg.py 2>/dev/null; echo "done removing cached files"', "Fix: Remove accidentally tracked files")

# Add proper .gitignore entries
run_ssh(ssh, """cat >> .gitignore << 'GITEOF'
.venv/
backups/
*.db
*.db-shm
*.db-wal
_debug_inspect.py
scratch_*.py
__pycache__/
*.pyc
GITEOF
echo "gitignore updated"
""", "Fix: Update .gitignore")

run_ssh(ssh, 'git add .gitignore && git add -A && git commit -m "Fix: Add .gitignore, remove accidentally tracked .venv and backups" && git log --oneline -1', "Fix: Commit gitignore fix")

ssh.close()

