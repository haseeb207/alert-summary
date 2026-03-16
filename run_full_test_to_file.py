#!/usr/bin/env python3
"""Run full test with aggregation and save output."""

import sys
import os
import tempfile
sys.path.insert(0, '.')

# Set DRY_RUN
os.environ['DRY_RUN'] = 'true'

output = []

try:
    # Clean db
    if os.path.exists('alerts.db'):
        os.remove('alerts.db')
    
    # Import and run test
    import database
    from full_test import run_full_test
    
    output.append("=" * 80)
    output.append("FULL TEST WITH AGGREGATION")
    output.append("=" * 80)
    output.append("")
    
    # Initialize database
    database.init_database()
    output.append("✅ Database initialized")
    
    # Run full test
    result = run_full_test()
    output.append(str(result))
    
    output.append("")
    output.append("=" * 80)
    output.append("TEST COMPLETED SUCCESSFULLY")
    output.append("=" * 80)
    
except Exception as e:
    output.append("")
    output.append(f"❌ ERROR: {e}")
    import traceback
    output.append("")
    output.append(traceback.format_exc())

# Write to file
with open('full_test_result.txt', 'w') as f:
    f.write('\n'.join(output))

print("Full test results written to full_test_result.txt")
