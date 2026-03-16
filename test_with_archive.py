#!/usr/bin/env python3
"""
Test agent pipeline using sample .txt files from the OneDrive archive folder.
Uses DRY_RUN; does not post to Teams. Verifies parsing, aggregation, and summary wording.
"""

import os
import sys

# Use project root and same DB path as agent
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

# Ensure single DB and no Teams post
os.environ['DRY_RUN'] = 'true'

import database
database.DB_FILE = os.path.join(PROJECT_DIR, 'alerts.db')

from datetime import datetime, timedelta
from alert_parser import parse_alert
from aggregator import (
    aggregate_alerts_by_period,
    generate_period_summary,
    generate_simple_period_summary,
    format_period_label,
)

ARCHIVE_DIR = '/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails/archive'

# Minimal inline sample if archive is not accessible
SAMPLE_ALERT = """
[P3] Warn: API Profiling - Cart - High duration detected for addCartLine

🚨 High Duration Alert: addCartLine GraphQL API

Alert Details:
- Service: buy-www.mattressfirm-com.vercel.app
- Path: /cart
- GraphQL: addCartLine
- Duration Threshold: >2000ms (2 seconds)
- Time Window: Last 1 hour
- Count: 6.0

Related Logs
[https://app.datadoghq.com/logs/analytics?from_ts=1773366649000&to_ts=1773370249000]
"""


def main():
    print("=" * 80)
    print("TEST: Agent pipeline using archive sample files")
    print("=" * 80)

    # Fresh DB
    if os.path.exists(database.DB_FILE):
        os.remove(database.DB_FILE)
    if not database.init_database():
        print("ERROR: Failed to init database")
        return 1

    # Prefer archive .txt files; fall back to inline sample if archive not accessible
    files_to_use = []
    try:
        names = sorted(f for f in os.listdir(ARCHIVE_DIR) if f.endswith('.txt'))
        files_to_use = names[:10]
    except OSError as e:
        print(f"Note: Archive dir not accessible ({e}). Using inline sample.")

    if not files_to_use:
        print("Using inline sample alert (no archive files).")
        files_to_use = [('sample_alert.txt', SAMPLE_ALERT)]

    print(f"\nReading {len(files_to_use)} files...")
    alerts_inserted = 0
    for item in files_to_use:
        if isinstance(item, tuple):
            fname, content = item
        else:
            fname = item
            fpath = os.path.join(ARCHIVE_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except OSError as e:
                print(f"  Skip {fname}: {e}")
                continue
        parsed = parse_alert(content, fname)
        database.insert_alert(
            operation=parsed['operation'],
            service=parsed['service'],
            alert_type=parsed['alert_type'],
            severity=parsed['severity'],
            condition=parsed['condition'],
            occurrence_count=parsed['occurrence_count'],
            time_window=parsed['time_window'],
            affected_pages=parsed['affected_pages'],
            status=parsed['status'],
            file_name=fname,
            raw_content=content,
            related_logs_url=parsed.get('related_logs_url', '')
        )
        alerts_inserted += 1
        print(f"  Inserted: {parsed['operation']} ({parsed['severity']}) - {parsed.get('status', 'ACTIVE')}")

    print(f"\nInserted {alerts_inserted} alerts into DB.")

    # Get alerts back for a recent period (use now - 2h to now so we include them)
    period_end = datetime.utcnow()
    period_start = period_end - timedelta(hours=2)
    start_str = period_start.strftime('%Y-%m-%d %H:%M:%S')
    end_str = period_end.strftime('%Y-%m-%d %H:%M:%S')

    alerts = database.get_alerts_in_period(start_str, end_str)
    print(f"Queried {len(alerts)} alerts in period {start_str} -> {end_str}")

    if not alerts:
        print("No alerts in period (timestamps may be in future). Using mock period for summary only.")
        period_start = datetime(2026, 3, 11, 14, 0, 0)
        period_end = datetime(2026, 3, 11, 15, 0, 0)
        alerts = []
        for item in files_to_use[:8]:
            if isinstance(item, tuple):
                fname, content = item
            else:
                fpath = os.path.join(ARCHIVE_DIR, item)
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    fname = item
                except OSError:
                    continue
            parsed = parse_alert(content, fname)
            parsed['alert_timestamp'] = start_str
            parsed.setdefault('related_logs_url', '')
            alerts.append(parsed)
        print(f"Using {len(alerts)} in-memory alerts for summary demo.")
    else:
        period_start = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
        period_end = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')

    period_delta = timedelta(hours=1)
    aggregated = aggregate_alerts_by_period(alerts, period_delta)
    print(f"Aggregated into {len(aggregated)} operation/service groups.\n")

    period_label = format_period_label('1h')

    # Test FULL summary
    summary_full = generate_period_summary(
        period_start, period_end, aggregated, period_label=period_label, use_simple=False
    )
    print("GENERATED FULL SUMMARY:")
    print("-" * 80)
    print(summary_full)
    print("-" * 80)
    assert "Summary for last" in summary_full, "Header should say Summary for last"
    assert "Only triggered (non-recovered)" in summary_full, "Should mention triggered only"
    assert "In this period:" in summary_full or "Total slow requests reported" in summary_full, "Full summary body"
    print("Full summary checks passed.")

    # Test SIMPLE summary
    summary_simple = generate_simple_period_summary(
        period_start, period_end, aggregated, period_label=period_label
    )
    print("\nGENERATED SIMPLE SUMMARY:")
    print("-" * 80)
    print(summary_simple)
    print("-" * 80)
    assert "Summary for last" in summary_simple, "Simple header"
    assert "EST:" in summary_simple and "UTC:" in summary_simple, "Timezone lines"
    assert "| Alert name |" in summary_simple or "| " in summary_simple, "Table present"
    print("Simple summary checks passed.")

    print("\nAll tests passed.")
    return 0

if __name__ == '__main__':
    sys.exit(main())
