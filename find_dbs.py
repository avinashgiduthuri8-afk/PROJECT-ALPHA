import paramiko

host = '148.113.9.103'
port = 20069
username = 'root'
password = 'SMT6SiQU2nIUMj0V'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, port, username, password)
stdin, stdout, stderr = ssh.exec_command('find / -name "*.db" -size +1M -exec ls -lh {} + 2>/dev/null')
print(stdout.read().decode('utf-8'))
ssh.close()
