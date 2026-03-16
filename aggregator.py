"""
Alert Aggregator Module

Aggregates raw alerts into time-windowed summaries and calculates trends.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

import database

logger = logging.getLogger('datadog_agent')


def parse_period_string(period_str: str) -> timedelta:
    """Parse period string like '3h', '6h', '24h', '1d' to timedelta."""
    period_str = period_str.lower().strip()
    
    try:
        if period_str.endswith('h'):
            hours = int(period_str[:-1])
            return timedelta(hours=hours)
        elif period_str.endswith('d'):
            days = int(period_str[:-1])
            return timedelta(days=days)
        elif period_str.endswith('m'):
            minutes = int(period_str[:-1])
            return timedelta(minutes=minutes)
        else:
            logger.warning(f"Invalid period format: {period_str}, defaulting to 3 hours")
            return timedelta(hours=3)
    except ValueError:
        logger.warning(f"Could not parse period: {period_str}, defaulting to 3 hours")
        return timedelta(hours=3)


def format_period_label(period_str: str) -> str:
    """Turn period string (e.g. '1h', '30m') into human-readable label for summaries."""
    s = period_str.lower().strip()
    try:
        if s.endswith('m'):
            n = int(s[:-1])
            return f"{n} minute{'s' if n != 1 else ''}"
        if s.endswith('h'):
            n = int(s[:-1])
            return f"{n} hour{'s' if n != 1 else ''}"
        if s.endswith('d'):
            n = int(s[:-1])
            return f"{n} day{'s' if n != 1 else ''}"
    except ValueError:
        pass
    return "1 hour"


def _format_time_12h(dt_utc: datetime, tz_name: str) -> str:
    """Format a UTC datetime in the given timezone as 12-hour am/pm (e.g. '9:00 pm')."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo('UTC'))
    local = dt_utc.astimezone(ZoneInfo(tz_name))
    h = local.hour
    m = local.minute
    if h == 0:
        hour_12 = 12
        am_pm = 'am'
    elif h < 12:
        hour_12 = h
        am_pm = 'am'
    elif h == 12:
        hour_12 = 12
        am_pm = 'pm'
    else:
        hour_12 = h - 12
        am_pm = 'pm'
    return f"{hour_12}:{m:02d} {am_pm}"


def format_period_in_timezones(period_start: datetime, period_end: datetime) -> List[str]:
    """
    Format the agent's reporting window in EST, CST, and UTC (12-hour am/pm).
    period_start and period_end are in UTC.
    Returns a list of lines, e.g.:
      ['EST: 9:00 pm to 11:00 pm', 'CST: 8:00 pm to 10:00 pm', 'UTC: 2:00 am to 4:00 am']
    """
    lines = []
    for label, tz_name in [('EST', 'America/New_York'), ('CST', 'America/Chicago'), ('UTC', 'UTC')]:
        start_str = _format_time_12h(period_start, tz_name)
        end_str = _format_time_12h(period_end, tz_name)
        lines.append(f"{label}: {start_str} to {end_str}")
    return lines


def get_period_boundaries(period_delta: timedelta) -> Tuple[datetime, datetime]:
    """
    Get start and end times for current aggregation period.
    Aligns to period boundaries (e.g., 0-3h, 3-6h, 6-9h).
    Uses UTC time to match SQLite CURRENT_TIMESTAMP.
    """
    now = datetime.utcnow()  # Use UTC to match SQLite timestamps
    period_seconds = int(period_delta.total_seconds())
    
    # Get seconds since midnight UTC
    seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
    
    # Calculate which period we're in
    periods_since_midnight = seconds_since_midnight // period_seconds
    period_start_seconds = periods_since_midnight * period_seconds
    
    # Build the start datetime
    period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = period_start + timedelta(seconds=period_start_seconds)
    period_end = period_start + period_delta
    
    return period_start, period_end


