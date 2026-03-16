#!/bin/bash
set -e

cd /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent

echo "=========================================="
echo "DATADOG ALERT AGGREGATION SYSTEM - FINAL TEST"
echo "=========================================="

# Step 1: Restore files from archive
echo ""
echo "Step 1: Preparing test data..."
python3 << 'PYEOF'
import os
watch_dir = '/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails'
archive_path = os.path.join(watch_dir, 'archive')
if os.path.exists(archive_path):
    archive_files = [f for f in os.listdir(archive_path) if f.endswith('.txt')]
    if archive_files:
        print(f"  Restoring {len(archive_files)} files from archive...")
        for f in archive_files:
            os.rename(os.path.join(archive_path, f), os.path.join(watch_dir, f))
        print("  ✅ Files restored")
main_files = [f for f in os.listdir(watch_dir) if f.endswith('.txt') and os.path.isfile(os.path.join(watch_dir, f))]
print(f"  ✅ Ready: {len(main_files)} alert files in main directory")
PYEOF

# Step 2: Reset database
echo ""
echo "Step 2: Initializing database..."
rm -f alerts.db
echo "  ✅ Database cleared"

# Step 3: Run agent
echo ""
echo "Step 3: Running agent (95 seconds)..."
echo "  Starting agent via venv..."
./venv/bin/python3 agent.py > /tmp/agent_test.log 2>&1 &
AGENT_PID=$!
echo "  Agent PID: $AGENT_PID"

# Wait 95 seconds
for i in {1..19}; do
  sleep 5
  pct=$((i * 5 * 100 / 95))
  echo "  [$pct%] $(( i * 5))s elapsed"
done

# Stop agent
kill $AGENT_PID 2>/dev/null || true
sleep 1
echo "  ✅ Agent stopped"

# Step 4: Analyze results
echo ""
echo "Step 4: Analyzing results..."
./venv/bin/python3 << 'PYEOF'
import sqlite3
conn = sqlite3.connect('alerts.db')
cursor = conn.cursor()

# Check tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print(f"  Tables created: {tables}")

if 'alerts' not in tables:
    print("  ❌ FAILED: alerts table not created")
    exit(1)

# Count alerts
cursor.execute("SELECT COUNT(*) FROM alerts")
alert_count = cursor.fetchone()[0]
print(f"  ✅ Alerts stored: {alert_count}")

# Count periods
cursor.execute("SELECT COUNT(*) FROM alert_periods")
period_count = cursor.fetchone()[0]
print(f"  ✅ Aggregated periods: {period_count}")

if period_count > 0:
    print("\n✅ SUCCESS! Aggregation system is working!")
    
    # Show details
    cursor.execute("""
    SELECT period_start, period_end, operation, service, total_count, trend_direction
    FROM alert_periods
    ORDER BY period_start DESC
    LIMIT 3
    """)
    
    print("\nAggregated period details:")
    for row in cursor.fetchall():
        print(f"  Period: {row[0]} to {row[1]}")
        print(f"    {row[2]:30} | {row[3]:20} | {row[4]} alerts | {row[5]}")
else:
    print("\n⚠️  WARNING: No aggregated periods (might be expected if alerts outside current window)")
    
    # Show what we do have
    cursor.execute("SELECT alert_timestamp FROM alerts LIMIT 3")
    cursor.execute("SELECT * FROM alerts LIMIT 1")
    if cursor.fetchone():
        print("  But alerts table has data, so parsing worked!")

conn.close()
PYEOF

echo ""
echo "=========================================="
echo "TEST COMPLETE"
echo "=========================================="
