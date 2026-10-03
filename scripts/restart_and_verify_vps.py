import paramiko
import time

def restart_and_verify():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("148.113.9.103", port=20069, username="root", password="SMT6SiQU2nIUMj0V")

    print("Stopping project-alpha service and killing all orphan python processes...")
    client.exec_command("systemctl stop project-alpha || true")
    client.exec_command("pkill -9 -f app.py || true")
    client.exec_command("pkill -9 -f /opt/project-alpha/.venv/bin/python3 || true")
    client.exec_command("fuser -k 5001/tcp || true")
    time.sleep(3)

    print("Enabling and starting project-alpha service...")
    client.exec_command("systemctl daemon-reload")
    client.exec_command("systemctl enable project-alpha")
    client.exec_command("systemctl start project-alpha")
    
    print("Waiting 15 seconds for startup...")
    time.sleep(15)

    _, stdout, _ = client.exec_command("systemctl status project-alpha --no-pager")
    print("\n=== Systemctl Status (T+15s) ===\n" + stdout.read().decode())

    print("Waiting another 15 seconds to ensure continuous operation...")
    time.sleep(15)

    _, stdout, _ = client.exec_command("systemctl status project-alpha --no-pager")
    print("\n=== Systemctl Status (T+30s) ===\n" + stdout.read().decode())

    _, stdout, _ = client.exec_command("curl -s http://127.0.0.1:5001/api/v2/health")
    print("=== Health API ===\n" + stdout.read().decode())

    _, stdout, _ = client.exec_command("curl -s -H 'X-API-Key: alpha-prod-key' http://127.0.0.1:5001/api/v2/portfolio/snapshot?mode=PAPER")
    print("\n=== PAPER Snapshot ===\n" + stdout.read().decode())

    _, stdout, _ = client.exec_command("curl -s -H 'X-API-Key: alpha-prod-key' http://127.0.0.1:5001/api/trading/positions?status=OPEN")
    print("\n=== Open Positions ===\n" + stdout.read().decode())

    client.close()

if __name__ == "__main__":
    restart_and_verify()
