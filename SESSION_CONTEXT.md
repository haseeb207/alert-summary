# Datadog Alert Aggregation Agent - Session Context

**Last Updated**: March 11, 2026 (Updated 11:00 AM)  
**Status**: ✅ LIVE IN PRODUCTION - Elapsed-time aggregation running

---

## 📋 Project Summary

Building a Python agent that monitors Datadog alert emails, parses metadata, aggregates by time periods (hourly), and posts summaries to Microsoft Teams. The agent groups alerts by API operation/service and displays comprehensive metadata in each Teams message.

### Key Features
- 📁 Watches OneDrive directory for new alert `.txt` files
- 🔍 Extracts: API name, threshold, time window, occurrence count, affected pages
- 📊 Aggregates by hourly periods (customizable)
- 💾 Stores in SQLite database
- 📤 Posts formatted summaries to Teams webhook
- 🔄 Auto-archives processed files
- 🧪 DRY_RUN mode for safe testing

---

## ✅ Completed Work (This Session)

### 1. MAJOR FIX: Elapsed-Time Based Aggregation ✅ IMPLEMENTED

**Problem Identified:**
- Old code used calendar-aligned periods (0:00, 1:00, 2:00, etc.)
- This meant alerts only aggregated at fixed wall-clock hours
- User reported NO Teams messages from 6 AM - 10:57 AM despite agent running
- Root cause: Calendar boundaries are arbitrary and don't respect elapsed time

**Solution Implemented:**
```python
# OLD (calendar-based):
period_start, period_end = aggregator.get_period_boundaries(self.period_delta)
if self.last_reported_period == period_start:
    return False

# NEW (elapsed-time based):
current_time = time.time()
elapsed_seconds = current_time - self.last_report_time

if elapsed_seconds < period_seconds:
    return False  # Not enough time elapsed yet

# Calculate boundaries from actual elapsed time
period_start = datetime.fromtimestamp(self.last_report_time)
period_end = datetime.fromtimestamp(current_time)
```

**What Changed:**
- Agent now tracks `last_report_time` instead of `last_reported_period`
- Compares elapsed seconds against period delta (3600s for 1 hour)
- Reports after **X elapsed time**, not at calendar boundaries
- Log message now shows: `"Period elapsed (3661.5s >= 3600.0s)"`

**Verification:**
- Created `test_elapsed_time.py` to validate logic
- ✅ Elapsed time tracking working correctly
- ✅ Fresh period starts after each report
- ✅ No duplicate reports in same period

### 2. Fixed File Archiving Error Handling ✅ IMPLEMENTED

**Problem:**
```
ERROR - Error archiving file: [Errno 2] No such file or directory
```

**Solution:**
- Added `path.exists()` check before archiving
- Handle `FileExistsError` if file already archived
- Auto-create archive directory with `mkdir(exist_ok=True)`
- Log warnings instead of errors for graceful degradation

**Code Changes:**
```python
# Check if file exists before attempting move
if path.exists():
    archive_dir.mkdir(exist_ok=True)
    path.rename(archive_path)
else:
    logger.warning(f"File no longer exists, skipping archive: {path.name}")

# Handle file already at destination
except FileExistsError:
    logger.warning(f"File already archived, skipping: {path.name}")
```

### 3. Enabled Teams Posting in Production ✅ IMPLEMENTED

**Problem:**
- Agent had `DRY_RUN=true` in `.env` (test mode)
- No Teams messages being posted despite agent running

**Solution:**
- Changed `.env` from `DRY_RUN=true` to `DRY_RUN=false`
- Agent now posts real Teams messages instead of logging

**Current Status:**
```
✅ Teams Webhook: configured
✅ DRY_RUN: false (Teams posting ENABLED)
✅ Database: alerts.db initialized
✅ File Monitoring: ACTIVE
✅ Elapsed-time Aggregation: ACTIVE (reports every 3600 seconds)
✅ Agent PID: 7300+ (Running)
```

