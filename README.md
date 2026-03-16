# Datadog Alert Aggregation Agent

A Python daemon that monitors a directory for Datadog alert `.txt` files, parses metadata, aggregates alerts by elapsed-time periods (e.g. hourly), stores them in SQLite, and posts formatted summaries to Microsoft Teams.

## Overview

This agent is designed for teams that receive Datadog alerts as email (or exported `.txt` files, e.g. via OneDrive). It watches a configurable folder, parses each new alert file to extract **operation**, **service**, **severity**, **threshold**, **time window**, **occurrence count**, and **affected pages**, then stores them in a local SQLite database. On a configurable interval (e.g. every 1 hour), it aggregates alerts into period summaries, computes trends vs. the previous period, and posts a formatted report to a Microsoft Teams channel via an incoming webhook. Processed files are moved to `archive/`; parse failures go to `failed/` for inspection.

## 🎯 Features

- **Automated File Monitoring**: Uses `watchdog` to detect new `.txt` files in real-time
- **OneDrive Sync Handling**: File stabilization checks ensure files are fully synced before processing
- **Structured Parsing**: Extracts API name, severity, threshold, time window, occurrence count, affected pages
- **Elapsed-Time Aggregation**: Reports every N seconds (e.g. 3600s) since last report, not calendar boundaries
- **SQLite Storage**: Alerts and aggregated periods with trend tracking and page correlations
- **Microsoft Teams Integration**: Posts period summaries via incoming webhooks with retry logic
- **Robust Error Handling**: Exponential backoff retries, failed file segregation, defensive archiving
- **Graceful Shutdown**: Signal handlers ensure clean shutdown without data loss
- **Archive Management**: Processed files moved to `archive/`; failed parses to `failed/`

## 📋 Requirements

- **Python**: 3.9 or higher (uses `zoneinfo` for timezone-aware period labels)
- **Watch directory**: Folder containing Datadog alert `.txt` files (e.g. OneDrive-synced)
- **Microsoft Teams**: Incoming webhook URL for posting period summaries

## 🚀 Quick Start

### 1. Clone & Setup

```bash
cd /path/to/email-agent

# Create virtual environment
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
nano .env
```

**Required `.env` configuration:**

```env
# Get this from Teams: Channel → Connectors → Incoming Webhook
TEAMS_WEBHOOK_URL=https://your-org.webhook.office.com/webhookb2/your-webhook-url

# Directory to watch for Datadog alert .txt files (e.g. OneDrive-synced folder)
WATCH_DIR=~/path/to/datadog-alert-emails

# Aggregation period: 30m, 1h, 2h, 6h, 24h, 1d (default: 1h)
AGGREGATION_PERIOD=1h

# How long to keep alert history (days)
HISTORY_RETENTION_DAYS=7

# Summary mode: full (detailed per-alert breakdown) or simple (time lines + table: alert name, page(s), count, related logs)
SUMMARY_MODE=full

# When using simple mode: if true, table has one row per (alert, page); if false, one row per alert with comma-separated pages
SUMMARY_TABLE_GROUP_BY_PAGE=false

# Set to true to log summaries without posting to Teams
DRY_RUN=false
```

### 3. Create Watch Directory

```bash
mkdir -p "$(eval echo $WATCH_DIR)"
mkdir -p "$(eval echo $WATCH_DIR)/archive"
mkdir -p "$(eval echo $WATCH_DIR)/failed"
```

### 4. Run the Agent

```bash
python agent.py
```

You should see:

```
================================================================================
Datadog Alert Monitoring Agent with Aggregation & Trend Analysis
================================================================================
Configuration:
  Watch Directory: /path/to/datadog-alert-emails
  Aggregation Period: 1h
  History Retention: 7 days
  Teams Webhook: configured
================================================================================
...
Aggregator initialized. Will report every 3600.0 seconds
Started monitoring: /path/to/datadog-alert-emails
Press Ctrl+C to stop
```

## ⚙️ Configuration Reference

All settings are read from `.env` (copy from `.env.example`). Every option is listed below.

