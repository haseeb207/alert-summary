#!/usr/bin/env python3
"""
End-to-end test for Ollama AI integration across all enhancement points.

Covers:
  1. Health check (Ollama reachable)
  2. File flow: read alert files → parse → if vague operation, call Ollama (same as agent)
  3. Narrative summary: from mock op_counts and optionally from real DB aggregated data
  4. Full pipeline: optional run using real agent code path (process + report data)

Run with Ollama running locally (e.g. ollama serve && ollama run llama3.2).
Uses .env for OLLAMA_BASE_URL and OLLAMA_MODEL if set.

  python test_ollama.py                    # use default sample_alerts/ and mock DB data
  python test_ollama.py /path/to/alerts    # use your own .txt alert directory
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import ollama_client
import alert_parser
import aggregator
import database

# Same vague set as in agent.py (operation extraction only when one of these)
VAGUE_OPERATIONS = ('Unknown', 'Commerce', 'Checkout', 'Parse Error')

# Inline sample that parses to a vague operation (no fixture file needed)
SAMPLE_ALERT_VAGUE = """
[P3] Warn: Custom integration timeout - Payment gateway slow

Alert Details:
- Service: buy-www.mattressfirm-com.vercel.app
- Path: /checkout
- Duration Threshold: >3000ms
- Time Window: Last 1 hour
- Count: 5.0

