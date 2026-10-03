import os
import tarfile
import paramiko
import time

def deploy():
    print("Creating release archive...")
    tar_path = "release.tar.gz"
    exclude_dirs = {".git", ".venv", ".pytest_cache", ".pytest_temp", ".test_dbs", "__pycache__"}
    exclude_files = {"release.tar.gz"}

    with tarfile.open(tar_path, "w:gz") as tar:
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.endswith(".egg-info")]
            for f in files:
                if f in exclude_files or f.endswith(".pyc") or f.endswith(".log"):
                    continue
                full_path = os.path.join(root, f)
                arcname = os.path.relpath(full_path, ".")
                tar.add(full_path, arcname=arcname)

    print(f"Archive created: {os.path.getsize(tar_path)} bytes")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.113.9.103", port=20069, username="root", password="SMT6SiQU2nIUMj0V")

    def run_remote(cmd, desc=""):
        if desc:
            print(f"\n=== {desc} ===")
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if out:
            print("STDOUT:\n" + out)
        if err:
            print("STDERR:\n" + err)
        return out, err

    # 1. Stop service
    run_remote("systemctl stop project-alpha || true", "Stop project-alpha service")

    # 2. Upload archive via SFTP
    print("Uploading release archive...")
    sftp = client.open_sftp()
    sftp.put(tar_path, "/tmp/release.tar.gz")
    sftp.close()
    print("Upload complete.")

    # 3. Extract to /opt/project-alpha
    run_remote("tar -xzf /tmp/release.tar.gz -C /opt/project-alpha/ && rm -f /tmp/release.tar.gz", "Extract archive")

    # 4. Enforce PAPER / Safe config_override.json
    override_json = (
        "{\\n"
        '  \\"deployment_mode\\\": \\\"PAPER\\\",\\n'
        '  \\"trading_enabled\\\": false,\\n'
        '  \\"shadow_mode\\\": true\\n'
        "}"
    )
    run_remote(f'printf "{override_json}" > /opt/project-alpha/data/config_override.json', "Write safe config_override.json")
    run_remote("cat /opt/project-alpha/data/config_override.json", "Verify config_override.json")

    # 5. Fix venv symlinks & permissions
    run_remote("ln -sf /usr/bin/python3 /opt/project-alpha/.venv/bin/python3 && ln -sf /usr/bin/python3 /opt/project-alpha/.venv/bin/python && chmod +x /opt/project-alpha/.venv/bin/* || true", "Fix venv")
    run_remote("fuser -k 5001/tcp || true", "Free port 5001")

    # 6. Restart service
    run_remote("systemctl restart project-alpha", "Restart project-alpha service")
    time.sleep(6)

    # 7. Verify service and health
    run_remote("systemctl status project-alpha --no-pager", "Systemctl status")
    run_remote("curl -s http://127.0.0.1:5001/api/v2/health", "API Health check")
    run_remote("tail -n 30 /opt/project-alpha/output.log", "Recent output log")

    client.close()
    if os.path.exists(tar_path):
        os.remove(tar_path)
    print("\nDeployment completed successfully.")

if __name__ == "__main__":
    deploy()
