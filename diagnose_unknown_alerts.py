#!/usr/bin/env python3
"""
Diagnose alerts that were stored with operation='Unknown'.
Reads from the agent's DB, shows raw content snippets, and re-parses with the
current parser so you can see what went wrong and what the parser would output now.

Run from project root: python diagnose_unknown_alerts.py
Optional: pass a period in UTC to limit to alerts from that report window, e.g.:
  python diagnose_unknown_alerts.py "2026-03-13 17:06:01" "2026-03-13 17:21:29"
"""

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

import sqlite3
import database
database.DB_FILE = os.path.join(PROJECT_DIR, 'alerts.db')
DB_FILE = database.DB_FILE

from alert_parser import parse_alert


def first_lines(raw: str, max_chars: int = 1800) -> str:
    """First chunk of raw content (subject + Alert Details)."""
    if not raw:
        return ""
    raw = raw.strip()
    return raw[:max_chars] + ("..." if len(raw) > max_chars else "")


def main():
    period_start = sys.argv[1] if len(sys.argv) > 1 else None
    period_end = sys.argv[2] if len(sys.argv) > 2 else None

    print("=" * 70)
    print("Diagnose: Alerts stored as operation='Unknown'")
    print("=" * 70)
    print(f"DB: {database.DB_FILE}")
    if period_start and period_end:
        print(f"Period (UTC): {period_start} → {period_end}")
    else:
        print("Period: all time (or pass period_start period_end in UTC)")
    print()

    if not os.path.exists(DB_FILE):
        print("No database found. Run the agent first so alerts are stored.")
        return 1

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if period_start and period_end:
            cursor.execute(
                """
                SELECT id, operation, service, file_name, alert_timestamp, raw_content, affected_pages
                FROM alerts
                WHERE operation = 'Unknown' AND alert_timestamp BETWEEN ? AND ?
                ORDER BY alert_timestamp
                """,
                (period_start, period_end),
            )
        else:
            cursor.execute(
                """
                SELECT id, operation, service, file_name, alert_timestamp, raw_content, affected_pages
                FROM alerts
                WHERE operation = 'Unknown'
                ORDER BY alert_timestamp DESC
                LIMIT 50
                """
            )
        rows = cursor.fetchall()

    if not rows:
        print("No alerts with operation='Unknown' in the selected period.")
        return 0

    print(f"Found {len(rows)} alert(s) with operation='Unknown'\n")

    for i, row in enumerate(rows, 1):
        print("-" * 70)
        print(f"Unknown alert #{i} | id={row['id']} | file={row['file_name']}")
        print(f"  stored: operation={row['operation']!r}, service={row['service']!r}, pages={row['affected_pages']}")
        print()
        raw = row["raw_content"] or ""
        snippet = first_lines(raw)
        print("  Raw content (start):")
        for line in snippet.splitlines():
            print("    ", line)
        print()
        # Re-parse with current parser
        reparsed = parse_alert(raw, row["file_name"] or "unknown.txt")
        print(f"  Re-parsed with current parser: operation={reparsed['operation']!r}, service={reparsed['service']!r}")
        if reparsed["operation"] != "Unknown":
            print("  → Parser would now extract a better name for new alerts.")
        else:
            print("  → Still Unknown: consider adding a pattern for the text above (e.g. subject or Alert Details).")
        print()

    print("=" * 70)
    print("What happens to Unknown in Teams:")
    print("  - In the simple-summary table, each Unknown row is shown as")
    print("    'Unknown (path: <page>)' or 'Unknown (<service>)' so multiple Unknown rows are distinguishable.")
    print("  - New alerts will use the improved parser (Commerce/GetX, Path, API Profiling Alert, etc.).")
    print("  - Existing DB rows stay 'Unknown' until new emails are processed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
