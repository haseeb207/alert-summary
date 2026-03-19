"""
Ollama client for optional AI enhancement of the Datadog alert agent.

- Operation extraction: when regex yields vague names (Unknown, Commerce, Checkout),
  call Ollama to extract a specific operation/API name from the raw email.
- Narrative summary: optionally generate a one-sentence summary of the period's alerts.

Uses existing requests library; no new dependencies.
"""

import os
import logging
from typing import List, Tuple

import requests

logger = logging.getLogger('datadog_agent')

# Config from env (read at call time so agent can load_dotenv first)
def _base_url() -> str:
    return (os.getenv('OLLAMA_BASE_URL') or 'http://localhost:11434').rstrip('/')

def _model() -> str:
    return os.getenv('OLLAMA_MODEL') or 'llama3.2'

def _timeout() -> int:
    try:
        return int(os.getenv('OLLAMA_TIMEOUT_SECONDS', '20'))
    except ValueError:
        return 20

# Truncate alert text to stay within context limits
_MAX_ALERT_CHARS = 2500

_OPERATION_PROMPT = """From this Datadog alert email, extract the single most specific operation or API name.
Examples: removeCartLines, GetAddressFromZipCode, ApplePayEndpoint, GetCartDelivery.
Reply with only the operation name, nothing else. No explanation.

Email:
"""

_SUMMARY_PROMPT_PREFIX = """Total: {total} alerts. Focus on the 1–2 operations with the highest count. One short sentence for a status report.

Alert counts (highest first):
"""


def get_operation_from_alert(raw_text: str) -> str | None:
    """
    Ask Ollama to extract the operation/API name from the raw alert email.
    Returns the stripped single-line reply, or None on failure/timeout/invalid response.
    """
    if not raw_text or not raw_text.strip():
        return None
    text = raw_text.strip()
    if len(text) > _MAX_ALERT_CHARS:
        text = text[:_MAX_ALERT_CHARS] + "\n[...truncated]"
    prompt = _OPERATION_PROMPT + text
    try:
        r = requests.post(
            f"{_base_url()}/api/generate",
            json={"model": _model(), "prompt": prompt, "stream": False},
            timeout=_timeout(),
        )
        r.raise_for_status()
        data = r.json()
        response = (data.get("response") or "").strip()
        if not response:
            return None
        # Take first line only, limit length
        line = response.split("\n")[0].strip()
        if not line or len(line) > 80:
            return None
        return line
    except requests.exceptions.RequestException as e:
        logger.warning(f"Ollama operation extraction failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Ollama operation extraction error: {e}", exc_info=True)
        return None


def get_period_summary_sentence(operations_with_counts: List[Tuple[str, int]]) -> str | None:
    """
    Ask Ollama to generate one short sentence summarizing the list of (operation, count).
    Caller should pass list sorted by count descending. Total is computed and included in the prompt.
    Returns the sentence or None on failure.
    """
    if not operations_with_counts:
        return None
    total = sum(c for _, c in operations_with_counts)
    lines = [f"- {op}: {count}" for op, count in operations_with_counts[:20]]
    prompt = _SUMMARY_PROMPT_PREFIX.format(total=total) + "\n".join(lines) + "\n\nOne sentence:"
    try:
        r = requests.post(
            f"{_base_url()}/api/generate",
            json={"model": _model(), "prompt": prompt, "stream": False},
            timeout=_timeout(),
        )
        r.raise_for_status()
        data = r.json()
        response = (data.get("response") or "").strip()
        if not response:
            return None
        # Prefer first sentence or first line, cap length
        line = response.split("\n")[0].strip()
        if not line or len(line) > 300:
            return None
        return line
    except requests.exceptions.RequestException as e:
        logger.warning(f"Ollama narrative summary failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Ollama narrative summary error: {e}", exc_info=True)
        return None


def check_ollama_available() -> bool:
    """
    Perform a quick health check (GET /api/tags). Returns True if Ollama is reachable.
    Does not block startup on failure; call at startup to log a warning.
    """
    try:
        r = requests.get(f"{_base_url()}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"Ollama health check failed: {e}")
        return False