### 4. Core Extraction Functions (alert_parser.py) - Previously Completed

#### extract_threshold_from_alert()
- Extracts threshold/condition that triggered alert
- Patterns: `"Duration Threshold: >500ms (0.5 seconds)"`, `"Threshold: 1.5"`, `"Increased: 1.042"`
- Returns: String representation of threshold

#### extract_time_window_from_alert()
- Extracts time window for the alert
- Patterns: `"Time Window: Last 1 hour"`, `"Last 2 hour"`, `"Last 1 day"`
- Returns: `"Last 1 hour"`, `"Last 2 hour"`, etc.

#### extract_count_from_alert() **[FIXED in Previous Session]**
- Extracts occurrence count from alerts
- **Regex Pattern**: `r'(?:^|-\s+)?Count:\s*([\d.]+)'` with MULTILINE flag
- Handles `"- Count: 10.0"` format with leading dash
- Returns: Float value (10.0, 11.0, 28.0, etc.)

#### extract_pages_from_alert() **[Enhanced in Previous Session]**
- Extracts affected API paths/pages
- Primary: Extracts explicit `"Path:"` field
- Fallback: Pattern matching for `/cart`, `/checkout`, etc.
- Returns: List of paths (`['cart']`, `['applepay-express']`, etc.)

---

## 🐛 Critical Issues Fixed (This Session)

### Issue #1: No Teams Messages Since 6 AM ✅ FIXED

**Symptoms:**
- Agent running but no Teams messages posted from 6 AM - 10:57 AM
- Last message posted at 9 PM previous night
- Agent logs showing "Period boundary crossed" repeatedly

**Root Cause Analysis:**
1. Agent was using OLD calendar-based aggregation code
2. Code still in memory from previous startup (process not restarted)
3. Additionally, `DRY_RUN=true` prevented Teams posting even if reports were triggered

**Multi-Part Solution:**
1. ✅ **Replaced calendar-based logic with elapsed-time logic** in `check_and_report()`
2. ✅ **Restarted agent process** to load new code
3. ✅ **Changed DRY_RUN from true to false** to enable Teams posting
4. ✅ **Reset database** to start fresh period tracking

**Verification:**
```
Agent started: 10:59:08 AM
Log message: "Aggregator initialized. Will report every 3600.0 seconds"
First report will post: ~11:59:08 AM (1 hour after initialization)
```

### Issue #2: File Archiving Errors ✅ FIXED

**Symptoms:**
```
ERROR - Error archiving file: [Errno 2] No such file or directory
```

**Root Cause:**
- File disappeared from filesystem between processing and archiving
- Could happen if OneDrive syncs file away or external deletion
- No defensive checks before attempting `path.rename()`

**Solution:**
- Added `if path.exists()` check before archiving
- Catch `FileExistsError` if already moved
- Log as warning, not error (non-fatal issue)
- Auto-create archive directory

### Issue #3: Duplicate Teams Messages ✅ FIXED (Previous Session)

**Original Problem:**
- Same message posted 3 times in one period
- `last_reported_period` check insufficient

**Solution:**
- Added `last_report_time` tracking
- Now checks both: period start AND time elapsed
- Prevents same-period duplicates

---

## 🏗️ Architecture Overview

### Current Live Setup (March 11, 2026, 11:00 AM)

**Agent Process Status:**
- ✅ Running with venv Python: `./venv/bin/python agent.py`
- ✅ Started: 10:59:08 AM with fresh database (alerts.db)
- ✅ Using elapsed-time aggregation (3600 second periods)
- ✅ Teams posting enabled (DRY_RUN=false)
- ✅ File monitoring active on OneDrive directory

**Key Processes:**
- Watchdog file monitor: Scanning for new `.txt` files
- 60-second check loop: Evaluates period elapsed time
- Aggregation trigger: When elapsed >= 3600 seconds
- Teams webhook: Posts aggregated summaries

