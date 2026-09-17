import paramiko
import sys

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)
    except Exception as e:
        print(f"SSH connection failed: {e}")
        sys.exit(1)

    cmd = """python3 -c "
import os, glob

print('=== Searching for indicator files in /opt/project-alpha ===')
matches = glob.glob('/opt/project-alpha/**/indicator*.py', recursive=True)
for m in matches:
    print(m)

print('\\n=== Inspecting /opt/project-alpha/scanner/research/indicators.py ===')
with open('/opt/project-alpha/scanner/research/indicators.py') as f:
    lines = f.readlines()
print(f'Total lines: {len(lines)}')
for i, line in enumerate(lines):
    if line.startswith('def '):
        print(f'Line {i+1}: {line.strip()}')

print('\\n=== Searching for EMA/RSI/MACD in scanner/market_context.py ===')
if os.path.exists('/opt/project-alpha/scanner/market_context.py'):
    with open('/opt/project-alpha/scanner/market_context.py') as f:
        for i, line in enumerate(f):
            if 'def calculate_' in line or 'def compute_' in line or 'def get_' in line:
                print(f'Line {i+1}: {line.strip()}')
" """
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print("STDOUT:\n", out)
    if err:
        print("STDERR:\n", err)
    client.close()

if __name__ == '__main__':
    main()
