"""
SQLite Database Helper Module for Alert Aggregation

Handles all database operations: initialization, insertion, querying, and cleanup.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger('datadog_agent')

DB_FILE = 'alerts.db'


def init_database():
    """Initialize SQLite database with schema."""
    db_path = Path(DB_FILE)
    # Schema next to DB so it works regardless of process cwd
    schema_path = db_path.parent / 'schema.sql'
    if not schema_path.exists():
        logger.error(f"Schema file not found: {schema_path}")
        return False
    
    try:
        with open(schema_path, 'r') as f:
            schema = f.read()
        
        with sqlite3.connect(DB_FILE) as conn:
            conn.executescript(schema)
            conn.commit()
            # Migration: add related_logs_url to alerts if missing (existing DBs)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(alerts)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'related_logs_url' not in columns:
                cursor.execute("ALTER TABLE alerts ADD COLUMN related_logs_url TEXT")
                conn.commit()
                logger.info("Added related_logs_url column to alerts table")
        
        logger.info(f"Database initialized: {DB_FILE}")
        return True
    
    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        return False


def insert_alert(operation, service, alert_type, severity, condition, 
                  occurrence_count, time_window, affected_pages, status, 
                  file_name, raw_content, related_logs_url=''):
    """Insert a parsed alert into the database."""
    try:
        affected_pages_str = ','.join(affected_pages) if affected_pages else 'unknown'
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO alerts 
                (operation, service, alert_type, severity, condition, 
                 occurrence_count, time_window, affected_pages, status, 
                 related_logs_url, file_name, raw_content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (operation, service, alert_type, severity, condition,
                  occurrence_count, time_window, affected_pages_str, status,
                  related_logs_url or '', file_name, raw_content))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error inserting alert: {e}", exc_info=True)
        return False


def get_last_report_time():
    """
    Get last report time from agent_state.
    Returns (timestamp_float, raw_value_str). (None, None) if never set.
    Use raw_value_str in try_claim_report_period so WHERE clause matches exactly (avoids float->str roundtrip).
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM agent_state WHERE key = 'last_report_time'",
            )
            row = cursor.fetchone()
            if not row or row[0] is None or row[0] == '':
                return None, None
            raw = str(row[0]).strip()
            if not raw:
                return None, None
            try:
                return float(raw), raw
            except (TypeError, ValueError):
                return None, None
    except Exception as e:
        logger.error(f"Error reading last report time: {e}", exc_info=True)
        return None, None


def try_claim_report_period(old_raw_value, new_report_time):
    """
    Atomically update last_report_time only if it still equals old_raw_value.
    old_raw_value: exact string from DB (from get_last_report_time), or None for first run.
    Returns True if we claimed the period (this process should send the report), False otherwise.
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            if old_raw_value is None or old_raw_value == '':
                cursor.execute(
                    """
                    UPDATE agent_state SET value = ? WHERE key = 'last_report_time' AND (value = '' OR value IS NULL)
                    """,
                    (str(new_report_time),),
                )
            else:
                cursor.execute(
                    """
                    UPDATE agent_state SET value = ? WHERE key = 'last_report_time' AND value = ?
                    """,
                    (str(new_report_time), old_raw_value),
                )
            conn.commit()
            return cursor.rowcount == 1
    except Exception as e:
        logger.error(f"Error claiming report period: {e}", exc_info=True)
        return False


def set_last_report_time(timestamp):
    """Set last report time (unix timestamp) in agent_state."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO agent_state (key, value) VALUES ('last_report_time', ?)",
                (str(timestamp),),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting last report time: {e}", exc_info=True)
        return False


def try_record_posted_period(period_start_str, period_end_str):
    """
    Record that we are posting (or have posted) for this period.
    Returns True if we inserted (first to record) -> should post to Teams.
    Returns False if row already exists -> skip post (idempotent).
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO posted_periods (period_start, period_end) VALUES (?, ?)",
                (period_start_str, period_end_str),
            )
            conn.commit()
            return cursor.rowcount == 1
    except Exception as e:
        logger.error(f"Error recording posted period: {e}", exc_info=True)
        return False


def get_alert_count_total():
    """Return total number of alerts in the DB (for diagnostics)."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM alerts")
            return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Error counting alerts: {e}", exc_info=True)
        return 0


