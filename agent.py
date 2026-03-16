#!/usr/bin/env python3
"""
Datadog Alert Monitoring Agent with Aggregation & Trend Analysis

Monitors a directory for Datadog alert .txt files, parses them, aggregates by
time periods, calculates trends, and posts period summaries to Teams.
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# Import new aggregation modules
import database
import alert_parser
import aggregator

# Ensure all agent processes use the same DB (avoid duplicate reports from multiple instances)
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
database.DB_FILE = os.path.join(_AGENT_DIR, 'alerts.db')


# ============================================================================
# CONFIGURATION
# ============================================================================

# Load environment variables
load_dotenv()

# Environment variables with defaults
TEAMS_WEBHOOK_URL = os.getenv('TEAMS_WEBHOOK_URL')
_watch_dir_raw = os.getenv('WATCH_DIR')
if not _watch_dir_raw:
    print("ERROR: WATCH_DIR is not set in .env — copy .env.example to .env and configure it.")
    sys.exit(1)
WATCH_DIR = os.path.expanduser(_watch_dir_raw)
DRY_RUN = os.getenv('DRY_RUN', 'false').lower() == 'true'

# Aggregation configuration
AGGREGATION_PERIOD_STR = os.getenv('AGGREGATION_PERIOD', '1h')
HISTORY_RETENTION_DAYS = int(os.getenv('HISTORY_RETENTION_DAYS', '7'))

# Summary mode: 'full' (detailed) or 'simple' (time lines + table with alert name, count, related logs)
SUMMARY_MODE = (os.getenv('SUMMARY_MODE', 'full') or 'full').lower()
# When simple mode: if true, table has one row per (alert, page); if false, one row per alert with comma-separated pages
SUMMARY_TABLE_GROUP_BY_PAGE = (os.getenv('SUMMARY_TABLE_GROUP_BY_PAGE', 'false') or 'false').lower() == 'true'

# Retry configuration for Teams webhook
WEBHOOK_MAX_RETRIES = 3
WEBHOOK_RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds

# File stabilization configuration
FILE_STABILITY_CHECK_INTERVAL = 0.5  # seconds
FILE_STABILITY_THRESHOLD = 1.0  # seconds of no size change


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """Configure structured logging to both console and rotating file."""
    log_dir = Path(_AGENT_DIR) / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # Create logger
    logger = logging.getLogger('datadog_agent')
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # Rotating file handler (10MB max, 5 backups)
    file_handler = RotatingFileHandler(
        log_dir / 'agent.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


logger = setup_logging()


# ============================================================================
# FILE STABILIZATION
# ============================================================================

FILE_STABILITY_TIMEOUT = 60  # seconds — give up if file never stabilises


def wait_for_file_stability(filepath, check_interval=FILE_STABILITY_CHECK_INTERVAL,
                            stability_threshold=FILE_STABILITY_THRESHOLD,
                            timeout=FILE_STABILITY_TIMEOUT):
    """
    Wait until file size remains unchanged for the stability threshold.
    Ensures OneDrive has completely synced the file before processing.
    Returns False if the file disappears or fails to stabilise within *timeout* seconds.
    """
    logger.info(f"Waiting for file stability: {Path(filepath).name}")
    
    try:
        last_size = -1
        stable_since = None
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            if not os.path.exists(filepath):
                logger.warning(f"File disappeared during stabilization check: {filepath}")
                return False
            
            current_size = os.path.getsize(filepath)
            
            if current_size == last_size:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= stability_threshold:
                    logger.info(f"File stabilized at {current_size} bytes: {Path(filepath).name}")
                    return True
            else:
                logger.debug(f"File size changed: {last_size} -> {current_size} bytes")
                last_size = current_size
                stable_since = None
            
            time.sleep(check_interval)
        
        logger.warning(f"File did not stabilise within {timeout}s: {Path(filepath).name}")
        return False
    
    except Exception as e:
        logger.error(f"Error during file stabilization check: {e}", exc_info=True)
        return False


def open_file_with_retry(filepath, max_retries=5, initial_delay=0.5):
    """
    Open a file with retry logic for permission errors.
    Handles OneDrive lock delays by retrying with exponential backoff.
    
    Returns (success, file_content) tuple.
    """
    filename = Path(filepath).name
    delay = initial_delay
    
    for attempt in range(1, max_retries + 1):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"Successfully opened file on attempt {attempt}: {filename}")
            return True, content
        
        except PermissionError as e:
            if attempt < max_retries:
                logger.warning(f"Permission denied (attempt {attempt}/{max_retries}), retrying in {delay:.1f}s: {filename}")
                time.sleep(delay)
                delay *= 2
            else:
                logger.error(f"Failed to open file after {max_retries} attempts: {filename} - {e}")
                return False, None
        
        except Exception as e:
            logger.error(f"Error opening file {filename}: {e}", exc_info=True)
            return False, None
    
    return False, None


# ============================================================================
# ALERT PROCESSING
# ============================================================================

def process_alert_file(filepath):
    """
    Read and parse a single alert file.
    
    Returns parsed alert dict or None on error.
    """
    try:
        # Wait for file to stabilize
        if not wait_for_file_stability(filepath):
            logger.error(f"File stability check failed: {filepath}")
            return None
        
        # Read file content with retry logic for OneDrive locks
        logger.info(f"Reading alert file: {filepath}")
        success, alert_text = open_file_with_retry(filepath)
        
        if not success:
            logger.error(f"Failed to read file after retries: {filepath}")
            return None
        
        logger.info(f"Read {len(alert_text)} characters from {filepath}")
        
        # Parse alert
        filename = Path(filepath).name
        parsed = alert_parser.parse_alert(alert_text, filename)
        
        # Store in database
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
            file_name=filename,
            raw_content=alert_text,
            related_logs_url=parsed.get('related_logs_url', '')
        )
        
        logger.info(f"Stored alert in database: {parsed['operation']} ({parsed['severity']})")
        return parsed
    
    except Exception as e:
        logger.error(f"Error processing alert file {filepath}: {e}", exc_info=True)
        return None


# ============================================================================
# TEAMS WEBHOOK
# ============================================================================

def send_to_teams(summary, max_retries=WEBHOOK_MAX_RETRIES, retry_delays=WEBHOOK_RETRY_DELAYS):
    """
    Post summary to Microsoft Teams via incoming webhook with retry logic.
    If DRY_RUN is enabled, logs the summary without posting.
    """
    if not TEAMS_WEBHOOK_URL:
        logger.error("TEAMS_WEBHOOK_URL not configured in .env")
        return False
    
    # Teams webhook payload format (Office 365 Message Card)
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0078D4",
        "summary": "Datadog Alert Summary",
        "sections": [
            {
                "text": summary
            }
        ]
    }
    
    if DRY_RUN:
        logger.info("=" * 80)
        logger.info("🧪 DRY RUN MODE - Would post the following to Teams:")
        logger.info("=" * 80)
        logger.info(summary)
        logger.info("=" * 80)
        return True
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Posting to Teams (attempt {attempt + 1}/{max_retries})")
            
            response = requests.post(
                TEAMS_WEBHOOK_URL,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            # Accept any 2xx as success (Workflows webhooks return 202 Accepted, not 200)
            if 200 <= response.status_code < 300:
                logger.info(f"Successfully posted to Teams (HTTP {response.status_code})")
                return True
            else:
                logger.warning(f"Teams webhook returned status {response.status_code}: {response.text}")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error posting to Teams: {e}")
        
        # Retry with exponential backoff (if not last attempt)
        if attempt < max_retries - 1:
            delay = retry_delays[attempt] if attempt < len(retry_delays) else retry_delays[-1]
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
    
    logger.error(f"Failed to post to Teams after {max_retries} attempts")
    return False


# ============================================================================
# WATCHDOG EVENT HANDLER
# ============================================================================

PROCESSED_FILES_MAX = 5000


class DatadogAlertHandler(FileSystemEventHandler):
    """Handle file system events for Datadog alert .txt files."""
    
    def __init__(self):
        super().__init__()
        self.processed_files = set()
    
    def _handle_alert_file(self, filepath):
        """Common handler for both created and moved-in .txt files."""
        if not filepath.endswith('.txt'):
            logger.debug(f"Ignoring non-.txt file: {filepath}")
            return
        
        path = Path(filepath)
        if path.parent.name in ('archive', 'failed'):
            logger.debug(f"Ignoring file in {path.parent.name}/: {filepath}")
            return
        
        if filepath in self.processed_files:
            return
        
        logger.info(f"New alert file detected: {path.name}")
        self.processed_files.add(filepath)
        
        # Prevent unbounded memory growth
        if len(self.processed_files) > PROCESSED_FILES_MAX:
            to_remove = list(self.processed_files)[:PROCESSED_FILES_MAX // 2]
            self.processed_files.difference_update(to_remove)
        
        parsed = process_alert_file(filepath)
        
        if parsed:
            logger.info(f"Successfully processed: {path.name}")
            try:
                if path.exists():
                    archive_dir = path.parent / 'archive'
                    archive_dir.mkdir(exist_ok=True)
                    archive_path = archive_dir / path.name
                    path.rename(archive_path)
                    logger.info(f"Archived to: {archive_path}")
                else:
                    logger.warning(f"File no longer exists, skipping archive: {path.name}")
            except FileExistsError:
                logger.warning(f"File already archived, skipping: {path.name}")
            except Exception as e:
                logger.error(f"Error archiving file: {e}")
        else:
            logger.warning(f"Failed to process (will not archive): {path.name}")
    
    def on_created(self, event):
        """Handle new file creation events."""
        if event.is_directory:
            return
        self._handle_alert_file(event.src_path)
    
    def on_moved(self, event):
        """Handle file move/rename events (e.g. OneDrive renames temp files into place)."""
        if event.is_directory:
            return
        self._handle_alert_file(event.dest_path)


# ============================================================================
# PERIOD AGGREGATION & REPORTING
# ============================================================================

class PeriodAggregator:
    """Manages alert aggregation by time period. Uses DB-persisted last_report_time to prevent duplicate reports."""
    
    def __init__(self, period_str: str):
        self.period_str = period_str
        self.period_delta = aggregator.parse_period_string(period_str)
    
    def check_and_report(self):
        """
        Check if elapsed time since last report >= period_delta, and report if so.
        Uses DB-persisted last_report_time and atomic claim so only one report is sent per period
        (avoids duplicates from multiple processes or 59th/minute double-send).
        Returns True if a report was generated, False otherwise.
        """
        current_time = time.time()
        period_seconds = self.period_delta.total_seconds()
        last_report_time, last_report_raw = database.get_last_report_time()
        
        # First run: set last_report_time to one period ago so the first report includes
        # alerts from the last hour (e.g. from startup scan). Otherwise they'd fall in a gap.
        if last_report_time is None:
            initial_time = current_time - period_seconds
            if not database.try_claim_report_period(None, initial_time):
                return False
            logger.info(
                f"Aggregator initialized (last_report_time = 1 period ago). "
                f"Will report every {period_seconds:.0f}s; first report in ~{period_seconds:.0f}s."
            )
            return False
        
        # Check if enough time has elapsed
        elapsed_seconds = current_time - last_report_time
        if elapsed_seconds < period_seconds:
            return False
        
        # Atomic claim: use exact raw value from DB so WHERE clause matches (avoids float->str mismatch)
        if not database.try_claim_report_period(last_report_raw, current_time):
            logger.debug("Another process claimed this period, skipping report")
            return False
        
        # We claimed: build period and report (last_report_time already updated in DB)
        period_start = datetime.utcfromtimestamp(last_report_time)
        period_end = datetime.utcfromtimestamp(current_time)
        
        logger.info(f"Period elapsed ({elapsed_seconds:.1f}s >= {period_seconds:.1f}s). Checking for alerts (UTC): {period_start.strftime('%Y-%m-%d %H:%M:%S')} - {period_end.strftime('%Y-%m-%d %H:%M:%S')}")
        
        alerts = database.get_alerts_in_period(
            period_start.strftime('%Y-%m-%d %H:%M:%S'),
            period_end.strftime('%Y-%m-%d %H:%M:%S')
        )
        
        if not alerts:
            total_in_db = database.get_alert_count_total()
            logger.info(
                f"No alerts in current period (UTC {period_start.strftime('%Y-%m-%d %H:%M:%S')} - {period_end.strftime('%H:%M:%S')}). "
                f"Total alerts in DB: {total_in_db}. "
                f"Alerts are counted by when they were processed/inserted. "
                f"If you expect alerts, check that files in the watch dir were processed (look for 'Stored alert' or errors above)."
            )
            return False
        
        logger.info(f"Found {len(alerts)} alerts in current period")
        
        group_by_page = (SUMMARY_MODE == 'simple' and SUMMARY_TABLE_GROUP_BY_PAGE)
        aggregated = aggregator.aggregate_alerts_by_period(alerts, self.period_delta, group_by_page=group_by_page)
        if not aggregated:
            logger.info("No active alerts to aggregate")
            return False
        
        period_label = aggregator.format_period_label(self.period_str)
        use_simple = (SUMMARY_MODE == 'simple')
        summary = aggregator.generate_period_summary(
            period_start, period_end, aggregated,
            period_label=period_label,
            use_simple=use_simple
        )
        
        # Idempotent post: only one message per period (guards against any duplicate claim/process)
        period_start_str = period_start.strftime('%Y-%m-%d %H:%M:%S')
        period_end_str = period_end.strftime('%Y-%m-%d %H:%M:%S')
        if not database.try_record_posted_period(period_start_str, period_end_str):
            logger.warning(f"Already posted for period {period_start_str} - {period_end_str}, skipping Teams post")
            return True
        
        print("\n" + "="*80)
        print("PERIOD ALERT SUMMARY")
        print("="*80)
        print(summary)
        print("="*80 + "\n")
        
        aggregator.save_aggregated_period(period_start, period_end, aggregated)
        send_to_teams(summary)
        
        logger.info(f"Report posted for period: {period_start_str} - {period_end_str}")
        return True


# ============================================================================
# STARTUP VALIDATION
# ============================================================================

def validate_startup():
    """Validate environment and dependencies before starting the agent."""
    logger.info("Running startup validation checks...")
    
    # Check if .env is loaded
    if not TEAMS_WEBHOOK_URL:
        logger.error("TEAMS_WEBHOOK_URL not set in .env file")
        logger.error("Please copy .env.example to .env and configure it")
        return False
    
    # Check if watch directory exists
    watch_path = Path(WATCH_DIR)
    if not watch_path.exists():
        logger.error(f"Watch directory does not exist: {WATCH_DIR}")
        logger.error("Please create the directory or update WATCH_DIR in .env")
        return False
    
    if not watch_path.is_dir():
        logger.error(f"Watch path is not a directory: {WATCH_DIR}")
        return False
    
    logger.info(f"Watch directory OK: {WATCH_DIR}")
    
    # Initialize database
    if not database.init_database():
        logger.error("Failed to initialize database")
        return False
    
    logger.info("All startup validation checks passed ✓")
    return True


# ============================================================================
# STARTUP FILE SCANNING
# ============================================================================

def scan_for_existing_files():
    """Scan for and process any existing alert files at startup."""
    logger.info(f"Scanning for existing alert files in {WATCH_DIR}")
    
    watch_path = Path(WATCH_DIR)
    try:
        txt_files = list(watch_path.glob('*.txt'))
    except OSError as e:
        logger.error(
            f"Cannot list watch directory (check permissions / Full Disk Access): {e}. "
            f"Path: {watch_path}"
        )
        return 0
    
    if not txt_files:
        logger.info(
            "No existing alert files found. "
            "If you expect files here, ensure the app running the agent (e.g. Terminal) has Full Disk Access in System Settings → Privacy & Security."
        )
        return 0
    
    logger.info(f"Found {len(txt_files)} existing alert files")
    processed_count = 0
    
    for file_path in txt_files:
        logger.info(f"Processing existing file: {file_path.name}")
        
        # Process the alert file
        parsed = process_alert_file(str(file_path))
        
        if parsed:
            logger.info(f"Successfully processed: {file_path.name}")
            processed_count += 1
            
            # Archive the file
            try:
                if file_path.exists():
                    archive_dir = file_path.parent / 'archive'
                    archive_dir.mkdir(exist_ok=True)
                    archive_path = archive_dir / file_path.name
                    file_path.rename(archive_path)
                    logger.info(f"Archived to: {archive_path.name}")
                else:
                    logger.warning(f"File no longer exists, skipping archive: {file_path.name}")
            except FileExistsError:
                logger.warning(f"File already archived, skipping: {file_path.name}")
            except Exception as e:
                logger.error(f"Error archiving file {file_path.name}: {e}")
        else:
            logger.warning(f"Failed to process: {file_path.name}")
            
            # Move to failed directory
            try:
                failed_dir = file_path.parent / 'failed'
                failed_dir.mkdir(exist_ok=True)
                failed_path = failed_dir / file_path.name
                file_path.rename(failed_path)
                logger.info(f"Moved to failed: {file_path.name}")
            except Exception as e:
                logger.error(f"Error moving failed file {file_path.name}: {e}")
    
    logger.info(f"Startup scan complete: processed {processed_count}/{len(txt_files)} files")
    return processed_count


# ============================================================================
# MAIN FUNCTION & SIGNAL HANDLING
# ============================================================================

# Global observer for graceful shutdown
observer = None
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals (SIGINT, SIGTERM) gracefully."""
    global shutdown_requested
    
    signal_name = 'SIGINT' if signum == signal.SIGINT else 'SIGTERM'
    logger.info(f"Received {signal_name}, initiating graceful shutdown...")
    
    shutdown_requested = True
    
    if observer:
        observer.stop()