### File Structure
```
/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent/
├── agent.py                          # Main orchestration + watchdog handler
│                                      # ✅ Updated with elapsed-time logic
├── alert_parser.py                   # 4 extraction functions + parse_alert()
├── aggregator.py                     # Period bucketing + summary generation
├── database.py                       # SQLite schema + CRUD operations
├── .env                              # Configuration
│                                      # ✅ DRY_RUN=false (Teams enabled)
├── alerts.db                         # SQLite database (fresh at 10:59:08 AM)
├── logs/
│   └── agent.log                     # Rotating logs (10MB max, 5 backups)
│                                      # ✅ Shows elapsed-time logic
├── test_elapsed_time.py              # ✅ NEW: Tests elapsed-time logic
└── venv/                             # Python virtual environment
```

### Data Flow Diagram (Updated for Elapsed-Time Logic)
```
Alert .txt file arrives
    ↓
wait_for_file_stability() - Wait for OneDrive sync complete
    ↓
process_alert_file() - Read file content
    ↓
parse_alert() - Extract 6 fields:
  • operation (API name)
  • service
  • condition (threshold)
  • occurrence_count (from "- Count: X.X")
  • time_window (from "Time Window: ...")
  • affected_pages (from "Path: ...")
    ↓
database.insert_alert() - Store in SQLite
    ↓
File processed → Move to /archive/ (with error handling)
    ↓
Main loop: check_and_report() every 60 seconds
    ↓
⭐ NEW LOGIC: Check elapsed time since last report
    ↓
If (current_time - last_report_time) >= period_delta:
  • Calculate period_start from last_report_time
  • Calculate period_end from current_time
  • get_alerts_in_period() - Query alerts for this elapsed period
  • aggregate_alerts_by_period() - Group by (operation, service)
  • generate_period_summary() - Format Teams markdown
  • send_to_teams() - Post to webhook (ENABLED)
  • Update last_report_time = current_time
    ↓
Fresh period starts - next report in ~3600 seconds
```

### Key Classes

**DatadogAlertHandler (watchdog event handler)**
- Listens for new `.txt` files
- Filters out archive/ and failed/ subdirectories
- Calls process_alert_file() on each new alert
- ✅ Enhanced: Defensive file archiving with existence checks

**PeriodAggregator**
- ✅ **NEW**: Uses elapsed-time tracking instead of calendar boundaries
- Tracks `last_report_time` (unix timestamp of last report)
- Checks: `elapsed_seconds = current_time - last_report_time`
- Reports when: `elapsed_seconds >= period_seconds` (3600 for 1 hour)
- Updates `last_report_time = current_time` after each report

---

## ⚙️ Configuration

### .env File (Current Production Settings)
```bash
TEAMS_WEBHOOK_URL=https://...  # ✅ Configured
WATCH_DIR=/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails  # ✅ Active
AGGREGATION_PERIOD=1h          # ✅ 1 hour (3600 seconds)
HISTORY_RETENTION_DAYS=7
DRY_RUN=false                  # ✅ CHANGED FROM true - Teams posting ENABLED
OLLAMA_BASE_URL=http://localhost:11434
```

### How Elapsed-Time Aggregation Works

**Example Timeline (1-hour period):**
```
10:59:08 AM - Agent starts, initializes last_report_time
10:59:08 AM - "Aggregator initialized. Will report every 3600.0 seconds"
11:00 AM   - Check 1: elapsed_time = 52s < 3600s → No report yet
11:30 AM   - Check 2: elapsed_time = 1852s < 3600s → No report yet  
11:59 AM   - Check 3: elapsed_time = 3551s < 3600s → No report yet
11:59:09AM - Check 4: elapsed_time = 3601s >= 3600s → ✅ REPORT TRIGGERED
           - Aggregates all alerts collected from 10:59:08 AM - 11:59:09 AM
           - Posts to Teams
           - Sets: last_report_time = 11:59:09 AM
           - Next report will be at ~12:59:09 PM
```

