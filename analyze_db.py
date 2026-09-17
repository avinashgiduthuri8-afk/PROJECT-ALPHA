import sqlite3
import json
from datetime import datetime, timedelta, timezone

db_path = 'vps_alpha_v2.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("1. Is Scanner running?")
try:
    cursor.execute("SELECT logged_at FROM event_log WHERE event_type LIKE '%SCAN%' OR source_service LIKE '%scanner%' ORDER BY logged_at DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"Yes. Latest scanner event: {row['logged_at']}")
    else:
        print("No recent scanner events found.")
except Exception as e:
    print(e)

print("\n2. How many signals were generated in the last 24 hours?")
try:
    cursor.execute("SELECT MAX(generated_at) FROM signals")
    max_ts = cursor.fetchone()[0]
    if max_ts:
        dt = datetime.fromisoformat(max_ts.replace('Z', '+00:00'))
        dt_24h_ago = dt - timedelta(hours=24)
        cursor.execute("SELECT COUNT(*) FROM signals WHERE generated_at >= ?", (dt_24h_ago.isoformat(),))
        print(cursor.fetchone()[0])
    else:
        print("0")
except Exception as e:
    print(e)


print("\n3. How many current active signals exist?")
try:
    if max_ts:
        cursor.execute("SELECT COUNT(*) FROM signals WHERE expires_at > ?", (max_ts,))
        print(cursor.fetchone()[0])
    else:
        print("0")
except Exception as e:
    print(e)

print("\n4. How many MTB signals exist specifically?")
try:
    cursor.execute("SELECT COUNT(*) FROM signals WHERE raw_payload LIKE '%MTB%' OR source_bot = 'MTB'")
    print(cursor.fetchone()[0])
except Exception as e:
    print(e)

print("\n5. For the latest MTB signal, show details:")
try:
    cursor.execute("SELECT * FROM signals WHERE raw_payload LIKE '%MTB%' OR source_bot = 'MTB' ORDER BY generated_at DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        payload = json.loads(row['raw_payload'])
        print(f"Coin: {row['coin']}")
        print(f"Strategy: {payload.get('strategy', 'MTB')}")
        print(f"Action: {payload.get('opportunity_type', row['opportunity_type'])}")
        print(f"Score: {row['score']}")
        print(f"Timestamp: {row['generated_at']}")
        print(f"Entry: {payload.get('price', 'N/A')}")
    else:
        print("No MTB signals found.")
except Exception as e:
    print(e)

print("\n6. If there are zero MTB signals, identify which scanner condition/filter is preventing them:")
try:
    cursor.execute("SELECT payload_json FROM event_log WHERE payload_json LIKE '%MTB%' ORDER BY logged_at DESC LIMIT 5")
    rows = cursor.fetchall()
    for r in rows:
        print(json.dumps(json.loads(r['payload_json']), indent=2))
        
    if not rows:
        print("No MTB mentions in event_log.")
        
    cursor.execute("SELECT payload_json FROM event_log WHERE event_type LIKE '%REJECT%' OR payload_json LIKE '%reject%' ORDER BY logged_at DESC LIMIT 2")
    rows = cursor.fetchall()
    for r in rows:
        print(json.dumps(json.loads(r['payload_json']), indent=2))

except Exception as e:
    print(e)
