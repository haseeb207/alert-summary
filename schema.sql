-- SQLite Database Schema for Alert Aggregation & Trend Analysis

-- Store raw parsed alerts
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    service TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT,
    condition TEXT,
    occurrence_count INTEGER,
    time_window TEXT,
    affected_pages TEXT,
    status TEXT,
    related_logs_url TEXT,
    alert_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_name TEXT UNIQUE,
    raw_content TEXT
);

-- Store aggregated alerts per time period
CREATE TABLE IF NOT EXISTS alert_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    operation TEXT NOT NULL,
    service TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT,
    total_count INTEGER DEFAULT 0,
    total_occurrences INTEGER DEFAULT 0,
    affected_pages TEXT,
    status TEXT,
    trend_delta INTEGER DEFAULT 0,
    trend_direction TEXT,
    previous_period_count INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(period_start, period_end, operation, service)
);

-- Page correlation mapping (auto-populated from alerts)
CREATE TABLE IF NOT EXISTS page_correlations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    service TEXT NOT NULL,
    page TEXT NOT NULL,
    frequency INTEGER DEFAULT 1,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(operation, service, page)
);

-- Agent state (last report time) for single-report-per-period across restarts/processes
CREATE TABLE IF NOT EXISTS agent_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT OR IGNORE INTO agent_state (key, value) VALUES ('last_report_time', '');

-- Periods we have already posted to Teams (idempotent: only one post per period)
CREATE TABLE IF NOT EXISTS posted_periods (
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    PRIMARY KEY (period_start, period_end)
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_alerts_operation_timestamp 
    ON alerts(operation, alert_timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_periods_operation_period 
    ON alert_periods(operation, service, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_page_operation_service 
    ON page_correlations(operation, service);