The checkout flow is calling an external payment provider.
"""


def section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def test_health() -> bool:
    """1. Health check - same as agent startup."""
    section("1. Health check (Ollama reachable)")
    ok = ollama_client.check_ollama_available()
    if not ok:
        print("FAIL: Ollama is not reachable. Start with: ollama serve && ollama run llama3.2")
        return False
    print("OK: Ollama is reachable")
    return True


def test_operation_extraction_from_files(alert_dir: Optional[Path]) -> bool:
    """
    2. File flow: read alert files → parse → if vague, call get_operation_from_alert (same as agent).
    Uses sample_alerts/ if alert_dir is None; otherwise uses alert_dir. Also runs inline vague sample.
    """
    section("2. File flow: alert files → parse → Ollama (operation extraction)")

    # Collect (content, filename) from directory
    files_to_test: List[Tuple[str, str]] = []
    if alert_dir and alert_dir.is_dir():
        for p in sorted(alert_dir.glob("*.txt")):
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                files_to_test.append((content, p.name))
            except Exception as e:
                print(f"  Skip {p.name}: {e}")
    if not files_to_test:
        # Default: use built-in samples (vague + specific)
        default_dir = PROJECT_DIR / "sample_alerts"
        if default_dir.is_dir():
            for p in sorted(default_dir.glob("*.txt")):
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    files_to_test.append((content, p.name))
                except Exception as e:
                    print(f"  Skip {p.name}: {e}")
        # Always add inline vague sample so at least one triggers Ollama
        files_to_test.append((SAMPLE_ALERT_VAGUE.strip(), "(inline vague sample)"))

    if not files_to_test:
        files_to_test.append((SAMPLE_ALERT_VAGUE.strip(), "(inline vague sample)"))

    all_ok = True
    for alert_text, filename in files_to_test:
        parsed = alert_parser.parse_alert(alert_text, filename)
        op = parsed.get("operation", "?")
        is_vague = op in VAGUE_OPERATIONS

        print(f"\n  File: {filename}")
        print(f"    Parsed operation (regex): {op!r}")

        if is_vague:
            ai_op = ollama_client.get_operation_from_alert(alert_text)
            if ai_op:
                print(f"    AI operation (Ollama):  {ai_op!r}")
            else:
                print("    AI operation (Ollama):  (none or failed)")
                all_ok = False
        else:
            print("    (Specific operation — Ollama not called, as in agent)")

    return all_ok


def test_narrative_summary_mock() -> bool:
    """3a. Narrative summary from mock op_counts (same shape as agent's aggregated → op_counts)."""
    section("3a. Narrative summary (mock op_counts — same as agent input)")
    ops_with_counts = [
        ("removeCartLines", 5),
        ("GetCartDelivery", 3),
        ("GetAddressFromZipCode", 2),
    ]
    print("  Input (operation, count):", ops_with_counts)
    sentence = ollama_client.get_period_summary_sentence(ops_with_counts)
    if sentence:
        print(f"  AI summary: {sentence!r}")
        return True
    print("  AI summary: (none or failed)")
    return False


def test_narrative_summary_from_db() -> bool:
    """
    3b. Narrative summary from real DB: get_alerts_in_period → aggregate → op_counts → Ollama.
    Same flow as agent's check_and_report (without posting).
    """
    section("3b. Narrative summary (from database + aggregation)")

    if not Path(database.DB_FILE).exists():
        print("  Skip: no alerts.db; run agent or insert alerts first.")
        return True

    database.init_database()
    period_end = datetime.utcnow()
    period_start = period_end - timedelta(hours=24)
    start_str = period_start.strftime("%Y-%m-%d %H:%M:%S")
    end_str = period_end.strftime("%Y-%m-%d %H:%M:%S")

    alerts = database.get_alerts_in_period(start_str, end_str)
    if not alerts:
        print("  Skip: no alerts in last 24h in DB; insert alerts to test this path.")
        return True

    period_delta = timedelta(hours=1)
    aggregated = aggregator.aggregate_alerts_by_period(alerts, period_delta, group_by_page=False)
    if not aggregated:
        print("  Skip: aggregation empty (e.g. all RECOVERED).")
        return True

    # Build op_counts exactly like agent.py
    op_counts: dict[str, int] = {}
    for key, data in aggregated.items():
        op = key[0] if isinstance(key, tuple) else key
        op_counts[op] = op_counts.get(op, 0) + data.get("count", 0)
    ops_with_counts = list(op_counts.items())

    print(f"  Period: {start_str} -> {end_str}")
    print(f"  Alerts in DB (period): {len(alerts)}")
    print(f"  Aggregated keys: {len(aggregated)}")
    print("  op_counts (operation, count):", ops_with_counts)

    sentence = ollama_client.get_period_summary_sentence(ops_with_counts)
    if sentence:
        print(f"  AI summary: {sentence!r}")
        return True
    print("  AI summary: (none or failed)")
    return False


def test_full_pipeline_with_fixture(alert_dir: Optional[Path]) -> bool:
    """
    4. Full pipeline: parse file → if vague call Ollama → then use same text as if we had
    stored and aggregated (we don't insert into DB here to avoid side effects). This mirrors
    the two places the agent uses Ollama: process_alert_file and check_and_report.
    """
    section("4. Full pipeline (parse + Ollama op extraction; then narrative from mock)")

    # Use one vague alert to simulate process_alert_file path
    alert_text = SAMPLE_ALERT_VAGUE.strip()
    if alert_dir and alert_dir.is_dir():
        vague_files = [p for p in alert_dir.glob("*.txt") if "vague" in p.name.lower()]
        if vague_files:
            alert_text = vague_files[0].read_text(encoding="utf-8", errors="ignore")

    parsed = alert_parser.parse_alert(alert_text, "pipeline_test.txt")
    op = parsed.get("operation", "?")
    is_vague = op in VAGUE_OPERATIONS

    print("  Step A: Parse alert (same as agent)")
    print(f"    Parsed operation: {op!r} (vague={is_vague})")

    if is_vague:
        ai_op = ollama_client.get_operation_from_alert(alert_text)
        if ai_op and len(ai_op) <= 80 and "\n" not in ai_op:
            parsed["operation"] = ai_op
            print(f"    After Ollama: {ai_op!r}")
        else:
            print("    Ollama returned invalid/empty; keeping regex op.")

    # Simulate period report: build op_counts and get narrative (as in check_and_report)
    print("  Step B: Narrative summary (same input shape as agent)")
    ops_with_counts = [(parsed["operation"], 1)]  # single alert
    sentence = ollama_client.get_period_summary_sentence(ops_with_counts)
    if sentence:
        print(f"    AI summary: {sentence!r}")
        return True
    print("    AI summary: (none or failed)")
    return False


def main() -> int:
    alert_dir = None
    if len(sys.argv) > 1:
        alert_dir = Path(sys.argv[1])

    print("Ollama AI integration — all enhancement points")
    if alert_dir:
        print(f"Alert directory: {alert_dir}")
    else:
        print("Alert directory: sample_alerts/ (default) + inline sample")

    if not test_health():
        return 1

    test_operation_extraction_from_files(alert_dir)
    test_narrative_summary_mock()
    test_narrative_summary_from_db()
    test_full_pipeline_with_fixture(alert_dir)

    section("Done")
    print("All flows exercised. Check output above for any failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