| Variable | Description | Default / Example |
|:---------|:------------|:-----------------|
| **TEAMS_WEBHOOK_URL** | Microsoft Teams incoming webhook URL (Channel → Connectors → Incoming Webhook) | Required; no default |
| **WATCH_DIR** | Directory to watch for Datadog alert `.txt` files (e.g. OneDrive-synced folder). Supports `~` for home. | Required |
| **AGGREGATION_PERIOD** | How often to aggregate and post a period summary. Elapsed-time since last report, not calendar boundaries. | `1h`; also `30m`, `2h`, `6h`, `24h`, `1d` |
| **HISTORY_RETENTION_DAYS** | Days of alert/period history to keep in SQLite; older records are deleted on cleanup. | `7` |
| **SUMMARY_MODE** | Format of the period summary posted to Teams: `full` (detailed per-alert breakdown) or `simple` (time lines + compact table). | `full` |
| **SUMMARY_TABLE_GROUP_BY_PAGE** | Only applies when `SUMMARY_MODE=simple`. If `true`, table has one row per (alert, page); if `false`, one row per alert with comma-separated pages. | `false` |
| **DRY_RUN** | If `true`, summaries are logged but not posted to Teams. Use for testing. | `false` |

### Summary modes: full vs simple

- **Full mode** (`SUMMARY_MODE=full`): Each aggregated (operation, service) gets a detailed breakdown—counts, trend vs previous period, affected pages, and per-alert details. Best for thorough review.
- **Simple mode** (`SUMMARY_MODE=simple`): Shorter report with period time lines (in configured timezones) and a single table: alert name, affected page(s), count, and related logs link. Less verbose for high-volume channels.
  - **SUMMARY_TABLE_GROUP_BY_PAGE**: In simple mode, set to `true` for one table row per (alert, page), or `false` for one row per alert with pages in a comma-separated list.

## 🏗️ Architecture

### Processing Pipeline

```
New .txt file detected in watch directory
    ↓
File stabilization (poll size until stable for 1s)
    ↓
Read content → parse_alert() (operation, service, severity, threshold, count, time window, pages)
    ↓
Insert into SQLite (alerts table)
    ↓
Move file to archive/ (or failed/ on parse error)
    ↓
Main loop every 60s: if elapsed time since last report >= AGGREGATION_PERIOD
    ↓
Query alerts in period (UTC) → aggregate by (operation, service) → generate markdown summary
    ↓
POST summary to Teams webhook & save aggregated period to DB
```

### Directory Structure

```
watch_dir/
├── alert_2026-03-11_P3.txt    # New alert (processed then archived)
├── archive/                    # Successfully processed
└── failed/                     # Parse failures
```

### Key Components

| Component | File/Function | Purpose |
|:----------|:--------------|:--------|
| **File Monitor** | `DatadogAlertHandler` | Watchdog handler for `.txt` creation; ignores archive/ and failed/ |
| **Stabilization** | `wait_for_file_stability()` | Waits for file size to be stable before reading |
| **Parser** | `alert_parser.parse_alert()` | Extracts operation, service, severity, condition, count, time_window, affected_pages, related_logs_url |
| **Aggregation** | `PeriodAggregator.check_and_report()` | Elapsed-time windows; aggregates and posts every N seconds |
| **Teams Posting** | `send_to_teams()` | Office 365 Message Card, 3 retries with exponential backoff |
| **Database** | `database` module | SQLite: alerts, alert_periods, page_correlations, agent_state, posted_periods; cleanup by retention |
| **Logging** | `setup_logging()` | Rotating file (10MB, 5 backups) + console |

### Database Schema

The SQLite database (`alerts.db`) is created from `schema.sql` and includes:

| Table | Purpose |
|:------|:--------|
| **alerts** | Raw parsed alerts: operation, service, alert_type, severity, condition, occurrence_count, time_window, affected_pages, status, related_logs_url, file_name, raw_content |
| **alert_periods** | Aggregated counts per (period_start, period_end, operation, service) with trend_delta and trend_direction |
| **page_correlations** | Maps (operation, service) to affected pages with frequency and last_seen |
| **agent_state** | Key-value store (e.g. `last_report_time`) for elapsed-time reporting across restarts |
| **posted_periods** | Tracks (period_start, period_end) already posted to Teams for idempotent posting |

### Project Structure

