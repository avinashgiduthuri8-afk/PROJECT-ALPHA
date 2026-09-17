import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    def run(cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='replace').strip()
        err = stderr.read().decode('utf-8', errors='replace').strip()
        return out, err

    print("=== Find project_alpha.db ===")
    out, err = run('find / -name "project_alpha.db" 2>/dev/null')
    print(out)

    print("\n=== Running processes (python) ===")
    out, err = run('ps aux | grep python')
    print(out)

    print("\n=== Directory listing /root /opt ===")
    out, err = run('ls -la /root /opt 2>/dev/null')
    print(out)

    ssh.close()

if __name__ == '__main__':
    main()
