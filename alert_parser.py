"""
Alert Parser Module

Extracts structured information from raw Datadog alert email text.
"""

import re
import logging
from typing import Dict, List

logger = logging.getLogger('datadog_agent')


def extract_pages_from_alert(alert_text: str) -> List[str]:
    """
    Extract affected page/path names from alert content.
    Uses only the explicit 'Path: /...' field from Alert Details to avoid mixing in
    API/operation names (e.g. getCart, removeCartLines, paypal-express) which are not pages.
    """
    pages = set()
    
    # Only use explicit "Path:" field from Alert Details (e.g. "Path: /cart")
    path_match = re.search(r'Path:\s*(/\S+)', alert_text)
    if path_match:
        path = path_match.group(1).strip('/').strip()
        if path:
            pages.add(path.lower())
    
    # Optional: Datadog query style \@path:"/cart" (path only, not callname/API)
    for m in re.finditer(r'\\?@path:\s*["\']?(/[a-zA-Z0-9_-]+)', alert_text):
        p = m.group(1).strip('/').lower()
        if p:
            pages.add(p)
    
    return list(sorted(pages)) if pages else ["unknown"]


def extract_threshold_from_alert(alert_text: str) -> str:
    """
    Extract the threshold/condition that triggered the alert.
    Looks for patterns like: 'Duration Threshold: >500ms', 'Threshold: 1.5', etc.
    """
    # Look for explicit Duration Threshold
    threshold_match = re.search(r'Duration Threshold:\s*([^\n]+)', alert_text)
    if threshold_match:
        return threshold_match.group(1).strip()
    
    # Look for generic Threshold
    threshold_match = re.search(r'Threshold:\s*([^\n]+)', alert_text)
    if threshold_match:
        return threshold_match.group(1).strip()
    
    # Look for Increased pattern
    increased_match = re.search(r'Increased:\s*([^\n]+)', alert_text)
    if increased_match:
        return f"Increased {increased_match.group(1).strip()}"
    
    # Fallback regex for condition
    condition_match = re.search(r'(>[<=]?\s*[\d.]+\s*(?:ms|sec|s|%|m|seconds|milliseconds))', alert_text)
    if condition_match:
        return condition_match.group(1).strip()
    
    return 'Unknown Threshold'


def extract_time_window_from_alert(alert_text: str) -> str:
    """
    Extract the time window for the alert.
    Looks for 'Time Window: Last 2 hour' patterns.
    """
    # Look for explicit Time Window field
    window_match = re.search(r'Time Window:\s*([^\n]+)', alert_text)
    if window_match:
        return window_match.group(1).strip()
    
    # Fallback: Look for time patterns in text
    window_match = re.search(r'(?:last|in\s+the\s+last)\s+([\d\w\s]+?)(?:\b(?:hour|day|minute|second|week))', alert_text, re.IGNORECASE)
    if window_match:
        return f"Last {window_match.group(1).strip()}".strip()
    
    return 'Unknown'


def extract_subject_from_alert(alert_text: str) -> str:
    """
    Extract the email subject/title from the alert body.
    Typically appears at the top after the "outside the organization" disclaimer,
    e.g. "[P3] Warn: API Profiling - Cart - (Graphql API) High duration detected for removeCartLines"
    """
    lines = alert_text.splitlines()
    subject_lines = []
    # Skip disclaimer block (e.g. "⚠** This email... Think before clicking... **")
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith('⚠') or s.startswith('**') or 'outside the organization' in s or 'Think before' in s or 'clicking on links' in s.lower():
            i += 1
            continue
        # First line that looks like a subject: [P1-4], Warn:, Recovered:, API Profiling, etc.
        if re.match(r'^\[?(P[1-5]|Critical|Warn|High|Medium|Low)\]', s, re.I) or 'API Profiling' in s or 'Recovered:' in s or 'Triggered:' in s:
            break
        i += 1
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            break
        if s.startswith('🚨') or s.startswith('Alert Details') or s.startswith('http'):
            break
        subject_lines.append(s)
        i += 1
    return ' '.join(subject_lines).strip() if subject_lines else ''