def aggregate_alerts_by_period(alerts: List[Dict], period_delta: timedelta,
                               group_by_page: bool = False) -> Dict[Tuple, Dict]:
    """
    Group alerts by operation/service (and optionally by page) within time periods.

    When group_by_page is False, returns dict keyed by (operation, service);
    Page(s) column will show comma-separated list of affected pages.
    When group_by_page is True, returns dict keyed by (operation, service, page);
    table will have one row per (alert, page) with a single page in the Page(s) column.
    """
    aggregated = {}

    for alert in alerts:
        if alert.get('status') == 'RECOVERED':
            logger.debug(f"Skipping recovered alert: {alert['operation']}")
            continue

        op, svc = alert['operation'], alert['service']
        pages = list(alert.get('affected_pages') or [])
        if not pages or (pages == ['unknown']):
            pages = ['unknown']

        if group_by_page:
            for page in pages:
                key = (op, svc, page)
                if key not in aggregated:
                    aggregated[key] = {
                        'operation': op,
                        'service': svc,
                        'alert_type': alert['alert_type'],
                        'severity': alert['severity'],
                        'count': 0,
                        'total_occurrences': 0,
                        'affected_pages': {page},
                        'all_conditions': [],
                        'all_alerts': []
                    }
                aggregated[key]['count'] += 1
                aggregated[key]['total_occurrences'] += alert.get('occurrence_count', 0)
                aggregated[key]['affected_pages'].add(page)
                aggregated[key]['all_conditions'].append(alert.get('condition', 'Unknown'))
                aggregated[key]['all_alerts'].append(alert)
        else:
            key = (op, svc)
            if key not in aggregated:
                aggregated[key] = {
                    'operation': op,
                    'service': svc,
                    'alert_type': alert['alert_type'],
                    'severity': alert['severity'],
                    'count': 0,
                    'total_occurrences': 0,
                    'affected_pages': set(),
                    'all_conditions': [],
                    'all_alerts': []
                }
            aggregated[key]['count'] += 1
            aggregated[key]['total_occurrences'] += alert.get('occurrence_count', 0)
            aggregated[key]['affected_pages'].update(pages)
            aggregated[key]['all_conditions'].append(alert.get('condition', 'Unknown'))
            aggregated[key]['all_alerts'].append(alert)

    return aggregated


def calculate_trend(current_count: int, previous_count: int) -> Tuple[int, str]:
    """
    Calculate trend change and direction.
    
    Returns (delta, direction) where direction is IMPROVING, STABLE, or DEGRADING
    """
    if previous_count == 0:
        delta = 0
        direction = 'NEW'
    else:
        delta = current_count - previous_count
        if delta < -5:  # 5+ fewer alerts
            direction = 'IMPROVING'
        elif delta > 5:  # 5+ more alerts
            direction = 'DEGRADING'
        else:
            direction = 'STABLE'
    
    return delta, direction


def generate_simple_period_summary(period_start: datetime, period_end: datetime,
                                   aggregated_alerts: Dict[Tuple, Dict],
                                   period_label: str = "1 hour",
                                   include_related_logs: bool = True) -> str:
    """
    Simple summary: time window on separate lines, then a table of alert name | page(s) | count | related logs.
    When include_related_logs is False, the Related logs column is omitted (e.g. for test output).
    """
    if not aggregated_alerts:
        return "✅ **No active alerts in this period**\n"
    
    lines = []
    lines.append(f"**Summary for last {period_label}**")
    for line in format_period_in_timezones(period_start, period_end):
        lines.append(line)
    lines.append("")
    # Table: Alert name | Page(s) | Subject | Number of alerts | [Related logs]
    if include_related_logs:
        lines.append("| Alert name | Page(s) | Subject | Number of alerts | Related logs |")
        lines.append("| --- | --- | --- | --- | --- |")
    else:
        lines.append("| Alert name | Page(s) | Subject | Number of alerts |")
        lines.append("| --- | --- | --- | --- |")
    for key, data in sorted(aggregated_alerts.items()):
        if len(key) == 3:
            operation, service, page = key
            pages = [page]
        else:
            operation, service = key
            pages = sorted(list(data.get('affected_pages', set()) or []))
        count = data['count']
        pages_cell = ", ".join(p for p in pages if p and p != 'unknown') or "—"
        subject = ""
        for a in data.get('all_alerts', []):
            sub = (a.get('subject') or "").strip()
            if sub:
                subject = sub[:100] + ("…" if len(sub) > 100 else "")
                break
        subject_cell = (subject or "—").replace('|', '\\|').replace('\n', ' ')
        if (operation or '').strip() in ('', 'Unknown'):
            if pages and pages != ['unknown']:
                op_display = f"Unknown (path: {pages[0]})"
            else:
                short_svc = (service or 'unknown')[:30] + ('…' if len(service or '') > 30 else '')
                op_display = f"Unknown ({short_svc})"
        else:
            op_display = operation or 'Unknown'
        op_cell = op_display.replace('|', '\\|')
        pages_cell_safe = pages_cell.replace('|', '\\|')
        if include_related_logs:
            related_url = ''
            for a in data.get('all_alerts', []):
                u = a.get('related_logs_url') or ''
                if u and u.strip():
                    related_url = u.strip()
                    break
            related_cell = f"[Link]({related_url})" if related_url else "—"
            lines.append(f"| {op_cell} | {pages_cell_safe} | {subject_cell} | {count} | {related_cell} |")
        else:
            lines.append(f"| {op_cell} | {pages_cell_safe} | {subject_cell} | {count} |")
    return "\n".join(lines)


