import paramiko
import os

host = '148.113.9.103'
port = 20069
username = 'root'
password = 'SMT6SiQU2nIUMj0V'

remote_db = '/opt/project-alpha/v2/data/alpha_v2.db'
local_db = 'vps_alpha_v2.db'

print("Connecting to VPS...")
transport = paramiko.Transport((host, port))
transport.connect(username=username, password=password)
sftp = paramiko.SFTPClient.from_transport(transport)

print(f"Downloading {remote_db} to {local_db}...")
try:
    sftp.get(remote_db, local_db)
    print("Download complete.")
except Exception as e:
    print("Error:", e)
finally:
    sftp.close()
    transport.close()
