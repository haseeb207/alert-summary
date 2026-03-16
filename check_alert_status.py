#!/usr/bin/env python3
import sqlite3
import re

conn = sqlite3.connect('alerts.db')
cursor = conn.cursor()

# Get statuses of all alerts
cursor.execute("SELECT COUNT(*), status FROM alerts GROUP BY status")
print("Alert statuses:")
for row in cursor.fetchall():
    print(f"  {row[1]}: {row[0]}")

# Get raw content of first alert
cursor.execute("SELECT raw_content, status FROM alerts LIMIT 1")
row = cursor.fetchone()

if row:
    content = row[0]
    status = row[1]
    
    print(f"\n=== FIRST ALERT ===")
    print(f"Status: {status}")
    print(f"\nContent (first 600 chars):")
    print(content[:600])
    print("\n---")
    
    # Check for recovery keywords
    recovery_keywords = ['recovered', 'resolved', 'back to normal', 'recovery complete', 'issue resolved', 'alert cleared']
    
    print("\nRecovery keyword check:")
    found_any = False
    for keyword in recovery_keywords:
        if re.search(keyword, content, re.IGNORECASE):
            found_any = True
            print(f"  ❌ FOUND: '{keyword}'")
            # Show context
            idx = content.lower().find(keyword.lower())
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(content), idx + len(keyword) + 40)
                print(f"     >>> {content[start:end]}")
    
    if not found_any:
        print("  ✅ No false positives detected")

conn.close()
