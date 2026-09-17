import paramiko

script = """
import sqlite3
import json

def print_query(cur, title, q):
    print(f"\\n--- {title} ---")
    try:
        cur.execute(q)
        rows = cur.fetchall()
        if not rows:
            print("No results found.")
        for r in rows:
            print(r)
    except Exception as e:
        print("ERR:", e)

conn = sqlite3.connect('/opt/project-alpha/data/project_alpha.db')
cur = conn.cursor()

print_query(cur, "Task 1: Latest Signal", "SELECT id, coin, opportunity_type, score, generated_at, priority, raw_payload FROM signals ORDER BY generated_at DESC LIMIT 1")

print_query(cur, "Task 2: AI Analyses Counts", "SELECT COUNT(*) as total_ai_analyses, COUNT(CASE WHEN recommendation = 'CONFIRM' THEN 1 END) as confirmed, COUNT(CASE WHEN recommendation = 'REJECT' THEN 1 END) as rejected, COUNT(CASE WHEN recommendation IS NULL THEN 1 END) as pending FROM ai_analyses;")
print_query(cur, "Task 2: Recent AI Analyses", "SELECT signal_id, coin, recommendation, confidence_score, risk_reward_assessment, analyzed_at FROM ai_analyses ORDER BY analyzed_at DESC LIMIT 3;")

# Since decision_divergences tracks v1 vs v2, we'll just show the divergences recorded
print_query(cur, "Task 2: Risk / Divergence Checks", "SELECT COUNT(*) as total_checks, COUNT(CASE WHEN divergence_type != 'NONE' THEN 1 END) as diverged, COUNT(CASE WHEN divergence_type = 'NONE' THEN 1 END) as matched FROM decision_divergences;")
print_query(cur, "Task 2: Recent Divergences", "SELECT signal_id, coin, divergence_type, reason, detected_at FROM decision_divergences ORDER BY detected_at DESC LIMIT 5;")

print_query(cur, "Task 3: Orders Counts", "SELECT COUNT(*) as total_orders, COUNT(CASE WHEN state = 'FILLED' THEN 1 END) as filled, COUNT(CASE WHEN state = 'PENDING_ENTRY' OR state = 'CREATED' THEN 1 END) as pending, COUNT(CASE WHEN state = 'REJECTED' OR state = 'CANCELLED' THEN 1 END) as rejected FROM orders;")
print_query(cur, "Task 3: Recent Orders", "SELECT id, coin, side, price, req_qty, state, created_at FROM orders ORDER BY created_at DESC LIMIT 10;")

print_query(cur, "Task 3: Open Positions", "SELECT COUNT(*) as open_positions, SUM(qty) as total_quantity, AVG(entry_price) as avg_entry_price, COUNT(CASE WHEN unrealised_pnl > 0 THEN 1 END) as winning_positions, COUNT(CASE WHEN unrealised_pnl < 0 THEN 1 END) as losing_positions FROM positions WHERE status = 'OPEN';")
print_query(cur, "Task 3: Recent Open Positions", "SELECT id, coin, entry_price, qty, unrealised_pnl, status, entry_time FROM positions WHERE status = 'OPEN' ORDER BY entry_time DESC LIMIT 5;")

print_query(cur, "Task 3: Closed Positions Counts", "SELECT COUNT(*) as closed_positions, COUNT(CASE WHEN exit_price > entry_price THEN 1 END) as profitable_closes, COUNT(CASE WHEN exit_price < entry_price THEN 1 END) as loss_closes FROM positions WHERE status = 'CLOSED';")
print_query(cur, "Task 3: Recent Closed Positions", "SELECT id, coin, entry_price, exit_price, qty, status, closed_at FROM positions WHERE status = 'CLOSED' ORDER BY closed_at DESC LIMIT 5;")

print_query(cur, "Task 3: Portfolio State", "SELECT SUM(CASE WHEN status = 'OPEN' THEN unrealised_pnl ELSE 0 END) as unrealized_pnl, COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open_count, COUNT(CASE WHEN status = 'CLOSED' THEN 1 END) as closed_count FROM positions;")
print_query(cur, "Task 3: Metrics/Statistics", "SELECT coin, COUNT(*) as trades, SUM(CASE WHEN exit_price > entry_price THEN 1 END) as wins, ROUND(SUM(CASE WHEN exit_price > entry_price THEN 1 END) * 100.0 / COUNT(*), 1) as win_rate FROM positions WHERE status = 'CLOSED' GROUP BY coin ORDER BY trades DESC LIMIT 10;")

print_query(cur, "Task 4: Flow Counts", "SELECT (SELECT COUNT(*) FROM signals) as signals, (SELECT COUNT(*) FROM ai_analyses) as ai, (SELECT COUNT(*) FROM decision_divergences) as risk, (SELECT COUNT(*) FROM orders) as orders, (SELECT COUNT(*) FROM positions) as positions")
conn.close()
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

sftp = ssh.open_sftp()
with sftp.file('/tmp/task234.py', 'w') as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command("cd /opt/project-alpha && .venv/bin/python3 /tmp/task234.py")
print(stdout.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii'))
print(stderr.read().decode('utf-8', errors='replace').strip().encode('ascii', 'replace').decode('ascii'))

ssh.close()

