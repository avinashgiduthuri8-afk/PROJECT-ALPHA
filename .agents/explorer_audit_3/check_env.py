import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('148.113.9.103', port=20069, username='root', password='SMT6SiQU2nIUMj0V', timeout=15)

    py_script = """
import sys
print("Python version:", sys.version)

try:
    import numpy as np
    print("NumPy version:", np.__version__)
except ImportError as e:
    print("NumPy missing:", e)

try:
    import pandas as pd
    print("Pandas version:", pd.__version__)
except ImportError as e:
    print("Pandas missing:", e)
"""
    stdin, stdout, stderr = ssh.exec_command("/opt/project-alpha/.venv/bin/python3")
    stdin.write(py_script)
    stdin.channel.shutdown_write()
    print("STDOUT:\n", stdout.read().decode('utf-8', errors='replace'))
    print("STDERR:\n", stderr.read().decode('utf-8', errors='replace'))
    ssh.close()

if __name__ == '__main__':
    main()
