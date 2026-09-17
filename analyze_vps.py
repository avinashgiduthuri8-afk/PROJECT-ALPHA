import sqlite3
import json
from datetime import datetime, timedelta, timezone

db_path = 'vps_alpha_v2.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("--- 1. Is Scanner Running? ---")
# Check the most recent event log entry
try:
    cursor.execute("SELECT logged_at, event_type FROM event_log ORDER BY logged_at DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"Latest event log: {row['logged_at']} ({row['event_type']})")
    
    cursor.execute("SELECT generated_at FROM signals ORDER BY generated_at DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"Latest signal generated at: {row['generated_at']}")
except Exception as e:
    print("Error checking logs/signals:", e)


print("\n--- 2. How many signals were generated in the last 24 hours? ---")
try:
    now = datetime.now(timezone.utc)
    yesterday_iso = (now - timedelta(hours=24)).isoformat()
    # Or just use the max timestamp in the db as reference if the DB is slightly out of sync
    cursor.execute("SELECT MAX(generated_at) as latest FROM signals")
    row = cursor.fetchone()
    latest_ts = row['latest']
    if latest_ts:
        # assume latest_ts is ISO string
        latest_dt = datetime.fromisoformat(latest_ts.replace('Z', '+00:00'))
        yesterday_dt = latest_dt - timedelta(hours=24)
        
        cursor.execute("SELECT COUNT(*) as count FROM signals WHERE generated_at >= ?", (yesterday_dt.isoformat(),))
        print(f"Signals in 24h before {latest_ts}: {cursor.fetchone()['count']}")
    else:
        print("No signals found.")
except Exception as e:
    print("Error:", e)


print("\n--- 3. How many current active signals exist? ---")
try:
    # We can check expires_at > latest_ts
    cursor.execute("SELECT COUNT(*) as count FROM signals WHERE expires_at > ?", (latest_ts,))
    print(f"Active signals (expires_at > latest signal time): {cursor.fetchone()['count']}")
except Exception as e:
    print("Error:", e)


print("\n--- 4. How many MTB signals exist specifically? ---")
try:
    cursor.execute("SELECT COUNT(*) as count FROM signals WHERE source_bot = 'MTB' OR raw_payload LIKE '%MTB%'")
    print(f"Total MTB signals: {cursor.fetchone()['count']}")
except Exception as e:
    print("Error:", e)


print("\n--- 5. Latest MTB signal ---")
try:
    cursor.execute("SELECT * FROM signals WHERE source_bot = 'MTB' OR raw_payload LIKE '%MTB%' ORDER BY generated_at DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        payload = json.loads(row['raw_payload'])
        print(f"Coin: {row['coin']}")
        print(f"Strategy: {payload.get('strategy', 'N/A')}")
        print(f"Action: {payload.get('opportunity_type', row['opportunity_type'])}")
        print(f"Score: {row['score']}")
        print(f"Timestamp: {row['generated_at']}")
        print(f"Entry: {payload.get('price', 'N/A')}")
    else:
        print("No MTB signals found.")
except Exception as e:
    print("Error:", e)


print("\n--- 6. Scanner condition/filter for MTB ---")
try:
    cursor.execute("SELECT payload FROM event_log WHERE payload LIKE '%funnel%' ORDER BY logged_at DESC LIMIT 5")
    rows = cursor.fetchall()
    for r in rows:
        payload_json = json.loads(r['payload'])
        if 'funnel' in payload_json:
            print("Funnel data:", json.dumps(payload_json['funnel'], indent=2))
            break
except Exception as e:
    print("Error:", e)

conn.close()

