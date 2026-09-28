import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V')

def run(cmd):
    print(f"\n$ {cmd}")
    _, out, err = client.exec_command(cmd)
    o = out.read().decode().strip()
    e = err.read().decode().strip()
    if o: print(o)
    if e: print("ERR:", e)

run("ss -tulpn | grep 5001")
run("fuser -k 5001/tcp || true")
run("pkill -9 -f 'python3 app.py' || true")
run("sleep 2")
run("systemctl restart project-alpha")
run("sleep 3")
run("systemctl status project-alpha --no-pager")
run("journalctl -u project-alpha -n 25 --no-pager")

client.close()
