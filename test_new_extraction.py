#!/usr/bin/env python3
"""Test new extraction functions - saves output to file."""

import sys
import os
sys.path.insert(0, '.')

from alert_parser import (
    extract_threshold_from_alert,
    extract_time_window_from_alert,
    extract_count_from_alert,
    extract_pages_from_alert,
    parse_alert
)

output = []

try:
    watch_dir = '/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails'
    files = [f for f in os.listdir(watch_dir) if f.endswith('.txt') and os.path.isfile(os.path.join(watch_dir, f))]
    
    output.append(f"Testing extraction functions on {len(files)} alert files:\n")
    
    for fname in sorted(files)[:5]:  # Test first 5
        fpath = os.path.join(watch_dir, fname)
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        try:
            # Test each extraction function
            threshold = extract_threshold_from_alert(content)
            time_window = extract_time_window_from_alert(content)
            count = extract_count_from_alert(content)
            pages = extract_pages_from_alert(content)
            
            # Full parse
            parsed = parse_alert(content, fname)
            
            output.append(f"File: {fname[:50]}...")
            output.append(f"  API Operation: {parsed['operation']}")
            output.append(f"  Service: {parsed['service']}")
            output.append(f"  Path/Pages: {pages}")
            output.append(f"  Threshold: {threshold}")
            output.append(f"  Time Window: {time_window}")
            output.append(f"  Count: {count}")
            output.append(f"  Status: {parsed['status']}")
            output.append("")
        except Exception as e:
            output.append(f"ERROR processing {fname}: {e}")
            import traceback
            output.append(traceback.format_exc())
            output.append("")
    
    output.append("✅ Extraction test completed!")
    
except Exception as e:
    output.append(f"FATAL ERROR: {e}")
    import traceback
    output.append(traceback.format_exc())

# Write to file
with open('extraction_test_result.txt', 'w') as f:
    f.write('\n'.join(output))

print("Test output written to extraction_test_result.txt")
