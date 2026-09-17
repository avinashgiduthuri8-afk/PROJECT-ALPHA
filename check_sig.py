import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')
stdin, stdout, stderr = ssh.exec_command('sqlite3 /opt/project-alpha/data/project_alpha.db "SELECT COUNT(*) as recent_signals FROM signals WHERE generated_at > datetime(\'now\', \'-5 minute\');"')
print('Recent signals:', stdout.read().decode('utf-8').strip())
stdin, stdout, stderr = ssh.exec_command('journalctl -u project-alpha-v2.service -n 100 --no-pager | grep -E "raw_universe|Scanner Funnel"')
print('Log:', stdout.read().decode('utf-8').strip())
ssh.close()

