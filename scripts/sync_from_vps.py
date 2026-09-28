import os
import sys
import paramiko

VPS_HOST = "148.113.9.103"
VPS_PORT = 20069
VPS_USER = "root"
VPS_PASS = "SMT6SiQU2nIUMj0V"
REMOTE_DB_PATH = "/opt/project-alpha/v2/data/alpha_v2.db"
LOCAL_DB_PATH = os.path.join("data", "project_alpha.db")
LOCAL_DB_COPY = os.path.join("data", "alpha_v2.db")

def sync_db_from_vps():
    print(f"Connecting to VPS {VPS_HOST}:{VPS_PORT}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS)

    sftp = ssh.open_sftp()
    print(f"Downloading {REMOTE_DB_PATH} from VPS...")
    os.makedirs("data", exist_ok=True)
    
    # Save to local database paths
    sftp.get(REMOTE_DB_PATH, LOCAL_DB_PATH)
    sftp.get(REMOTE_DB_PATH, LOCAL_DB_COPY)
    print(f"[OK] Successfully synced database from VPS to local:\n  - {LOCAL_DB_PATH}\n  - {LOCAL_DB_COPY}")

    sftp.close()
    ssh.close()

if __name__ == "__main__":
    sync_db_from_vps()
