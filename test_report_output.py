#!/usr/bin/env python3
"""
Test the improved report output: actual-window header, table sort by count, total row, cross-day times.
Run: python test_report_output.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

from aggregator import (
    format_actual_duration_label,
    format_period_in_timezones,
    generate_simple_period_summary,
    generate_period_summary,
)


def _make_aggregated():
    """Minimal aggregated_alerts with (op, svc) keys and varying counts for sort test."""
    return {
        ("GetCardPaymentAcceptPoint (PayPal Express)", "buy-www.example.com"): {
            "operation": "GetCardPaymentAcceptPoint (PayPal Express)",
            "service": "buy-www.example.com",
            "count": 1,
            "affected_pages": set(),
            "all_alerts": [{"subject": "[P3] Warn: API Profiling - Payment...", "related_logs_url": "https://example.com"}],
        },
        ("removeCartLines", "buy-www.example.com"): {
            "operation": "removeCartLines",
            "service": "buy-www.example.com",
            "count": 16,
            "affected_pages": {"cart"},
            "all_alerts": [{"subject": "[P3] Warn: API Profiling - Cart...", "related_logs_url": "https://example.com"}],
        },
        ("addCartCoupon", "buy-www.example.com"): {
            "operation": "addCartCoupon",
            "service": "buy-www.example.com",
            "count": 2,
            "affected_pages": {"cart"},
            "all_alerts": [{"subject": "[P3] Warn: API Profiling - Cart...", "related_logs_url": ""}],
        },
    }


def test_actual_duration_header():
    """Header uses actual window duration, not configured period."""
    start = datetime(2026, 3, 11, 10, 0, 0)
    end = datetime(2026, 3, 11, 15, 0, 0)  # 5h
    label = format_actual_duration_label(start, end)
    assert label == "5 hours", f"Expected '5 hours', got {label!r}"
    # With remainder minutes
    end2 = datetime(2026, 3, 11, 14, 58, 0)  # 4h 58m
    label2 = format_actual_duration_label(start, end2)
    assert "4h 58m" in label2 or "4" in label2, f"Expected 4h 58m style, got {label2!r}"
    print("  OK actual duration label")


def test_same_day_time_format():
    """Same-day window: time only, no date."""
    start = datetime(2026, 3, 11, 14, 0, 0)
    end = datetime(2026, 3, 11, 19, 0, 0)
    lines = format_period_in_timezones(start, end)
    assert len(lines) == 3 and "EST:" in lines[0], "Should have EST/CST/UTC"
    # No "Mar" in same-day (times only)
    assert all("Mar" not in line for line in lines), "Same-day should not include date"
    print("  OK same-day time format")


def test_cross_day_time_format():
    """Cross-day window: short date + time."""
    start = datetime(2026, 3, 10, 22, 0, 0)
    end = datetime(2026, 3, 11, 14, 0, 0)
    lines = format_period_in_timezones(start, end)
    assert len(lines) == 3
    assert "Mar 10" in lines[0] or "Mar 11" in lines[0], "Cross-day should include date"
    print("  OK cross-day time format")


def test_simple_summary_header_and_total():
    """Simple summary uses actual duration in header and has a Total row."""
    start = datetime(2026, 3, 11, 10, 0, 0)
    end = datetime(2026, 3, 11, 15, 0, 0)
    aggregated = _make_aggregated()
    summary = generate_simple_period_summary(start, end, aggregated, "1 hour", include_related_logs=True)
    assert "Summary for last 5 hours" in summary, f"Header should show actual 5h window: {summary[:200]!r}"
    assert "**Total**" in summary, "Should have Total row"
    assert "**19**" in summary, "Total should be 1+16+2=19"
    print("  OK header and total row")


def test_simple_summary_sorted_by_count():
    """Table rows are sorted by count descending (highest first)."""
    start = datetime(2026, 3, 11, 10, 0, 0)
    end = datetime(2026, 3, 11, 15, 0, 0)
    aggregated = _make_aggregated()
    summary = generate_simple_period_summary(start, end, aggregated, "1 hour", include_related_logs=False)
    # removeCartLines (16) should appear before addCartCoupon (2) and GetCard... (1)
    pos_16 = summary.find("| 16 |")
    pos_2 = summary.find("| 2 |")
    pos_1 = summary.find("| 1 |")
    assert pos_16 >= 0 and pos_2 >= 0 and pos_1 >= 0, "Counts 16, 2, 1 should appear"
    assert pos_16 < pos_2 and pos_2 < pos_1, "Order should be 16, then 2, then 1 (descending)"
    print("  OK table sorted by count descending")


def main():
    print("Testing improved report output")
    print("-" * 50)
    test_actual_duration_header()
    test_same_day_time_format()
    test_cross_day_time_format()
    test_simple_summary_header_and_total()
    test_simple_summary_sorted_by_count()
    print("-" * 50)
    print("All report output tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
