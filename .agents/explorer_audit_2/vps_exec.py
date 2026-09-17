import sys
import paramiko

def run_ssh_command(cmd):
    host = "148.113.9.103"
    port = 20069
    user = "root"
    password = "SMT6SiQU2nIUMj0V"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, port=port, username=user, password=password, timeout=15)
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        exit_code = stdout.channel.recv_exit_status()
        print(f"=== EXIT CODE: {exit_code} ===")
        if out:
            print("=== STDOUT ===")
            print(out)
        if err:
            print("=== STDERR ===")
            print(err)
        return exit_code, out, err
    finally:
        client.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = " ".join(sys.argv[1:])
    else:
        command = "uname -a"
    run_ssh_command(command)
