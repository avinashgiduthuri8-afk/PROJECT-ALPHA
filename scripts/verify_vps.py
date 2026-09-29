import paramiko
import json

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V')

def run(cmd, desc):
    print(f"\n==================== {desc} ====================")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print("STDOUT:\n" + out)
    if err:
        print("STDERR:\n" + err)
    return out, err

run("systemctl status project-alpha --no-pager", "Systemctl Status")
run("curl -s -H 'X-API-Key: alpha-prod-key' http://127.0.0.1:5001/api/v2/portfolio/snapshot?mode=PAPER", "PAPER Portfolio Snapshot")
run("curl -s -H 'X-API-Key: alpha-prod-key' http://127.0.0.1:5001/api/v2/portfolio/snapshot?mode=LIVE", "LIVE Portfolio Snapshot")
run("curl -s -H 'X-API-Key: alpha-prod-key' http://127.0.0.1:5001/api/trading/positions?status=OPEN", "API Trading Positions (PAPER)")
run("curl -s -H 'X-API-Key: alpha-prod-key' 'http://127.0.0.1:5001/api/trading/positions?status=OPEN&mode=LIVE'", "API Trading Positions (LIVE)")
run("curl -s http://127.0.0.1:5001/api/v2/health", "API Health")

client.close()
