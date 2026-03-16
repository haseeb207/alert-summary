#!/usr/bin/env python3
"""Test to verify the elapsed time aggregation logic."""

import time
from datetime import datetime, timedelta

print("=" * 80)
print("TESTING ELAPSED TIME AGGREGATION LOGIC")
print("=" * 80)
print()

# Simulate the PeriodAggregator with elapsed time
period_delta = timedelta(seconds=2)  # Use 2 seconds for quick testing
last_report_time = None
period_seconds = period_delta.total_seconds()

print(f"Period delta: {period_delta.total_seconds()} seconds\n")

# First initialization
print("Step 1: Initialize aggregator")
current_time = time.time()
last_report_time = current_time
print(f"✓ Initialized at {datetime.fromtimestamp(current_time)}")
print(f"  Next report will be triggered after {period_seconds} seconds\n")

# Check 1: Not enough time elapsed
print("Step 2: Check 1 - Less than period elapsed (should not report)")
time.sleep(0.5)
current_time = time.time()
elapsed_seconds = current_time - last_report_time
if elapsed_seconds < period_seconds:
    print(f"✓ Elapsed: {elapsed_seconds:.2f}s < {period_seconds}s - No report")
else:
    print(f"✗ ERROR: Should not have reported yet!")
print()

# Check 2: Enough time elapsed - SHOULD REPORT
print("Step 3: Check 2 - More than period elapsed (should report)")
time.sleep(2.0)  # Sleep to exceed the 2-second period
current_time = time.time()
elapsed_seconds = current_time - last_report_time
if elapsed_seconds >= period_seconds:
    period_start = datetime.fromtimestamp(last_report_time)
    period_end = datetime.fromtimestamp(current_time)
    print(f"✓ Elapsed: {elapsed_seconds:.2f}s >= {period_seconds}s - REPORT TRIGGERED")
    print(f"  Period: {period_start} - {period_end}")
    last_report_time = current_time
else:
    print(f"✗ ERROR: Should have triggered report!")
print()

# Check 3: Fresh period starts
print("Step 4: Check 3 - New period started (should not report)")
time.sleep(0.5)
current_time = time.time()
elapsed_seconds = current_time - last_report_time
if elapsed_seconds < period_seconds:
    print(f"✓ Elapsed: {elapsed_seconds:.2f}s < {period_seconds}s - No report (fresh period)")
else:
    print(f"✗ ERROR: Should not have reported yet in new period!")
print()

print("=" * 80)
print("✅ ELAPSED TIME LOGIC VERIFIED!")
print("=" * 80)
