import paramiko
import json
import hashlib
import os

VPS_HOST = "148.113.9.103"
VPS_PORT = 20069
VPS_USER = "root"
VPS_PASS = "SMT6SiQU2nIUMj0V"

def run_ssh_command(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    exit_code = stdout.channel.recv_exit_status()
    return {"cmd": cmd, "exit_code": exit_code, "stdout": out, "stderr": err}

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS, timeout=15)

    results = {}

    # 1. Git status on /opt/project-alpha and /root/PROJECT-ALPHA
    results["git_status_opt"] = run_ssh_command(ssh, "cd /opt/project-alpha && git status --porcelain=v1 && git status")
    results["git_diff_opt"] = run_ssh_command(ssh, "cd /opt/project-alpha && git diff")
    results["git_log_opt"] = run_ssh_command(ssh, "cd /opt/project-alpha && git log -1 --format='%H %s (%cd)'")

    results["git_status_root"] = run_ssh_command(ssh, "cd /root/PROJECT-ALPHA && git status --porcelain=v1 && git status")
    results["git_diff_root"] = run_ssh_command(ssh, "cd /root/PROJECT-ALPHA && git diff")
    results["git_log_root"] = run_ssh_command(ssh, "cd /root/PROJECT-ALPHA && git log -1 --format='%H %s (%cd)'")

    # 2. Check indicators file existence, line counts, and hashes
    results["file_check_opt"] = run_ssh_command(ssh, "test -f /opt/project-alpha/scanner/indicators.py && echo EXISTS || echo NOT_FOUND")
    results["file_check_root"] = run_ssh_command(ssh, "test -f /root/PROJECT-ALPHA/scanner/indicators.py && echo EXISTS || echo NOT_FOUND")
    results["wc_opt"] = run_ssh_command(ssh, "wc -l /opt/project-alpha/scanner/research/indicators.py")
    results["wc_root"] = run_ssh_command(ssh, "wc -l /root/PROJECT-ALPHA/scanner/research/indicators.py")
    results["sha_opt"] = run_ssh_command(ssh, "sha256sum /opt/project-alpha/scanner/research/indicators.py")
    results["sha_root"] = run_ssh_command(ssh, "sha256sum /root/PROJECT-ALPHA/scanner/research/indicators.py")

    # 3. Systemd service status & running process
    results["systemd_status"] = run_ssh_command(ssh, "systemctl status project-alpha-v2.service --no-pager")
    results["ps_check"] = run_ssh_command(ssh, "ps aux | grep -E 'python3.*app.py' | grep -v grep")

    # 4. Indicator test executions
    # A. Using .venv/bin/python3 -m pytest
    results["pytest_module_opt"] = run_ssh_command(ssh, "cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_indicator_calculations.py -v")
    # B. Using .venv/bin/pytest directly (verify explorer 2 finding)
    results["pytest_direct_opt"] = run_ssh_command(ssh, "cd /opt/project-alpha && .venv/bin/pytest tests/test_indicator_calculations.py -v")
    # C. Research indicators subset in test_v2_coin_research.py
    results["pytest_research_subset"] = run_ssh_command(ssh, "cd /opt/project-alpha && .venv/bin/python3 -m pytest tests/test_v2_coin_research.py -k 'computation or bands or atr' -v")

    ssh.close()

    with open(r"c:\Users\ASUS\Documents\GitHub\PROJECT-ALPHA\.agents\auditor_audit_1\vps_check_1.json", "w") as f:
        json.dump(results, f, indent=2)

    print("Audit check 1 completed successfully.")

if __name__ == "__main__":
    main()