# ============================================================================
# SINGLE-INSTANCE LOCK (PID FILE)
# ============================================================================

PID_FILE = Path(_AGENT_DIR) / 'agent.pid'


def acquire_pid_lock():
    """Ensure only one agent process runs. Uses exclusive create so only one process can create the file."""
    def try_create():
        try:
            with open(PID_FILE, 'x') as f:
                f.write(str(os.getpid()))
            return True
        except FileExistsError:
            return False

    if try_create():
        return True
    # File exists: check if owner is still running
    try:
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
    except (ValueError, OSError):
        try:
            PID_FILE.unlink()
        except OSError:
            pass
        return try_create()
    try:
        os.kill(old_pid, 0)
        logger.error(f"Another agent is already running (PID {old_pid}). Exiting.")
        return False
    except ProcessLookupError:
        pass
    except PermissionError:
        pass
    try:
        PID_FILE.unlink()
    except OSError:
        pass
    if try_create():
        return True
    logger.error("Could not acquire pid lock (another process may have taken it). Exiting.")
    return False


def release_pid_lock():
    """Remove pid file on exit."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except OSError:
        pass


def delete_processed_archive_files(watch_dir: str) -> int:
    """
    Delete all .txt files in watch_dir/archive/ and watch_dir/failed/.
    These are already processed; no retention - remove them to free disk space.
    Returns the number of files deleted.
    """
    root = Path(watch_dir)
    deleted = 0
    for subdir in ('archive', 'failed'):
        dir_path = root / subdir
        if not dir_path.is_dir():
            continue
        try:
            for f in dir_path.glob('*.txt'):
                try:
                    f.unlink()
                    deleted += 1
                except OSError as e:
                    logger.warning(f"Could not delete {f.name}: {e}")
        except OSError as e:
            logger.warning(f"Could not list {dir_path}: {e}")
    if deleted > 0:
        logger.info(f"Deleted {deleted} processed .txt file(s) from archive/failed")
    return deleted


def main():
    """Main entry point for the Datadog alert monitoring agent."""
    global observer
    
    logger.info("="*80)
    logger.info("Datadog Alert Monitoring Agent with Aggregation & Trend Analysis")
    logger.info("="*80)
    logger.info(f"Configuration:")
    logger.info(f"  Watch Directory: {WATCH_DIR}")
    logger.info(f"  Aggregation Period: {AGGREGATION_PERIOD_STR}")
    logger.info(f"  History Retention: {HISTORY_RETENTION_DAYS} days")
    logger.info(f"  Summary Mode: {SUMMARY_MODE} (full=detailed, simple=table)")
    logger.info(f"  Teams Webhook: {'configured' if TEAMS_WEBHOOK_URL else 'NOT CONFIGURED'}")
    if DRY_RUN:
        logger.info(f"  ⚠️  DRY RUN MODE ENABLED - No messages will be posted to Teams")
    logger.info("="*80)
    
    # Run startup validation
    if not validate_startup():
        logger.error("Startup validation failed. Exiting.")
        sys.exit(1)
    
    # Single-instance lock: prevent duplicate reports from multiple agent processes
    if not acquire_pid_lock():
        sys.exit(1)
    
    # Scan for and process existing files at startup
    scan_for_existing_files()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create period aggregator
    period_agg = PeriodAggregator(AGGREGATION_PERIOD_STR)
    
    # Create and configure watchdog observer
    event_handler = DatadogAlertHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    
    # Start monitoring
    observer.start()
    logger.info(f"Started monitoring: {WATCH_DIR}")
    logger.info(f"Alerts will be aggregated by period and posted to Teams")
    logger.info("Press Ctrl+C to stop")
    
    try:
        # Main loop: check for period boundaries and report
        check_interval = 60  # Check every minute
        cleanup_interval_seconds = 3600 * 6  # Every 6 hours
        next_cleanup_time = time.time() + cleanup_interval_seconds
        
        while not shutdown_requested:
            period_agg.check_and_report()
            
            # Periodically clean up old records and delete processed .txt files in archive/failed
            if time.time() >= next_cleanup_time:
                database.cleanup_old_records(HISTORY_RETENTION_DAYS)
                delete_processed_archive_files(WATCH_DIR)
                next_cleanup_time = time.time() + cleanup_interval_seconds
            
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    
    finally:
        # Clean shutdown
        release_pid_lock()
        logger.info("Stopping observer...")
        observer.stop()
        observer.join()
        logger.info("Agent stopped gracefully")


if __name__ == '__main__':
    main()
