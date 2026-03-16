#!/usr/bin/env python3
"""Debug script to check what's in the database."""

import sqlite3
import sys
from datetime import datetime, timedelta

DB_FILE = 'alerts.db'

try:
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all alerts
        cursor.execute("SELECT operation, occurrence_count, time_window, alert_timestamp FROM alerts LIMIT 10")
        rows = cursor.fetchall()
        
        print(f"Total alerts in DB: {cursor.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]}\n")
        
        if rows:
            print("Sample alerts (first 10):")
            print("-" * 80)
            for row in rows:
                row_dict = dict(row)
                print(f"Operation: {row_dict['operation']}")
                print(f"  Occurrence Count: {row_dict['occurrence_count']} (type: {type(row_dict['occurrence_count']).__name__})")
                print(f"  Time Window: {row_dict['time_window']}")
                print(f"  Timestamp: {row_dict['alert_timestamp']}")
                print()
        else:
            print("⚠️  No alerts found in database!")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