def extract_related_logs_url(alert_text: str) -> str:
    """
    Extract the Related Logs URL from Datadog alert email.
    Looks for "Related Logs" followed by a line or same line containing [http(s)://...].
    Returns the first URL found (safelinks or direct), or empty string.
    """
    # "Related Logs" then optional newline/whitespace then bracket URL (capture until ])
    match = re.search(
        r'Related\s+Logs\s*\[(https?://[^\]]+)\]',
        alert_text,
        re.IGNORECASE | re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return ''


def extract_count_from_alert(alert_text: str) -> float:
    """
    Extract the occurrence count from the alert.
    Looks for 'Count: <number>' field (with or without leading dashes).
    """
    # Look for explicit Count field (handles "- Count: 10.0" format)
    count_match = re.search(r'(?:^|-\s+)?Count:\s*([\d.]+)', alert_text, re.MULTILINE)
    if count_match:
        try:
            return float(count_match.group(1))
        except ValueError:
            return 0.0
    
    # Fallback: Look for "More than N log events" pattern
    events_match = re.search(r'[Mm]ore than\s+(\d+)\s+(?:log\s+)?events?', alert_text)
    if events_match:
        try:
            return float(events_match.group(1))
        except ValueError:
            return 0.0
    
    return 0.0


def parse_alert(raw_alert_text: str, filename: str) -> Dict:
    """
    Parse raw alert email text and extract structured data.
    
    Returns dict with keys:
    - operation: API operation name (e.g., "removeCartLines")
    - service: Service name
    - alert_type: Type of alert (e.g., "High Duration", "Error Rate")
    - severity: P1, P2, P3, etc.
    - condition: Threshold that was exceeded
    - occurrence_count: Number of occurrences
    - time_window: Time window of the alert
    - affected_pages: List of affected pages
    - status: ACTIVE or RECOVERED
    """
    try:
        result = {
            'operation': 'Unknown',
            'service': 'Unknown Service',
            'alert_type': 'Unknown Alert',
            'severity': 'P3',
            'condition': extract_threshold_from_alert(raw_alert_text),
            'occurrence_count': int(extract_count_from_alert(raw_alert_text)),
            'time_window': extract_time_window_from_alert(raw_alert_text),
            'affected_pages': extract_pages_from_alert(raw_alert_text),
            'status': 'ACTIVE',
            'related_logs_url': extract_related_logs_url(raw_alert_text),
            'subject': extract_subject_from_alert(raw_alert_text),
            'filename': filename
        }
        
        # Extract severity level
        severity_match = re.search(r'\[(P[1-4]|Critical|High|Medium|Low|Warn)\]', raw_alert_text)
        if severity_match:
            result['severity'] = severity_match.group(1)
        
        # Check if it's a recovery/resolved alert (be strict to avoid false positives)
        # Look for explicit language like "Alert has recovered" or "Issue is resolved"
        # Avoid matching subject line patterns like "[P3] Recovered: API Profiling"
        recovery_patterns = [
            r'alert\s+(?:has\s+)?recovered',  # "alert has recovered" or "alert recovered"
            r'issue\s+(?:has\s+)?resolved',   # "issue has resolved" or "issue resolved"
            r'issue\s+(?:is\s+)?fixed',       # "issue is fixed"
            r'back\s+to\s+normal',            # "back to normal"
            r'recovery\s+complete',           # "recovery complete"
            r'alert\s+cleared',               # "alert cleared"
            r'resolved\s+on',                 # "Resolved on [date]"
        ]
        for pattern in recovery_patterns:
            if re.search(pattern, raw_alert_text, re.IGNORECASE):
                result['status'] = 'RECOVERED'
                break
        
        # Extract operation name (GraphQL, REST API, D365, or Affirm). Include optional parenthetical e.g. "(PayPal)".
        # Prefer Alert Details line "D365: GetCardPaymentAcceptPoint (PayPal)" so full name is preserved.
        _op_with_paren = r'(\w+(?:\s*\([^)]+\))?)'  # word chars, optional " (Something)"
        api_pattern = re.search(
            r'(?:GraphQL|REST\s*API|D365):\s*' + _op_with_paren,
            raw_alert_text, re.IGNORECASE
        )
        if api_pattern:
            result['operation'] = api_pattern.group(1).strip()
        else:
            # Affirm API: "Affirm: api/promos/v2/..." or "🚨 High Duration Alert: api/promos/v2/... Affirm API"
            affirm_match = re.search(r'Affirm:\s*([a-zA-Z0-9/_.-]+)', raw_alert_text)
            if affirm_match:
                op = affirm_match.group(1).strip()
                # Use last path segment if long (e.g. api/promos/v2/P6V0I5H0J3T2W0BD → Affirm promos)
                if '/' in op and len(op) > 25:
                    result['operation'] = 'Affirm-' + op.split('/')[-1][:20]
                else:
                    result['operation'] = op if len(op) <= 40 else 'Affirm-' + op.split('/')[-1]
            else:
                # Primary: "🚨 High Duration Alert: <name> <type> API" — allow optional (PayPal) etc.
                alert_title_match = re.search(
                    r'🚨\s+(?:High Duration|High Latency|Error Rate)\s+Alert:\s+' + _op_with_paren + r'\s+',
                    raw_alert_text
                )
                if alert_title_match:
                    result['operation'] = alert_title_match.group(1).strip()
        # SLO / Inventory style: "[P5] Triggered: ATPInventoryDynamic - P99" or "Recovered: ATPInventoryDynamic -"
        if result['operation'] == 'Unknown':
            slo_match = re.search(r'(?:Triggered|Recovered):\s*([A-Za-z0-9]+)\s*[-–]', raw_alert_text)
            if slo_match:
                result['operation'] = slo_match.group(1).strip()
        if result['operation'] == 'Unknown':
            # Commerce/ATP/MFIATPInventoryDynamic in URL or text
            commerce_op = re.search(r'Commerce/(?:ATP/)?([A-Za-z0-9]+)', raw_alert_text)
            if commerce_op:
                result['operation'] = commerce_op.group(1).strip()
        
        # "API Profiling Alert - X" (e.g. "API Profiling Alert - Apple Pay Endpoint Error Rate")
        if result['operation'] == 'Unknown':
            profiling_match = re.search(r'API\s+Profiling\s+Alert\s+[-–]\s+([A-Za-z][A-Za-z0-9\s]+?)(?:\s+Error\s+Rate|\s+High\s+Duration|$)', raw_alert_text)
            if profiling_match:
                result['operation'] = profiling_match.group(1).strip().replace(' ', '') or result['operation']
        
        # Commerce/OperationName (e.g. Commerce/GetAddressFromZipCode) — use the operation, not "Commerce"
        if result['operation'] == 'Unknown' or result['operation'] == 'Commerce':
            commerce_op = re.search(r'Commerce[/\s]+([A-Za-z][A-Za-z0-9]+)', raw_alert_text)
            if commerce_op:
                result['operation'] = commerce_op.group(1).strip()
        
        # Fallback: Check common operations list (case-insensitive). Exclude "checkout" to avoid
        # matching "Express Checkout" in subject; we want the real API name.
        if result['operation'] == 'Unknown':
            operations = [
                'removeCartLines', 'getCartDelivery', 'GetAddressFromZipCode',
                'GetCartRelatedProducts', 'fetchCart', 'updateCart',
                'addToCart', 'removeItems', 'getCart', 'addItems', 'removeAllItems',
                'validateCart', 'submitOrder',
            ]
            for op in operations:
                pattern = r'(?:Alert|API|GraphQL|REST|D365|Operation|Duration)[:\s]+.*?\b(' + re.escape(op) + r')\b'
                match = re.search(pattern, raw_alert_text, re.IGNORECASE)
                if match:
                    result['operation'] = match.group(1)
                    break
        
        # When still vague or Unknown, use Path as the label (e.g. Path: /applepay-express → applepay-express)
        if result['operation'] in ('Unknown', 'Commerce', 'Checkout'):
            path_match = re.search(r'Path:\s*/([a-zA-Z0-9_-]+)', raw_alert_text)
            if path_match:
                path_segment = path_match.group(1).strip()
                if path_segment and path_segment not in ('unknown', 'cart', 'checkout'):
                    result['operation'] = path_segment
                elif path_segment and result['operation'] == 'Unknown':
                    result['operation'] = path_segment
            # Express Checkout (Applepay) → Apple Pay Express
            if result['operation'] == 'Checkout' and re.search(r'Express\s+Checkout\s+\(Applepay\)', raw_alert_text, re.I):
                result['operation'] = 'ApplePayExpress'
        
        # Extract service name
        service_match = re.search(r'(buy-\S+\.vercel\.app|mattressfirm|cart-api|www\.mattressfirm)', raw_alert_text)
        if service_match:
            result['service'] = service_match.group(0)
        
        # Extract alert type
        if 'duration' in raw_alert_text.lower():
            result['alert_type'] = 'High Duration'
        elif 'error' in raw_alert_text.lower():
            result['alert_type'] = 'Error Rate'
        elif 'latency' in raw_alert_text.lower():
            result['alert_type'] = 'High Latency'
        
        logger.debug(f"Parsed alert: {result['operation']} - {result['severity']}")
        return result
    
    except Exception as e:
        logger.error(f"Error parsing alert {filename}: {e}", exc_info=True)
        return {
            'operation': 'Parse Error',
            'service': 'Unknown',
            'alert_type': 'Unknown',
            'severity': 'P3',
            'condition': 'Parse failed',
            'occurrence_count': 0,
            'time_window': 'Unknown',
            'affected_pages': [],
            'status': 'UNKNOWN',
            'related_logs_url': '',
            'subject': '',
            'filename': filename
        }
