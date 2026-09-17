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
        print(out.strip())
    if err:
        print("STDERR:", err.strip())

# Step 1: Backup databases
backup_dir = "/opt/project-alpha/backups"
run_cmd(f"mkdir -p {backup_dir}")
timestamp = time.strftime("%Y%m%d_%H%M%S")

run_cmd(f"cp /opt/project-alpha/v2/data/alpha_v2.db {backup_dir}/alpha_v2.db.bak.{timestamp}")
run_cmd(f"ls -lh {backup_dir}/alpha_v2.db.bak.{timestamp}")

# Also check for data/project_alpha.db and back it up if it exists
run_cmd(f"if [ -f /opt/project-alpha/data/project_alpha.db ]; then cp /opt/project-alpha/data/project_alpha.db {backup_dir}/project_alpha.db.bak.{timestamp}; ls -lh {backup_dir}/project_alpha.db.bak.{timestamp}; else echo 'data/project_alpha.db does not exist'; fi")

# Step 2: Confirm Phase B fix is checked out
# Let's search the git log for the fix, or just see the current commit hash and if `scanner/market/public_client.py` or similar contains the fix.
run_cmd("cd /opt/project-alpha && git log -n 10 --oneline")
# Find the exact commit that mentions Phase B or CoinDCX market-universe parser
run_cmd("cd /opt/project-alpha && git log --grep='Phase B' --oneline")
# Let's also check the actual code file for the fix (e.g. BTCINR, USDT parsing)
run_cmd("cd /opt/project-alpha && cat scanner/market/feeder.py | grep -i -C 3 'BTCINR'")

# Step 3: Check data existence
# As established, if project_alpha.db doesn't exist, we don't even need to query it. But let's check its size if it exists.
run_cmd("ls -lh /opt/project-alpha/data/project_alpha.db 2>/dev/null || echo 'Canonical DB missing'")
run_cmd("ls -lh /opt/project-alpha/v2/data/alpha_v2.db 2>/dev/null")

ssh.close()

