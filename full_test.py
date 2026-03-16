#!/usr/bin/env python3
"""
Run complete test of the aggregation pipeline.
"""
import subprocess
import time
import sqlite3
import sys
import os

os.chdir('/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent')

# Remove old database
if os.path.exists('alerts.db'):
    os.remove('alerts.db')

# Start agent
print("=" * 70)
print("STARTING AGGREGATION PIPELINE TEST")
print("=" * 70)
print("\n1️⃣  Starting agent (will run for 95 seconds)...")

proc = subprocess.Popen(
    ["/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent/venv/bin/python3", "agent.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd='/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent'
)

# Wait 95 seconds
print("   Waiting for alerts to be scanned and aggregated...")
for i in range(19):
    time.sleep(5)
    print(f"   ... {(i+1)*5}s elapsed")

# Stop agent
print("\n2️⃣  Stopping agent...")
proc.terminate()
try:
    stdout, stderr = proc.communicate(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    stdout, stderr = proc.communicate()

print("   ✅ Agent stopped")

# Show agent output if there were errors
if stderr and len(stderr) > 0:
    print("\n⚠️  Agent stderr (last 1000 chars):")
    print(stderr[-1000:])
print()

# Verify results
print("3️⃣  Checking database results...")
print("-" * 70)

conn = sqlite3.connect('alerts.db')
cursor = conn.cursor()

# Count alerts
cursor.execute("SELECT COUNT(*) FROM alerts")
alert_count = cursor.fetchone()[0]
print(f"   ✅ Total alerts in database: {alert_count}")

# Count periods
cursor.execute("SELECT COUNT(*) FROM alert_periods")
period_count = cursor.fetchone()[0]
print(f"   📊 Aggregated periods: {period_count}")

if alert_count == 0:
    print("\n   ⚠️  WARNING: No alerts found! Check if files are in main directory.")
    sys.exit(1)

if period_count == 0:
    print("\n   ⚠️  WARNING: No aggregated periods! Aggregation may not have run.")
    print("   (This can happen if all alerts fall outside the current time window)")
else:
    print("\n4️⃣  Aggregated Period Details:")
    print("-" * 70)
    
    cursor.execute("""
    SELECT period_start, period_end, operation, total_count, total_occurrences, trend_direction
    FROM alert_periods
    ORDER BY period_start DESC
    """)
    
    for row in cursor.fetchall():
        print(f"   Period: {row[0][:19]} to {row[1][:19]}")
        print(f"   • Operation: {row[2]}")
        print(f"   • Count: {row[3]}, Occurrences: {row[4]}, Trend: {row[5]}")
        print()

# Check page correlations
cursor.execute("SELECT COUNT(*) FROM page_correlations")
page_count = cursor.fetchone()[0]
print(f"   📍 Page correlations tracked: {page_count}")

if page_count > 0:
    cursor.execute("""
    SELECT operation, COUNT(DISTINCT page) as page_count
    FROM page_correlations
    GROUP BY operation
    """)
    
    print("\n   Pages by operation:")
    for row in cursor.fetchall():
        print(f"   • {row[0]:30} → {row[1]} pages")

conn.close()

print("\n" + "=" * 70)
print("✅ TEST COMPLETE")
print("=" * 70)
