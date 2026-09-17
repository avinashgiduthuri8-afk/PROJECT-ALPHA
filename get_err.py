import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')
stdin, stdout, stderr = ssh.exec_command('journalctl -u project-alpha-v2.service -n 50')
with open('vps_error.log', 'wb') as f:
    f.write(stdout.read())
ssh.close()

