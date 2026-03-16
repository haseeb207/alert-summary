#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '.')

from alert_parser import parse_alert

watch_dir = '/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails'
archive_path = os.path.join(watch_dir, 'archive')

# Get all alert files
all_files = sorted([f for f in os.listdir(archive_path) if f.endswith('.txt')])[:8]

print("\n🧪 TESTING ALERT PARSER - All 8 Alerts\n")
print("=" * 80)
print(f"{'#':3} | {'Operation Name':30} | {'Severity':5} | {'Status':10}")
print("=" * 80)

operations = {}
for i, fname in enumerate(all_files, 1):
    fpath = os.path.join(archive_path, fname)
    with open(fpath, 'r') as f:
        content = f.read()
    
    parsed = parse_alert(content, fname)
    op = parsed['operation']
    operations[op] = operations.get(op, 0) + 1
    
    print(f"{i:3} | {op:30} | {parsed['severity']:5} | {parsed['status']:10}")

print("=" * 80)
print("\n📊 Aggregation Summary:")
print("=" * 80)
for op, count in sorted(operations.items()):
    print(f"  {op:30} : {count} alerts")
print("=" * 80)
