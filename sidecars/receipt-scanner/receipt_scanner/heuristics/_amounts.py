"""Amount, total, subtotal, tax, and fees extraction."""

import re
from typing import Optional


# Match a currency amount like "$1,234.56", "1234.56", "904.54 USD".
# - Optional currency symbol prefix
# - Optional negative sign
# - Comma-thousands or plain digits
# - Required 2-digit fractional part
# - Optional ISO code suffix
AMOUNT_RE = re.compile(
    r"(?<![A-Za-z0-9.])"           # not glued to prior alnum or another dot
    r"(?P<sym>\$|€|£)?"
    r"(?P<neg>-)?"
    r"(?P<whole>\d{1,3}(?:,\d{3})+|\d+)"
    r"\.(?P<frac>\d{2})"
    r"\b"
    r"(?:\s*(?P<iso>USD|EUR|GBP|CAD|AUD))?"
)

SYMBOL_TO_ISO = {"$": "USD", "€": "EUR", "£": "GBP"}


# Total-keyword cascade. Each tier is tried in order; the first tier
# that yields a non-zero amount wins. Within a tier, the closest amount
# after a keyword match is preferred.
TOTAL_KEYWORD_TIERS: list[list[re.Pattern]] = [
    # Tier 1: an explicit, unambiguous "Total" line.
    [
        re.compile(r"(?<!Sub)\bTotal\b\s*:?(?!\s+excluding)(?!\s+MileagePlus)", re.IGNORECASE),
        re.compile(r"\bGrand\s+total\b", re.IGNORECASE),
        re.compile(r"\bTotal\s+Per\s+Passenger\b", re.IGNORECASE),
    ],
    # Tier 2: paid / charged.
    [
        re.compile(r"\bAmount\s+paid\b", re.IGNORECASE),
        re.compile(r"\bAmount\s+charged\b", re.IGNORECASE),
        re.compile(r"\bTotal\s+charged\b", re.IGNORECASE),
    ],
    # Tier 3: due / balance (often $0 after payment, hence lower priority).
    [
        re.compile(r"\bAmount\s+due\b", re.IGNORECASE),
        re.compile(r"\bBalance\s+due\b", re.IGNORECASE),
        re.compile(r"\bBalance\b\s*:", re.IGNORECASE),
    ],
]

SUBTOTAL_KEYWORDS = [
    re.compile(r"\bSubtotal\b", re.IGNORECASE),
    re.compile(r"\bTotal\s+excluding\s+tax\b", re.IGNORECASE),
]

# A bare "Tax" can be a column header (e.g. the Anthropic invoice has a
# `Description | Tax | Amount` table where "Tax" precedes a line-item
# subtotal, not the tax amount). Require either a colon (`Tax:`) or a
# jurisdiction qualifier (`Tax - Maryland (6% on $5.00)`) so the column
# header doesn't capture the wrong number. GST/VAT/HST are unambiguous.
# The `(?:\s*\([^)]*\))?` consumes a trailing rate parenthetical so
# the keyword end-position lands past it — e.g. for "Tax - Maryland
# (6% on $5.00)\n$0.30", we don't want the $5.00 inside the parens
# to win over the real $0.30 on the next line.
TAX_KEYWORDS = [
    re.compile(r"\bTax\s+-\s+\w+(?:\s*\([^)]*\))?", re.IGNORECASE),
    re.compile(r"\b(?:Sales\s+|Total\s+)?Tax\s*:", re.IGNORECASE),
    re.compile(r"\bGST\b", re.IGNORECASE),
    re.compile(r"\bVAT\b", re.IGNORECASE),
    re.compile(r"\bHST\b", re.IGNORECASE),
]

# Charges added on top of the subtotal that aren't tax — service fees,
# processing fees, tips, gratuities, etc. Matched only with a colon or
# specific qualifier so bare "Fee" in unrelated text doesn't capture.
FEES_KEYWORDS = [
    re.compile(r"\bService\s+(?:fee|charge)\b", re.IGNORECASE),
    re.compile(r"\bProcessing\s+fee\b", re.IGNORECASE),
    re.compile(r"\b(?:Credit\s+card|Card)\s+(?:fee|charge)\b", re.IGNORECASE),
    re.compile(r"\bConvenience\s+fee\b", re.IGNORECASE),
    re.compile(r"\bDelivery\s+fee\b", re.IGNORECASE),
    re.compile(r"\bBooking\s+fee\b", re.IGNORECASE),
    re.compile(r"\bSurcharge\b", re.IGNORECASE),
    re.compile(r"\bGratuity\b", re.IGNORECASE),
    re.compile(r"\bTip\s*:", re.IGNORECASE),
    re.compile(r"\bFees?\s*:", re.IGNORECASE),
]


def find_amounts(text: str) -> list[tuple[int, float, Optional[str]]]:
    """Return list of (position, value, currency_iso_or_None)."""
    out = []
    for m in AMOUNT_RE.finditer(text):
        whole = m.group("whole").replace(",", "")
        value = float(f"{whole}.{m.group('frac')}")
        if m.group("neg") == "-":
            value = -value
        currency = m.group("iso") or SYMBOL_TO_ISO.get(m.group("sym") or "")
        out.append((m.start(), value, currency))
    return out


def amount_after_keyword(
    text: str,
    keyword_patterns: list[re.Pattern],
    amounts: list[tuple[int, float, Optional[str]]],
    window: int = 100,
    require_positive: bool = True,
) -> Optional[tuple[float, Optional[str]]]:
    """
    Find the amount with smallest distance after any matching keyword.
    If require_positive, $0 values are skipped — useful for finding the
    "real" total when "Amount Due" is shown as $0 after payment.
    """
    best_dist = float("inf")
    best: Optional[tuple[float, Optional[str]]] = None
    for kw_re in keyword_patterns:
        for m in kw_re.finditer(text):
            kw_end = m.end()
            for pos, value, currency in amounts:
                if pos < kw_end or pos - kw_end > window:
                    continue
                if require_positive and value <= 0:
                    continue
                dist = pos - kw_end
                if dist < best_dist:
                    best_dist = dist
                    best = (value, currency)
    return best


def find_total(
    text: str,
    amounts: list[tuple[int, float, Optional[str]]],
) -> Optional[tuple[float, Optional[str]]]:
    """Cascade through tiers; first tier with a hit wins."""
    for tier in TOTAL_KEYWORD_TIERS:
        hit = amount_after_keyword(text, tier, amounts, require_positive=True)
        if hit is not None:
            return hit
    # Last resort: largest amount in the document. Useful for receipts
    # that show a payment line without a "Total" keyword (e.g. Lyft).
    positive = [a for a in amounts if a[1] > 0]
    if positive:
        _, value, currency = max(positive, key=lambda a: a[1])
        return value, currency
    return None
