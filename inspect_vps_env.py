import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("148.113.9.103", port=20069, username="root", password="SMT6SiQU2nIUMj0V", timeout=15)

def run_cmd(cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    print(f"--- {cmd} ---")
    print(stdout.read().decode('utf-8'))
    print(stderr.read().decode('utf-8'))

run_cmd("ls -la /root/PROJECT-ALPHA")
run_cmd("which python3; which pip; which virtualenv")
run_cmd("find /root/PROJECT-ALPHA -maxdepth 2 -name 'activate'")

client.close()

