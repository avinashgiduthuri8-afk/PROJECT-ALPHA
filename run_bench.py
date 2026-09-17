import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && .venv/bin/python3 scripts/benchmark_paper_mode.py")
output = stdout.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii')
err = stderr.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii')

if output: print(output)
if err: print("ERR:", err)

ssh.close()
