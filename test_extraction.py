#!/usr/bin/env python3
"""Quick test of new extraction functions."""

import sys
sys.path.insert(0, '.')

from alert_parser import (
    extract_threshold_from_alert,
    extract_time_window_from_alert,
    extract_count_from_alert,
    extract_pages_from_alert,
    parse_alert
)

# Read first alert file
import os
watch_dir = '/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails'
files = [f for f in os.listdir(watch_dir) if f.endswith('.txt') and os.path.isfile(os.path.join(watch_dir, f))]

if not files:
    print("❌ No alert files found!")
    sys.exit(1)

print(f"Testing {len(files)} alert files...\n")

for fname in files[:3]:  # Test first 3
    fpath = os.path.join(watch_dir, fname)
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Test each extraction function
    threshold = extract_threshold_from_aler#!/usr/bin/env python3
"""Quick test of new extraction functions."""

import sys
sys.path.insert(0,_a"""Quick test of new es
import sys
sys.path.insert(0, '.')

from al  #sys.path.se
from alert_parser impert    extract_threshold_fro p    extract_time_window_from_ale."    extract_count_from_alert,
    at  n']}")
    print(f"  Path/Pa    parse_alert
)

# Read fi T)

# Read firsesholimport os
watch_dir = e watch_di{tfiles = [f for f in os.listdir(watch_dir) if f.endswith('.txt') and osxtraction tests completed!")
