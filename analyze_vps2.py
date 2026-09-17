import sqlite3
import json
from datetime import datetime, timedelta, timezone

db_path = 'vps_alpha_v2.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

cursor = conn.cursor()

print("--- TABLES ---")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
for t in tables:
    print(t['name'])

print("\n--- Event Log Schema ---")
cursor.execute("PRAGMA table_info(event_log)")
for r in cursor.fetchall():
    print(dict(r))

print("\n--- Signals Schema ---")
cursor.execute("PRAGMA table_info(signals)")
for r in cursor.fetchall():
    print(dict(r))

print("\n--- 1. Is Scanner Running? ---")
try:
    cursor.execute("SELECT logged_at, event_type, payload_json FROM event_log ORDER BY logged_at DESC LIMIT 10")
    for r in cursor.fetchall():
        print(f"{r['logged_at']} | {r['event_type']} | {r['payload_json']}")
except Exception as e:
    print("Error:", e)
    
print("\n--- Total signals ---")
cursor.execute("SELECT COUNT(*) FROM signals")
print(cursor.fetchone()[0])
