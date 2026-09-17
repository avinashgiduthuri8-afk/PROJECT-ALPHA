import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && git push origin main 2>&1")
out = stdout.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii')
err = stderr.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii')
if out: print(out)
if err: print(err)

stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && git log --oneline -1")
print("HEAD:", stdout.read().decode('utf-8').strip())

ssh.close()

