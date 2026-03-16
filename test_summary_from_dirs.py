#!/usr/bin/env python3
"""
Test: Read alert files from watch directory, archive, and failed; parse them,
aggregate, and generate the same summary the agent would post to Teams.
Then print a per-file review so you can see what caused wrong namings.

Run from project root:
  python test_summary_from_dirs.py

Uses WATCH_DIR, SUMMARY_MODE, and AGGREGATION_PERIOD from .env. Optional: TEST_SHOW_RELATED_LOGS_LINK (true/false) to show or hide the Related logs column in the summary table (test only). Requires: dotenv, alert_parser, aggregator.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

WATCH_DIR = os.path.expanduser(os.getenv('WATCH_DIR', '') or '')
SUMMARY_MODE = (os.getenv('SUMMARY_MODE', 'full') or 'full').lower()
AGGREGATION_PERIOD_STR = os.getenv('AGGREGATION_PERIOD', '15m')
SUMMARY_TABLE_GROUP_BY_PAGE = (os.getenv('SUMMARY_TABLE_GROUP_BY_PAGE', 'false') or 'false').lower() == 'true'
# Test-only: set to false to hide Related logs column in the summary table
TEST_SHOW_RELATED_LOGS_LINK = (os.getenv('TEST_SHOW_RELATED_LOGS_LINK', 'false') or 'false').lower() == 'true'

from alert_parser import parse_alert
from aggregator import (
    aggregate_alerts_by_period,
    generate_period_summary,
    generate_simple_period_summary,
    format_period_label,
    parse_period_string,
)


def collect_txt_files(watch_path: Path, max_per_dir: int = 30):
    """Collect .txt paths from watch_dir, archive, and failed (each capped)."""
    out = []
    for sub in ['', 'archive', 'failed']:
        dir_path = watch_path / sub if sub else watch_path
        if not dir_path.is_dir():
            continue
        try:
            files = sorted(dir_path.glob('*.txt'))[:max_per_dir]
            out.extend([(f, sub or 'root') for f in files])
        except OSError as e:
            print(f"  Skip {dir_path}: {e}")
    return out


def main():
    print("=" * 72)
    print("Test: Build summary from files in watch dir, archive, and failed")
    print("=" * 72)
    if not WATCH_DIR:
        print("ERROR: WATCH_DIR not set in .env")
        return 1
    watch_path = Path(WATCH_DIR)
    if not watch_path.exists():
        print(f"ERROR: Watch path does not exist: {watch_path}")
        return 1
    print(f"Watch dir: {watch_path}\n")

    # Collect files
    file_list = collect_txt_files(watch_path)
    if not file_list:
        print("No .txt files found in root, archive, or failed.")
        return 1
    print(f"Found {len(file_list)} .txt file(s)\n")

    # Parse each file and build alerts list (with fake timestamp for aggregation)
    period_delta = parse_period_string(AGGREGATION_PERIOD_STR)
    period_end = datetime.now(timezone.utc)
    period_start = period_end - period_delta
    start_str = period_start.strftime('%Y-%m-%d %H:%M:%S')
    alerts = []
    per_file = []

    for file_path, source in file_list:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except OSError as e:
            per_file.append((file_path.name, None, str(e)))
            continue
        parsed = parse_alert(content, file_path.name)
        parsed['alert_timestamp'] = start_str
        parsed.setdefault('related_logs_url', '')
        # Include all alerts (ACTIVE and RECOVERED) so Unknown and other vague namings show in the table
        alerts.append(parsed)
        per_file.append((
            file_path.name,
            parsed.get('operation'),
            parsed.get('service'),
            parsed.get('status'),
            parsed.get('affected_pages', []),
        ))

    # Per-file review (namings)
    print("-" * 72)
    print("PER-FILE PARSING (operation, service, status, affected_pages)")
    print("-" * 72)
    vague = ('Unknown', 'Commerce', 'Checkout', 'Parse Error', 'Unknown Service')
    for fname, op, svc, status, pages in per_file:
        if op is None:
            print(f"  FAIL: {fname} -> {svc}")
            continue
        flag = "  <-- vague" if (op in vague or (svc and str(svc).startswith('Unknown'))) else ""
        print(f"  {fname}")
        print(f"    -> operation={op!r}, service={svc!r}, status={status}, pages={pages}{flag}")
    print()

    # Vague summary
    vague_ops = [op for _, op, _, _, _ in per_file if op and op in vague]
    vague_count = len(vague_ops)
    total_parsed = sum(1 for _, op, _, _, _ in per_file if op is not None)
    if vague_ops:
        print(f"Vague operation names seen: {set(vague_ops)} ({vague_count} file(s))")
        print()
    else:
        print(f"Review: No vague namings in this run ({total_parsed} files parsed, 0 Unknown/Commerce/Checkout).")
        print()

    # Aggregate and generate summary (same as agent: SUMMARY_MODE, AGGREGATION_PERIOD, SUMMARY_TABLE_GROUP_BY_PAGE)
    group_by_page = (SUMMARY_MODE == 'simple' and SUMMARY_TABLE_GROUP_BY_PAGE)
    aggregated = aggregate_alerts_by_period(alerts, period_delta, group_by_page=group_by_page)
    period_label = format_period_label(AGGREGATION_PERIOD_STR)
    use_simple = (SUMMARY_MODE == 'simple')

    print("-" * 72)
    print(f"SUMMARY (SUMMARY_MODE={SUMMARY_MODE!r}, SUMMARY_TABLE_GROUP_BY_PAGE={SUMMARY_TABLE_GROUP_BY_PAGE} from .env)")
    if not TEST_SHOW_RELATED_LOGS_LINK and use_simple:
        print("(Related logs column hidden via TEST_SHOW_RELATED_LOGS_LINK)")
    print("-" * 72)
    if aggregated:
        if use_simple:
            summary = generate_simple_period_summary(
                period_start, period_end, aggregated, period_label,
                include_related_logs=TEST_SHOW_RELATED_LOGS_LINK,
            )
            print(summary)
        else:
            summary = generate_period_summary(
                period_start, period_end, aggregated, period_label=period_label, use_simple=False
            )
            print(summary[:4000] + ("..." if len(summary) > 4000 else ""))
    else:
        print("(No alerts to aggregate.)")

    print()
    print("=" * 72)
    print("Review: Check PER-FILE PARSING above for any operation/service that looks wrong.")
    print("=" * 72)
    return 0


if __name__ == '__main__':
    sys.exit(main())
