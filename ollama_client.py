"""
Ollama client for optional AI enhancement of the Datadog alert agent.

- Operation extraction: when regex yields vague names (Unknown, Commerce, Checkout),
  call Ollama to extract a specific operation/API name from the raw email.
- Narrative summary: optionally generate a one-sentence summary of the period's alerts.

Uses existing requests library; no new dependencies.
"""

import os
import re
import logging
from typing import List, Set, Tuple

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

_SUMMARY_PROMPT_PREFIX = """Total: {total} alerts. Write ONE short sentence for a status report.

Rules:
- Use ONLY the exact operation/API names exactly as written in the list below (same spelling and casing).
- Do NOT replace them with generic phrases like "inventory management", "cart management", "payment processing", or "multiple systems".
- Prefer naming the 1–2 operations with the highest counts using those exact names.

Bad example: "6 cart management alerts"
Good example: "removeCartLines (4) and addCartLine (2) are the highest-volume operations in this period"

Alert counts (highest first):
"""

_HISTORY_INSIGHT_PROMPT = """You compare two FIXED datasets from our monitoring database. Output must be grounded only in these lists.

DATASET A — Current reporting period (operation name: alert rows this period):
{current_block}

DATASET B — Earlier rows in the retention window before this period (operation name: row count, top by volume):
{prior_block}

Rules:
- At most 2 sentences. No bullet points. No numbers except counts that appear in A or B above for those operations.
- Use ONLY operation/API names that appear verbatim in DATASET A or DATASET B (same spelling). Do not invent names or incidents.
- Do not mention time zones, dates, or systems not in the data.
- If DATASET B is empty or a comparison is not meaningful, reply exactly this single line:
No prior-period comparison available.

Insight:
"""

# Words allowed in history insight after operation names are masked out (lowercase)
_INSIGHT_STOPWORDS: Set[str] = frozenset({
    "this", "that", "these", "those", "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "as", "by", "with", "from", "than", "into", "during", "including", "excluding", "against",
    "is", "are", "was", "were", "been", "be", "have", "has", "had", "do", "does", "did", "not", "no",
    "more", "less", "fewer", "most", "some", "all", "both", "each", "every", "other", "same", "such",
    "prior", "current", "period", "periods", "comparison", "compared", "compare", "between", "within",
    "while", "where", "when", "which", "who", "also", "only", "just", "then", "now", "new", "before",
    "higher", "lower", "similar", "different", "increased", "decreased", "stable", "relative", "overall",
    "alert", "alerts", "data", "volume", "volumes", "pattern", "patterns", "available", "insight",
    "continues", "continue", "dominant", "dominated", "focus", "remains", "remain", "suggests", "suggest",
    "indicates", "indicate", "shows", "show", "reflects", "reflect", "matches", "match", "like", "unlike",
    "than", "among", "across", "still", "again", "mostly", "mainly", "primarily", "versus", "vs",
    "dominates", "dominated", "dominate", "spike", "spikes", "elevated", "heavy", "light", "notable",
    "especially", "contributed", "contribution", "shift", "shifts", "activity", "recent", "earlier",
})


def validate_history_insight_text(text: str, allowed_ops: Set[str]) -> bool:
    """
    Reject model output that introduces unknown tokens after masking known operation names.
    """
    t = (text or "").strip()
    if not t or len(t) > 450:
        return False
    if re.match(r"^No prior-period comparison available\.?$", t, re.I):
        return True
    masked = t
    for op in sorted(allowed_ops, key=len, reverse=True):
        if op:
            masked = masked.replace(op, " ")
    rest = re.sub(r"[^\w\s]", " ", masked)
    for word in rest.split():
        wl = word.lower()
        if wl in _INSIGHT_STOPWORDS or len(word) <= 2:
            continue
        if word.isdigit():
            continue
        return False
    return True


def _first_two_sentences(text: str) -> str:
    """Take at most the first two sentences (., !, ?)."""
    t = text.strip()
    if not t:
        return ""
    ends = []
    for i, c in enumerate(t):
        if c in ".!?" and (i + 1 >= len(t) or t[i + 1] in " \n\t"):
            ends.append(i + 1)
    if len(ends) == 0:
        return t[:400]
    if len(ends) == 1:
        return t[: ends[0]].strip()
    return t[: ends[1]].strip()


def get_period_history_insight(
    current_ops: List[Tuple[str, int]],
    prior_ops: List[Tuple[str, int]],
) -> str | None:
    """
    Compare current period operation counts to prior rows in the retention window (before this period).
    Returns a short grounded insight, or None if Ollama fails or output fails validation.
    If prior_ops is empty, returns the fixed phrase without calling the model.
    """
    if not current_ops:
        return None
    allowed_ops: Set[str] = {op for op, _ in current_ops if op} | {op for op, _ in prior_ops if op}

    if not prior_ops:
        return "No prior-period comparison available."

    cur_lines = "\n".join(f"- {op}: {cnt}" for op, cnt in current_ops[:25])
    pri_lines = "\n".join(f"- {op}: {cnt}" for op, cnt in prior_ops[:25])
    prompt = _HISTORY_INSIGHT_PROMPT.format(current_block=cur_lines, prior_block=pri_lines)

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
        flat = " ".join(response.split())
        line = _first_two_sentences(flat)
        if not line:
            return None
        if not validate_history_insight_text(line, allowed_ops):
            logger.warning("History insight failed validation; omitting from Teams message.")
            return None
        return line
    except requests.exceptions.RequestException as e:
        logger.warning(f"Ollama history insight failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Ollama history insight error: {e}", exc_info=True)
        return None


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
