"""Date extraction from receipts."""

import re
from typing import Optional

import dateparser


# Pin date interpretation so ambiguous slash dates are deterministic
# (US month/day) rather than dateparser's locale autodetection, which
# silently flips order. English-only also avoids slow autodetection.
_DP_SETTINGS = {"DATE_ORDER": "MDY"}
_DP_LANGUAGES = ["en"]


def _parse(value: str):
    return dateparser.parse(value, settings=_DP_SETTINGS, languages=_DP_LANGUAGES)


# Date keyword tiers — try specific ones first.
DATE_KEYWORD_TIERS: list[list[re.Pattern]] = [
    # Tier 1: explicit receipt/invoice/transaction dates.
    [
        re.compile(r"\bReceipt\s+Date\b", re.IGNORECASE),
        re.compile(r"\bInvoice\s+Date\b", re.IGNORECASE),
        re.compile(r"\bTransaction\s+Date\b", re.IGNORECASE),
        re.compile(r"\bOrder\s+Date\b", re.IGNORECASE),
        re.compile(r"\bDate\s+of\s+issue\b", re.IGNORECASE),
        re.compile(r"\bDate\s+of\s+purchase\b", re.IGNORECASE),
        re.compile(r"\bBill\s+Date\b", re.IGNORECASE),
    ],
    # Tier 2: payment timing.
    [
        re.compile(r"\bDate\s+paid\b", re.IGNORECASE),
        re.compile(r"\bDate\s+charged\b", re.IGNORECASE),
        re.compile(r"\bAMOUNT\s+PAID\b\s*\n[^\n]*\n\s*DATE\s+PAID\b", re.IGNORECASE),
        re.compile(r"\bDATE\s+PAID\b", re.IGNORECASE),
        re.compile(r"\bPaid\s+on\b", re.IGNORECASE),
    ],
    # Tier 3: generic "Date" label (last resort).
    [
        re.compile(r"\bDate\b(?!\s+(?:due|of|format|paid|charged))", re.IGNORECASE),
    ],
]

DATE_TOKEN_RE = re.compile(
    r"\b("
    r"\d{4}-\d{2}-\d{2}"                            # 2026-01-04
    r"|\d{1,2}/\d{1,2}/\d{2,4}"                     # 01/04/2026
    r"|[A-Z][a-z]+ \d{1,2},?\s+\d{4}"               # January 4, 2026
    r"|[A-Z][a-z]{2,8},?\s+[A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4}"  # Mon, Jan 19, 2026
    r")\b"
)


# Verbose date with weekday + month name, e.g. "Wed, Jan 21, 2026".
# High-confidence — appears in email-sent lines and receipt narratives.
# Preferred over slash-format header dates ("1/28/26, 10:47 PM") which
# in Gmail-printed PDFs are the print date, not the receipt date.
VERBOSE_DATE_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"\s+\d{1,2},?\s+\d{4}\b"
)


def find_date(text: str) -> Optional[str]:
    """Return ISO date string (YYYY-MM-DD) or None."""
    for tier in DATE_KEYWORD_TIERS:
        for kw_re in tier:
            for m in kw_re.finditer(text):
                chunk = text[m.end(): m.end() + 80]
                for d in DATE_TOKEN_RE.finditer(chunk):
                    parsed = _parse(d.group(1))
                    if parsed:
                        return parsed.strftime("%Y-%m-%d")
    # Fallback A: verbose date with weekday — higher confidence than the
    # print-date in Gmail header noise.
    for m in VERBOSE_DATE_RE.finditer(text):
        parsed = _parse(m.group(0))
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    # Fallback B: first parseable date anywhere.
    for d in DATE_TOKEN_RE.finditer(text):
        parsed = _parse(d.group(1))
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    return None