| Path | Description |
|:-----|:------------|
| `agent.py` | Main entry point: file watcher, stabilization, parsing, aggregation loop, Teams posting, signal handling, PID lock |
| `alert_parser.py` | Parses raw alert text: subject, pages, threshold, time window, count, related logs URL |
| `aggregator.py` | Period boundaries, aggregation by (operation, service), trend calculation, markdown summary generation (full/simple) |
| `database.py` | DB init, insert/query alerts and periods, page correlations, retention cleanup, last report time and posted-period tracking |
| `schema.sql` | SQLite table and index definitions |
| `test_with_review.sh` | Runs agent in DRY_RUN with timeout for quick validation |
| `test_summary_from_dirs.py` | Builds summary from directories of `.txt` files (no watcher) |
| `test_with_archive.py` | Tests processing with archive/failed layout |
| `diagnose_unknown_alerts.py` | Inspects raw content of alerts for debugging parse issues |
| `logs/` | Rotating `agent.log` (10MB, 5 backups) |
| `alerts.db` | SQLite DB (created at runtime) |
| `agent.pid` | PID file for single-instance lock |

## 🧪 Testing

### Elapsed-time logic

```bash
python test_elapsed_time.py
```

### Integration test (no Teams post)

```bash
rm -f alerts.db
python test_integration.py
```

### File stabilization

Create a test file in the watch directory and watch logs:

```bash
echo "Subject: [P3] High Duration Alert: getCart" > "$WATCH_DIR/test_alert.txt"
tail -f logs/agent.log
```

### Dry-run test script

Run the agent in DRY_RUN for a short time without posting to Teams:

```bash
./test_with_review.sh
```

Output is written to `test_output.log`; the script cleans the DB and PID file before running.

## 📊 Logging

- **Location**: `logs/agent.log`
- **Rotation**: 10MB max, 5 backups
- **View live**: `tail -f logs/agent.log`

## 🔧 Troubleshooting

### "TEAMS_WEBHOOK_URL not configured"

Set `TEAMS_WEBHOOK_URL` in `.env` (from Teams channel → Connectors → Incoming Webhook).

### "Watch directory does not exist"

Create the path in `WATCH_DIR` or fix the path in `.env`.

### No Teams messages

1. Ensure `DRY_RUN=false` in `.env`
2. Aggregation is elapsed-time: first report is ~1 hour after agent start (for `AGGREGATION_PERIOD=1h`)
3. Check logs for "Period elapsed" and "Report posted"

### Files not detected

1. Use `.txt` extension; files in `archive/` or `failed/` are ignored
2. Check `tail -f logs/agent.log` for errors

### "Operation not permitted" or "Failed to open file" (OneDrive / CloudStorage)

If the watch directory is under OneDrive (e.g. `Library/CloudStorage/OneDrive-...`) and the agent logs **Operation not permitted** or **Failed to open file after 5 attempts**:

1. **Run the agent from a process that has access**  
   Run from Terminal after `cd`-ing into the project (or into the watch dir) so it uses the same permissions you have in the Finder.

2. **macOS privacy**  
   Grant **Full Disk Access** or **Files and Folders** access to the app that runs the agent:  
   **System Settings → Privacy & Security → Full Disk Access** (or **Files and Folders**) → add **Terminal** (or your IDE / the Python binary).

3. **OneDrive Files On-Demand**  
   Ensure the alert files are **available locally** (not cloud-only). In OneDrive settings, you can choose "Always keep on this device" for the alert folder.

4. **Unreadable files are moved to `failed/`**  
   After 5 failed read attempts, the agent moves the file into a `failed/` subfolder under the watch directory so it doesn’t block processing. You can inspect or re-run from there once permissions are fixed.

## 🚀 Production

### Run in background (macOS)

```bash
nohup ./venv/bin/python agent.py >> logs/agent.log 2>&1 &
```

### Run as LaunchAgent (macOS)

Use a plist with `ProgramArguments`, `WorkingDirectory`, and `StandardOutPath`/`StandardErrorPath` pointing at this repo and `agent.py`.

## 📦 Dependencies

| Package | Purpose |
|:--------|:--------|
| `watchdog` | Filesystem monitoring for new `.txt` files |
| `requests` | HTTP POST to Teams incoming webhook |
| `python-dotenv` | Load `.env` configuration |

Standard library: `sqlite3`, `logging`, `pathlib`, `signal`, `zoneinfo` (Python 3.9+).

## 📄 License

Internal use only - Visionet Systems Inc.

**Last Updated**: March 2026