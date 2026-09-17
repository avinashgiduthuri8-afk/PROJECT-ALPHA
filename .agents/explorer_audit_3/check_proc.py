import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    def run(cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        return stdout.read().decode('utf-8', errors='replace').strip()

    print("=== Check open files of process 71891 (app.py) ===")
    print(run('ls -l /proc/71891/fd 2>/dev/null | grep -E "project_alpha|\.db|\.log"'))

    print("\n=== Check systemd or supervisor services ===")
    print(run('systemctl list-units --type=service | grep -E "alpha|project"'))

    print("\n=== Check journalctl for project-alpha or app.py ===")
    print(run('journalctl -u project-alpha -n 30 --no-pager 2>/dev/null || true'))

    print("\n=== Check recent logs in /opt/project-alpha/logs or /var/log ===")
    print(run('ls -la /opt/project-alpha/logs 2>/dev/null || ls -la /opt/project-alpha/*.log 2>/dev/null'))

    print("\n=== Check environment variables of process 71891 ===")
    print(run('tr "\\0" "\\n" < /proc/71891/environ | grep -E "DB|DATABASE|SCANNER|MODE|BOT"'))

    ssh.close()

if __name__ == '__main__':
    main()