def generate_period_summary(period_start: datetime, period_end: datetime,
                           aggregated_alerts: Dict[Tuple, Dict],
                           period_label: str = "1 hour",
                           use_simple: bool = False) -> str:
    """Generate markdown summary for aggregated alerts in a period.
    If use_simple is True, returns simple summary (time lines + table). Otherwise full summary.
    Only triggered (non-recovered) alerts are included in aggregated_alerts.
    """
    if use_simple:
        return generate_simple_period_summary(period_start, period_end, aggregated_alerts, period_label)

    # Full summary expects one row per (operation, service); merge if table was grouped by page
    for_full = _merge_by_operation_service(aggregated_alerts)
    if not for_full:
        return "✅ **No active alerts in this period**\n"

    summary_lines = []
    summary_lines.append(f"**Summary for last {period_label}**")
    for line in format_period_in_timezones(period_start, period_end):
        summary_lines.append(line)
    summary_lines.append("")
    summary_lines.append("*Only triggered (non-recovered) alerts are included.*\n")

    for (operation, service), data in sorted(for_full.items()):
        previous_count = database.get_previous_period_count(operation, service, period_start)
        delta, direction = calculate_trend(data['count'], previous_count)
        
        # Build page string
        pages = sorted(list(data['affected_pages']))
        pages_str = ', '.join(pages) if pages and pages != ['unknown'] else 'unknown'
        
        # Trend indicator
        trend_icon = {
            'IMPROVING': '✅',
            'DEGRADING': '⚠️',
            'STABLE': '➡️',
            'NEW': '🆕'
        }.get(direction, '❓')
        
        trend_text = f"{delta:+d}" if direction != 'NEW' else "First detected"
        
        summary_lines.append(f"🚨 **{data['severity']} - {operation}** {trend_icon}")
        summary_lines.append(f"* **In this period:** {data['count']} {operation} alerts occurred ({trend_text})")
        summary_lines.append(f"* **Service:** `{service}`")
        summary_lines.append(f"* **Total slow requests reported:** {data['total_occurrences']}")
        summary_lines.append(f"* **Affected Pages:** {pages_str}")
        
        # Show threshold/condition if available
        if data['all_conditions'] and data['all_conditions'][0] != 'Unknown Condition':
            conditions_str = ', '.join(set(data['all_conditions']))
            summary_lines.append(f"* **Threshold:** {conditions_str}")
        
        # Show monitor window (per alert) - Datadog's window, not the agent's period
        time_windows = set(alert.get('time_window', 'Unknown') for alert in data['all_alerts'])
        if time_windows and time_windows != {'Unknown'}:
            windows_str = ', '.join(sorted(time_windows))
            summary_lines.append(f"* **Monitor window (per alert):** {windows_str}")
        
        summary_lines.append(f"* **Trend:** {direction.capitalize()}")
        summary_lines.append("")
    
    summary_lines.append("---")
    return "\n".join(summary_lines)


def _merge_by_operation_service(aggregated_alerts: Dict[Tuple, Dict]) -> Dict[Tuple, Dict]:
    """If keys are (op, svc, page), merge to (op, svc) for saving. Otherwise return as-is."""
    if not aggregated_alerts:
        return aggregated_alerts
    first_key = next(iter(aggregated_alerts))
    if len(first_key) != 3:
        return aggregated_alerts
    merged = {}
    for (op, svc, page), data in aggregated_alerts.items():
        key = (op, svc)
        if key not in merged:
            merged[key] = {
                'operation': op,
                'service': svc,
                'alert_type': data['alert_type'],
                'severity': data['severity'],
                'count': 0,
                'total_occurrences': 0,
                'affected_pages': set(),
                'all_conditions': data.get('all_conditions', []),
                'all_alerts': []
            }
        merged[key]['count'] += data['count']
        merged[key]['total_occurrences'] += data.get('total_occurrences', 0)
        merged[key]['affected_pages'].update(data.get('affected_pages', set()))
        merged[key]['all_alerts'].extend(data.get('all_alerts', []))
    return merged


def save_aggregated_period(period_start: datetime, period_end: datetime,
                          aggregated_alerts: Dict[Tuple, Dict]):
    """Save aggregated alerts to database. Merges by (operation, service) when table was grouped by page."""
    to_save = _merge_by_operation_service(aggregated_alerts)
    for (operation, service), data in to_save.items():
        previous_count = database.get_previous_period_count(operation, service, period_start)
        delta, direction = calculate_trend(data['count'], previous_count)

        pages = sorted(list(data.get('affected_pages', set()) or []))

        database.insert_alert_period(
            period_start=period_start.strftime('%Y-%m-%d %H:%M:%S'),
            period_end=period_end.strftime('%Y-%m-%d %H:%M:%S'),
            operation=operation,
            service=service,
            alert_type=data['alert_type'],
            severity=data['severity'],
            total_count=data['count'],
            total_occurrences=data['total_occurrences'],
            affected_pages=pages,
            status='ACTIVE',
            trend_delta=delta,
            trend_direction=direction,
            previous_period_count=previous_count,
            notes=f"Detected in {data['count']} alert files"
        )

        for page in pages:
            if page != 'unknown':
                database.insert_page_correlation(operation, service, page)

        logger.info(f"Saved aggregated period: {operation} ({direction})")
