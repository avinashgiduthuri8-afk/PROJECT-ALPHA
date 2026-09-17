import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=30)

cmd = """
curl -s -H "X-API-Key: alpha-prod-key" http://127.0.0.1:5001/api/v2/production/status
echo ""
curl -s -H "X-API-Key: alpha-prod-key" http://127.0.0.1:5001/api/v2/dashboard/overview
"""
stdin, stdout, stderr = ssh.exec_command(cmd)
data = stdout.read().decode('utf-8', errors='replace')
with open("c:/Users/ASUS/Documents/GitHub/PROJECT-ALPHA/.agents/challenger_audit_2/endpoints_output.txt", "w", encoding="utf-8") as f:
    f.write(data)
print("Saved endpoints_output.txt successfully, length:", len(data))
ssh.close()
