# Datadog Alert Aggregation Agent

A Python daemon that monitors a directory for Datadog alert `.txt` files, parses metadata, aggregates alerts by elapsed-time periods (e.g. hourly), stores them in SQLite, and posts formatted summaries to Microsoft Teams.

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

- **Python**: 3.9 or higher
- **OneDrive** (or any folder): Directory containing Datadog alert `.txt` files
- **Microsoft Teams**: Incoming webhook URL for posting summaries

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
| **Parser** | `alert_parser.parse_alert()` | Extracts operation, service, severity, condition, count, time_window, affected_pages |
| **Aggregation** | `PeriodAggregator.check_and_report()` | Elapsed-time windows; aggregates and posts every N seconds |
| **Teams Posting** | `send_to_teams()` | Office 365 Message Card, 3 retries with exponential backoff |
| **Database** | `database` module | SQLite: alerts, alert_periods, page_correlations; cleanup by retention |
| **Logging** | `setup_logging()` | Rotating file (10MB, 5 backups) + console |

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
| `watchdog` | Filesystem monitoring |
| `requests` | Teams webhook HTTP |
| `python-dotenv` | Load `.env` |

## 📄 License

Internal use only - Visionet Systems Inc.

---

**Last Updated**: March 2026
# alert-summary
