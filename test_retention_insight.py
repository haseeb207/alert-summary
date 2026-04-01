#!/usr/bin/env python3
"""Tests for retention top-ops query and history insight validation."""

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

import database
import ollama_client


def test_validate_insight_accepts_fixed_phrase():
    assert ollama_client.validate_history_insight_text(
        "No prior-period comparison available.",
        {"removeCartLines"},
    )


def test_validate_insight_accepts_only_allowed_ops_and_stopwords():
    allowed = {"removeCartLines", "ATPInventoryDynamic"}
    assert ollama_client.validate_history_insight_text(
        "removeCartLines shows higher volume than in the prior period.",
        allowed,
    )


def test_validate_insight_rejects_unknown_identifier():
    allowed = {"removeCartLines"}
    assert not ollama_client.validate_history_insight_text(
        "FakeApiName dominates compared to removeCartLines.",
        allowed,
    )


def test_get_top_operations_in_range():
    database.DB_FILE = str(PROJECT_DIR / "test_retention_insight_temp.db")
    if os.path.exists(database.DB_FILE):
        os.remove(database.DB_FILE)
    database.init_database()
    database.insert_alert(
        "opA", "svc", "High Duration", "P3", "x", 1, "1h", ["cart"], "ACTIVE",
        "f1.txt", "body",
    )
    database.insert_alert(
        "opA", "svc", "High Duration", "P3", "x", 1, "1h", ["cart"], "ACTIVE",
        "f2.txt", "body",
    )
    database.insert_alert(
        "opB", "svc", "High Duration", "P3", "x", 1, "1h", ["cart"], "ACTIVE",
        "f3.txt", "body",
    )
    rows = database.get_top_operations_in_range("2000-01-01 00:00:00", "2099-01-01 00:00:00", 5, True)
    assert rows[0][0] == "opA" and rows[0][1] == 2
    assert rows[1][0] == "opB" and rows[1][1] == 1
    os.remove(database.DB_FILE)
    database.DB_FILE = str(PROJECT_DIR / "alerts.db")


def main():
    test_validate_insight_accepts_fixed_phrase()
    test_validate_insight_accepts_only_allowed_ops_and_stopwords()
    test_validate_insight_rejects_unknown_identifier()
    test_get_top_operations_in_range()
    print("All retention/insight tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