def get_alerts_in_period(period_start, period_end):
    """Get all alerts within a specific time period (by insert time, UTC)."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM alerts 
                WHERE alert_timestamp BETWEEN ? AND ?
                ORDER BY operation, alert_timestamp
            """, (period_start, period_end))
            rows = cursor.fetchall()
            
            # Convert rows to dicts and parse comma-separated pages; derive subject from raw_content when present
            from alert_parser import extract_subject_from_alert
            alerts = []
            for row in rows:
                alert_dict = dict(row)
                alert_dict['affected_pages'] = alert_dict['affected_pages'].split(',') if alert_dict.get('affected_pages') else []
                alert_dict.setdefault('related_logs_url', '')
                raw = alert_dict.get('raw_content') or ''
                alert_dict['subject'] = extract_subject_from_alert(raw) if raw else ''
                alerts.append(alert_dict)
            return alerts
    except Exception as e:
        logger.error(f"Error querying alerts: {e}", exc_info=True)
        return []


def get_previous_period_count(operation, service, period_start):
    """Get alert count from previous period for trend comparison."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT total_count FROM alert_periods
                WHERE operation = ? AND service = ? AND period_end <= ?
                ORDER BY period_end DESC
                LIMIT 1
            """, (operation, service, period_start))
            result = cursor.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error querying previous period: {e}", exc_info=True)
        return 0


def insert_alert_period(period_start, period_end, operation, service, 
                        alert_type, severity, total_count, total_occurrences,
                        affected_pages, status, trend_delta, trend_direction, 
                        previous_period_count, notes):
    """Insert aggregated alert period into database."""
    try:
        affected_pages_str = ','.join(affected_pages) if affected_pages else 'unknown'
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO alert_periods
                (period_start, period_end, operation, service, alert_type, 
                 severity, total_count, total_occurrences, affected_pages, 
                 status, trend_delta, trend_direction, previous_period_count, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (period_start, period_end, operation, service, alert_type,
                  severity, total_count, total_occurrences, affected_pages_str,
                  status, trend_delta, trend_direction, previous_period_count, notes))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error inserting alert period: {e}", exc_info=True)
        return False


def insert_page_correlation(operation, service, page):
    """Track which pages are affected by which alerts."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO page_correlations (operation, service, page, frequency)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(operation, service, page) 
                DO UPDATE SET frequency = frequency + 1, last_seen = CURRENT_TIMESTAMP
            """, (operation, service, page))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error inserting page correlation: {e}", exc_info=True)
        return False


def get_page_correlations(operation, service):
    """Get all pages affected by a specific operation."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT page, frequency FROM page_correlations
                WHERE operation = ? AND service = ?
                ORDER BY frequency DESC
            """, (operation, service))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error querying page correlations: {e}", exc_info=True)
        return []


def cleanup_old_records(retention_days):
    """Delete alerts older than retention period."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=retention_days)  # Use UTC
        cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')  # Match SQLite CURRENT_TIMESTAMP format
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM alerts WHERE alert_timestamp < ?
            """, (cutoff_str,))
            alerts_deleted = cursor.rowcount
            
            cursor.execute("""
                DELETE FROM alert_periods WHERE period_end < ?
            """, (cutoff_str,))
            periods_deleted = cursor.rowcount
            
            cursor.execute("""
                DELETE FROM posted_periods WHERE period_end < ?
            """, (cutoff_str,))
            
            conn.commit()
        
        if alerts_deleted > 0 or periods_deleted > 0:
            logger.info(f"Cleaned up {alerts_deleted} old alerts and {periods_deleted} old periods")
        return True
    except Exception as e:
        logger.error(f"Error cleaning up old records: {e}", exc_info=True)
        return False
