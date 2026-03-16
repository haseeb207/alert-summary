#!/usr/bin/env python3
"""
Complete test with detailed logging.
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

print("=" * 70)
print("RUNNING COMPLETE AGGREGATION TEST")
print("=" * 70)
print("\n1️⃣  Starting agent...")

# Start agent with output to file
proc = subprocess.Popen(
    ["/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent/venv/bin/python3", "agent.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd='/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent'
)

print("   Agent running (PID: {})".format(proc.pid))
print("   Waiting 95 seconds for alerts to be scanned and aggregated...")

for i in range(19):
    time.sleep(5)
    pct = ((i+1) * 5) / 95 * 100
    print(f"   [{int(pct):3d}%] {(i+1)*5}s elapsed")

print("\n2️⃣  Stopping agent...")
proc.terminate()
try:
    stdout, stderr = proc.communicate(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    stdout, stderr = proc.communicate()

print("   ✅ Agent stopped\n")

# Show agent output
if stderr and 'NotOpenSSLWarning' not in stderr:
    print("⚠️  Agent errors:")
    print(stderr)
print()

# Check database
print("3️⃣  Database verification...")
print("-" * 70)

conn = sqlite3.connect('alerts.db')
cursor = conn.cursor()

# Count alerts
cursor.execute("SELECT COUNT(*) FROM alerts")
alert_count = cursor.fetchone()[0]
print(f"   ✅ Alerts in database: {alert_count}")

# Count periods
cursor.execute("SELECT COUNT(*) FROM alert_periods")
period_count = cursor.fetchone()[0]
print(f"   📊 Aggregated periods: {period_count}")

if alert_count == 0:
    print("\n   ❌ ERROR: No alerts found!")
else:
    if period_count > 0:
        print("\n✅ SUCCESS! Aggregation worked!")
        print("\n4️⃣  Aggregated Periods:")
        print("-" * 70)
        
        cursor.execute("""
        SELECT period_start, period_end, operation, service, total_count, 
               total_occurrences, trend_direction
        FROM alert_periods
        ORDER BY period_start DESC
        """)
        
        for row in cursor.fetchall():
            print(f"  Period: {row[0]} to {row[1]}")
            print(f"    Operation: {row[2]:30} Service: {row[3]}")
            print(f"    Count: {row[4]}, Occurrences: {row[5]}, Trend: {row[6]}")
            print()
    else:
        print("\n⚠️  WARNING: No aggregated periods created")
        print("   This suggests the aggregation check didn't run or alerts fell outside the window")

conn.close()

print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)