### Valid Aggregation Periods
```
'30m'  → 1800 seconds   (reports every 30 minutes)
'1h'   → 3600 seconds   (reports every 1 hour) ✅ CURRENT
'2h'   → 7200 seconds   (reports every 2 hours)
'6h'   → 21600 seconds  (reports every 6 hours)
'24h'  → 86400 seconds  (reports every 24 hours)
'1d'   → 86400 seconds  (same as 24h)
```

### How to Change Period
```bash
# Without restarting (via environment variable):
AGGREGATION_PERIOD=2h ./venv/bin/python agent.py

# Or edit agent.py line 43:
AGGREGATION_PERIOD_STR = os.getenv('AGGREGATION_PERIOD', '1h')
```

---

## 🧪 Testing & Verification

### Testing Elapsed-Time Logic
```bash
cd /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent
python3 test_elapsed_time.py
```

**Expected Output:**
```
✓ Initialized at [timestamp] - next report in 2.0 seconds
✓ Elapsed: 0.51s < 2.0s - No report
✓ Elapsed: 2.51s >= 2.0s - REPORT TRIGGERED
✓ Elapsed: 0.50s < 2.0s - No report (fresh period)
✅ ELAPSED TIME LOGIC VERIFIED!
```

### Quick Integration Test (Non-Destructive)
Tests extraction + aggregation with 8 test files, does not post to Teams.
```bash
cd /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent
rm -f alerts.db
/usr/bin/python3 test_integration.py
```

### Production Monitoring (Current)
```bash
# Monitor live logs
tail -f /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent/logs/agent.log

# Check agent process exists
pgrep -f "agent.py"

# Count alerts in database
sqlite3 alerts.db "SELECT COUNT(*) as total_alerts FROM alerts;"

# See alerts by API
sqlite3 alerts.db "SELECT operation, COUNT(*) FROM alerts GROUP BY operation;"
```

---

## 📊 Sample Output (Expected Format on Teams)

```
📊 **Alert Summary: 2026-03-11 10:59:08 - 2026-03-11 11:59:08**

🚨 **P3 - removeCartLines** 🆕
* **Service:** `buy-www.mattressfirm-com.vercel.app`
* **Alert Count:** 3 alerts occurred (First detected)
* **Total Occurrences:** 28
* **Affected Pages:** cart, removecart
* **Threshold:** >1500ms (1.5 seconds)
* **Time Window:** Last 1 hour
* **Trend:** New

🚨 **P3 - GetAddressFromZipCode** 🆕
* **Service:** `buy-www.mattressfirm-com.vercel.app`
* **Alert Count:** 2 alerts occurred (First detected)
* **Total Occurrences:** 14
* **Affected Pages:** cart
* **Threshold:** >500ms (0.5 seconds)
* **Time Window:** Last 1 hour
* **Trend:** New
```

---

## 📍 Important Paths

| Purpose | Path |
|---------|------|
| Watch Directory | `/Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails/` |
| Project Root | `/Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent/` |
| Database (runtime) | `alerts.db` |
| Logs (runtime) | `logs/agent.log` |
| Processed Files Archive | `{WATCH_DIR}/archive/` |
| Failed Files | `{WATCH_DIR}/failed/` |
| Test Alert Files | 97 files available in watch directory |

---

## 🔍 Debug Commands

When something isn't working, use these commands:

