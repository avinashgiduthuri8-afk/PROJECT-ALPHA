import paramiko
import time

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.113.9.103", port=20069, username="root", password="SMT6SiQU2nIUMj0V")

    unit_content = """[Unit]
Description=PROJECT-ALPHA Trading Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/project-alpha
Environment=PATH=/opt/project-alpha/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=/opt/project-alpha/.venv/bin/python3 app.py
Restart=always
RestartSec=5
StandardOutput=append:/opt/project-alpha/output.log
StandardError=append:/opt/project-alpha/output.log

[Install]
WantedBy=multi-user.target
"""

    print("Stopping service and freeing port...")
    client.exec_command("systemctl stop project-alpha || true")
    client.exec_command("pkill -9 -f app.py || true")
    client.exec_command("fuser -k 5001/tcp || true")
    time.sleep(2)

    print("Writing new systemd service unit...")
    sftp = client.open_sftp()
    with sftp.open("/etc/systemd/system/project-alpha.service", "w") as f:
        f.write(unit_content)
    sftp.close()

    print("Reloading systemd daemon and starting service...")
    client.exec_command("systemctl daemon-reload")
    client.exec_command("systemctl start project-alpha")
    
    print("Waiting 12 seconds...")
    time.sleep(12)

    _, stdout, _ = client.exec_command("systemctl status project-alpha --no-pager")
    print("\n=== Status after 12s ===\n" + stdout.read().decode())

    _, stdout, _ = client.exec_command("curl -s http://127.0.0.1:5001/api/v2/health")
    print("=== Health API ===\n" + stdout.read().decode())

    _, stdout, _ = client.exec_command("curl -s -H 'X-API-Key: alpha-prod-key' http://127.0.0.1:5001/api/v2/portfolio/snapshot?mode=PAPER")
    print("\n=== PAPER Snapshot ===\n" + stdout.read().decode())

    client.close()

if __name__ == "__main__":
    main()
