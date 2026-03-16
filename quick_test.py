#!/usr/bin/env python3
"""Quick parser test"""
import os
import sys
sys.path.insert(0, '.')

from alert_parser import parse_alert

watch_dir = '/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails'
archive = os.path.join(watch_dir, 'archive')

files = sorted([f for f in os.listdir(archive) if f.endswith('.txt')])[:8]

print("\n📋 PARSER TEST RESULTS:\n")
for i, fname in enumerate(files, 1):
    with open(os.path.join(archive, fname)) as f:
        parsed = parse_alert(f.read(), fname)
    print(f"{i}. {parsed['operation']}")