```bash
# Check if agent process is running
pgrep -af "agent.py"
ps aux | grep "agent.py" | grep -v grep

# Verify agent started correctly
tail -30 /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent/logs/agent.log

# Check configuration (Teams webhook, DRY_RUN status)
grep -E "Teams Webhook|DRY RUN|configured" logs/agent.log | tail -3

# See if alerts are being collected
sqlite3 alerts.db "SELECT COUNT(*) FROM alerts;"

# List all API operations being tracked
sqlite3 alerts.db "SELECT DISTINCT operation FROM alerts ORDER BY operation;"

# Count alerts per operation
sqlite3 alerts.db "SELECT operation, COUNT(*) as count FROM alerts GROUP BY operation ORDER BY count DESC;"

# Check files in archive (processed files)
ls /Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails/archive/ | wc -l

# Restore files from archive if needed (fresh start)
cd /Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails
[[ -d archive ]] && mv archive/*.txt . 2>/dev/null

# Clean everything and start fresh
cd /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent
rm -f alerts.db logs/*.log

# Check Python syntax
./venv/bin/python -m py_compile agent.py alert_parser.py aggregator.py database.py
```

---

## 🎯 Next Steps (For Next Session)

1. ✅ **Verify fixes work** - Run `test_integration.py` and confirm occurrence counts are correct
2. ✅ **Test DRY_RUN mode** - Run with `DRY_RUN=true` and verify Teams message format
3. ✅ **Production deployment** - Run full `python agent.py` and monitor `logs/agent.log`
4. 📋 **Monitor real alerts** - Watch for incoming alert emails and verify proper aggregation
5. 🔧 **Fine-tune if needed**:
   - Adjust AGGREGATION_PERIOD if needed
   - Add alert filtering if too many alerts
   - Modify summary format if Teams display issues
6. 📱 **Enable continuous monitoring** - Consider running agent in background via systemd/launchd

---

## 🎯 Quick Start for Next Session

**Check Agent Status:**
```bash
cd /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent

# Verify running
pgrep -f "agent.py" && echo "✅ Agent running" || echo "❌ Agent stopped"

# Check latest logs
tail -5 logs/agent.log
```

**If Agent Stopped, Restart:**
```bash
# Kill old processes
pkill -f "agent.py"

# Start fresh
cd /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent
nohup ./venv/bin/python agent.py >> logs/agent.log 2>&1 &

# Verify startup
sleep 3 && tail -10 logs/agent.log | grep -E "initialized|Teams"
```

**If Teams Messages Not Showing:**
```bash
# Check DRY_RUN setting
grep "^DRY_RUN=" .env

# Should be: DRY_RUN=false

# If it's true, change it:
sed -i '' 's/DRY_RUN=.*/DRY_RUN=false/' .env

# Restart agent
pkill -f "agent.py"
sleep 2
nohup ./venv/bin/python agent.py >> logs/agent.log 2>&1 &
```

**Monitor for Reports:**
```bash
# Watch logs until report posts (check every 10 seconds)
while true; do 
  grep "Report posted" logs/agent.log | tail -1
  sleep 10
done
```

---

## ✨ Latest Changes Summary (This Session)

| Item | Change | Files Modified | Status |
|------|--------|-----------------|--------|
| **MAJOR: Aggregation Logic** | Switched from calendar-based (0:00, 1:00, etc.) to elapsed-time based (3600s intervals) | agent.py | ✅ LIVE |
| Elapsed-time tracking | Now uses `time.time()` and `last_report_time` instead of calendar boundaries | agent.py (lines 315-385) | ✅ LIVE |
| File archiving errors | Added defensive checks: `path.exists()`, `FileExistsError` handling, auto-mkdir | agent.py (lines 293-307, 450-473) | ✅ LIVE |
| Teams posting | Changed `DRY_RUN=false` in `.env` file | .env | ✅ LIVE |
| Period elapsed logging | Updated log format to show: `"Period elapsed (3661.5s >= 3600.0s)"` | agent.py (line 338) | ✅ LIVE |
| Database | Fresh `alerts.db` created at agent restart (10:59:08 AM) | alerts.db | ✅ LIVE |
| Test file | Created `test_elapsed_time.py` to validate elapsed-time logic | test_elapsed_time.py | ✅ VERIFIED |

