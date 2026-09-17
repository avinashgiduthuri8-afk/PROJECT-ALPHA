import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')
stdin, stdout, stderr = ssh.exec_command('journalctl -u project-alpha-v2.service -n 5000 | grep -E -i "error|exception|fail|coindcx" | tail -n 50')
print(stdout.read().decode('utf-8'))
ssh.close()

