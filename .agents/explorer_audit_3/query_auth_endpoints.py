import paramiko
import json

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = r"""
import urllib.request
import json

headers = {
    'User-Agent': 'Audit/1.0',
    'X-API-Key': 'alpha-prod-key'
}

endpoints = [
    'http://127.0.0.1:5001/api/v2/dashboard/overview',
    'http://127.0.0.1:5001/api/v2/scanner/coins',
    'http://127.0.0.1:5001/api/v2/scanner/watchlist',
    'http://127.0.0.1:5001/api/v2/scanner/signals',
    'http://127.0.0.1:5001/api/v2/production/status'
]

for ep in endpoints:
    try:
        req = urllib.request.Request(ep, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode('utf-8')
            parsed = json.loads(data)
            print(f"=== {ep} (Status: {resp.status}) ===")
            if isinstance(parsed, list):
                print(f"List count: {len(parsed)}")
                if parsed:
                    print("Sample item keys:", list(parsed[0].keys()) if isinstance(parsed[0], dict) else parsed[0])
                    print("Sample item:", json.dumps(parsed[0], indent=2)[:350])
            elif isinstance(parsed, dict):
                print("Dict keys:", list(parsed.keys()))
                print("Sample:", json.dumps(parsed, indent=2)[:350])
    except Exception as e:
        print(f"=== {ep} ERROR: {e} ===")
"""
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_script)
    stdin.channel.shutdown_write()
    print("STDOUT:\n", stdout.read().decode('utf-8', errors='replace'))
    print("STDERR:\n", stderr.read().decode('utf-8', errors='replace'))
    ssh.close()

if __name__ == '__main__':
    main()
