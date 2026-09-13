import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("148.113.9.103", port=20069, username="root", password="SMT6SiQU2nIUMj0V", timeout=15)

stdin, stdout, stderr = client.exec_command("ps aux | grep app.py | grep -v grep")
print("Process Status:")
print(stdout.read().decode('utf-8'))

stdin, stdout, stderr = client.exec_command("tail -n 25 /root/PROJECT-ALPHA/app.log")
print("App Logs (tail -n 25):")
print(stdout.read().decode('utf-8'))

client.close()

