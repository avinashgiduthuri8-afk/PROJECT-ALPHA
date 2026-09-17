import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

# Check the common ancestor - the last commit we both share is 3b4c616
stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && git log --oneline 3b4c616..HEAD")
out = stdout.read().decode('utf-8').strip()
print("Commits to transfer:")
print(out)

# Create bundle from the common ancestor
stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && git bundle create /tmp/s1_naming.bundle 3b4c616..HEAD 2>&1")
print(stdout.read().decode('utf-8').strip())
print(stderr.read().decode('utf-8').strip())

# Verify bundle exists
stdin, stdout, stderr = ssh.exec_command("ls -lh /tmp/s1_naming.bundle")
print(stdout.read().decode('utf-8').strip())

# Download the bundle
sftp = ssh.open_sftp()
sftp.get('/tmp/s1_naming.bundle', 'C:/Users/ASUS/Documents/GitHub/PROJECT-ALPHA/s1_naming.bundle')
sftp.close()
print("Bundle downloaded successfully")

ssh.close()

