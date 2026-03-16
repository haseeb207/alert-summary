#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('alerts.db')
cursor = conn.cursor()

print("Alert timestamps in database:")
cursor.execute("SELECT alert_timestamp, operation FROM alerts LIMIT 2")
for row in cursor.fetchall():
    print(f"  {row[0]:30} | {row[1]}")

# Check the calculated period
now = datetime.utcnow()
period_3h = timedelta(hours=3)
period_seconds = int(period_3h.total_seconds())

seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
periods_since_midnight = seconds_since_midnight // period_seconds
period_start_seconds = periods_since_midnight * period_seconds

period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
period_start = period_start + timedelta(seconds=period_start_seconds)
period_end = period_start + period_3h

print(f"\nCurrent UTC time: {now}")
print(f"Calculated period: {period_start.strftime('%Y-%m-%d %H:%M:%S')} to {period_end.strftime('%Y-%m-%d %H:%M:%S')}")

# Test query
period_start_str = period_start.strftime('%Y-%m-%d %H:%M:%S')
period_end_str = period_end.strftime('%Y-%m-%d %H:%M:%S')

print(f"\nTesting BETWEEN query:")
print(f"  Period start: {period_start_str}")
print(f"  Period end:   {period_end_str}")

cursor.execute("""
  SELECT COUNT(*) FROM alerts
  WHERE alert_timestamp BETWEEN ? AND ?
""", (period_start_str, period_end_str))

count = cursor.fetchone()[0]
print(f"  Alerts matching: {count}")

# Show all alert timestamps for debugging
print("\nAll alert timestamps:")
cursor.execute("SELECT alert_timestamp FROM alerts ORDER BY alert_timestamp")
for row in cursor.fetchall():
    print(f"  {row[0]}")

conn.close()