---

## ⚠️ Important Notes for Next Session

### Current Agent Status (10:59:08 AM start)
```
✅ Elapsed-time aggregation: ACTIVE
✅ Teams posting: ENABLED (DRY_RUN=false)
✅ File monitoring: ACTIVE
✅ Database: Fresh (alerts.db)
✅ First report will post: ~11:59:08 AM
```

### Critical Implementation Details

1. **Elapsed-Time vs Calendar-Based**
   - ❌ OLD: "Period boundary crossed at 10:00, 11:00, 12:00 (calendar hours)"
   - ✅ NEW: "Period elapsed: 1 hour since last report"
   - This ensures rhythmic hourly reporting regardless of start time

2. **Period Tracking Variables**
   - `last_report_time`: Unix timestamp of last successful report
   - `last_reported_period`: No longer used (kept for backward compat only)
   - Initialize on first run: `if self.last_report_time is None`

3. **Report Timing**
   - Check every 60 seconds: `time.sleep(60)` in main loop
   - Compare: `elapsed_seconds = current_time - last_report_time`
   - Trigger: `if elapsed_seconds >= period_seconds:`
   - Update: `last_report_time = current_time` after posting

4. **File Archiving Safety**
   - Always check: `if path.exists():` before moving
   - Create directory: `archive_dir.mkdir(exist_ok=True)`
   - Catch: `except FileExistsError:` and log as warning
   - Never fail the entire alert processing on archive error

5. **Teams Posting Requirements**
   - `.env` must have: `DRY_RUN=false`
   - If `DRY_RUN=true`, messages only logged, not posted
   - Check logs for: "Teams Webhook: configured" (startup message)
   - If not seeing Teams messages: First check if agent is actually running

### If Agent Stops or Crashes

**Restart Procedure:**
```bash
# 1. Kill any old processes
pkill -f "agent.py"

# 2. Clean up old database (optional - keeps history if not cleaned)
cd /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent
rm -f alerts.db  # Remove if starting fresh period

# 3. Start fresh agent
nohup ./venv/bin/python agent.py >> logs/agent.log 2>&1 &

# 4. Verify it started
tail -20 logs/agent.log | grep -E "initialized|Teams|Configuration"

# 5. Verify no error restoring files from archive
cd /Users/haseeb.ahmedjaved/Library/CloudStorage/OneDrive-VisionetSystemsInc/Work/datadog-alert-emails
ls -la archive/ | wc -l  # Check how many files are there
```

### Monitoring Agent Health

**Live Log Monitoring:**
```bash
tail -f /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent/logs/agent.log
```

**Key Log Patterns to Watch For:**

✅ Good (Agent Working):
```
Aggregator initialized. Will report every 3600.0 seconds
Period elapsed (3661.5s >= 3600.0s). Checking for alerts
Found 5 alerts in current period
Report posted for period: 2026-03-11 10:59:08 - 2026-03-11 11:59:08
```

❌ Problems (Agent Stuck):
```
No alerts in current period  # If repeating every minute, files not being detected
Failed to process: filename  # Alert files with parsing errors
Error archiving file         # Consider restarting agent
```

⚠️ Warnings (Non-Fatal):
```
File no longer exists, skipping archive     # File deleted externally - OK
File already archived, skipping             # Already moved - OK
```

---

## 🚀 Next Steps for Next Session

1. **Monitor Teams Channel** - Verify messages posting hourly (11:59 AM, 12:59 PM, 1:59 PM, etc.)
2. **Check Alert Processing** - Verify alerts appear in Teams messages when files arrive
3. **Watch for Errors** - Review logs for any archiving or parsing errors
4. **Performance** - Agent uses minimal CPU/memory, should run 24/7
5. **Long-term** - Consider running via systemd or launchd for persistence across reboots

---

**Last Verified**: March 11, 2026, 11:00 AM - Agent running live in production ✅
