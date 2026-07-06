"""Vendor (expense payee) and payer (income) extraction, plus shared noise-line filter."""

import re
from typing import Optional


NOISE_LINE_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*Invoice\s*$", re.IGNORECASE),
    re.compile(r"^\s*Receipt\s*$", re.IGNORECASE),
    re.compile(r"^\s*PAID\s*$", re.IGNORECASE),
    re.compile(r"^\s*Invoice\s+number\s*$", re.IGNORECASE),
    re.compile(r"^\s*Receipt\s+number(\s+\S+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Order\s+number\s*$", re.IGNORECASE),
    re.compile(r"^\s*Order\s+Confirmation\s*(\s*-\s*\S+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*-\s*Order\s+Confirmation\b", re.IGNORECASE),
    re.compile(r"^\s*Purchase\s+from\b", re.IGNORECASE),
    re.compile(r"^\s*Bill\s+to\s*$", re.IGNORECASE),
    re.compile(r"^\s*Bill\s+from\s*$", re.IGNORECASE),
    re.compile(r"^\s*Description\s*$", re.IGNORECASE),
    re.compile(r"^\s*Subtotal\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Total\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Amount\b", re.IGNORECASE),
    re.compile(r"^\s*Thank\s+You\b", re.IGNORECASE),
    re.compile(r"^\s*\d+/\d+/\d+,\s+\d+:\d+"),     # "1/31/26, 1:33 PM"
    re.compile(r"^\s*https?://"),
    re.compile(r"^\s*\S+@\S+\.\S+\s*$"),           # bare email
    re.compile(r"^\s*[\d.,\s]+$"),                 # mostly digits
    re.compile(r"^\s*[<>]+\s*$"),                  # nav glyphs
    re.compile(r"^\s*[-=*]+\s*$"),                 # separator lines
    re.compile(r"^\s*(Gmail|<)"),
    re.compile(r"^\s*Sample\s+Customer\b"),        # our anonymized customer placeholder
    re.compile(r"^\s*Date\s+(?:paid|due|charged|of)\b", re.IGNORECASE),
    re.compile(r"^\s*Your\s*$", re.IGNORECASE),    # email-body filler
    re.compile(r"^\s*(?:Hello|Hi|Welcome|Dear)\b", re.IGNORECASE),
    re.compile(                                    # bare date "February 15, 2026"
        r"^\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*"
        r"\s+\d{1,2},?\s+\d{4}\s*$"
    ),
    re.compile(r"^\s*ANONINV-\d+\s*$", re.IGNORECASE),   # our anonymized invoice ID
]


def is_noise_line(line: str) -> bool:
    """True if the line matches any of the boilerplate / chrome patterns
    that should be skipped when scanning for a vendor or payer."""
    return any(p.match(line) for p in NOISE_LINE_PATTERNS)


VENDOR_SUFFIXES_TO_STRIP = (" Receipts", " Notifications", " Support", " Team")


def _clean_vendor(candidate: str) -> str:
    """Strip trailing whitespace, punctuation, common email-sender suffixes."""
    s = candidate.strip().rstrip(",.;: ")
    for suffix in VENDOR_SUFFIXES_TO_STRIP:
        if s.endswith(suffix):
            s = s[: -len(suffix)].rstrip()
    return s


def _vendor_from_domain(domain: str) -> str:
    """`acme-airlines.example.com` → `Acme Airlines`."""
    # Strip subdomains by taking the leftmost label.
    label = domain.split(".")[0]
    parts = label.replace("-", " ").replace("_", " ").split()
    return " ".join(p.capitalize() for p in parts)


def find_vendor(text: str) -> Optional[str]:
    """
    Try in priority order:
      1. Explicit "Receipt from X" / "Invoice from X" / "Order from X"
      2. Gmail-style sender header: `Name <local@domain.tld>`
      3. Email address with a non-generic domain
      4. First non-noise line that looks like a proper noun
    """
    # 1. Receipt/Invoice/Order from X — take to end of line, capped to 60c.
    for kw in ("Receipt from", "Invoice from", "Order from"):
        for m in re.finditer(rf"{kw}\s+([^\n]{{2,60}})", text, re.IGNORECASE):
            return _clean_vendor(m.group(1))

    # 2. Gmail sender header: "<Vendor Name> <local@domain>" on its own line.
    SENDER_RE = re.compile(
        r"^\s*([A-Z][A-Za-z0-9&'., \-]{2,40})\s*<[^@>\s]+@([A-Za-z0-9.\-]+)>",
        re.MULTILINE,
    )
    GENERIC_LOCALS = {"gmail", "googlemail", "mail", "icloud", "yahoo", "outlook", "hotmail"}
    for m in SENDER_RE.finditer(text):
        name, domain = m.group(1), m.group(2).lower()
        # Skip the recipient line ("Sample Customer <customer@example.com>").
        root = domain.split(".")[0]
        if root in GENERIC_LOCALS or ("example" in domain and name.startswith("Sample Customer")):
            continue
        return _clean_vendor(name)

    # 3. Plain email address whose domain isn't generic.
    for m in re.finditer(
        r"([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.(?:com|net|org|io|co|gov))",
        text,
    ):
        local = m.group(1).lower()
        domain = m.group(2).lower()
        # Skip the customer's anonymized placeholder.
        if local == "customer" and domain in ("example.com", "example.org"):
            continue
        # Skip bare example.* with no subdomain (it's the placeholder root).
        if domain in ("example.com", "example.org"):
            continue
        root = domain.split(".")[0]
        if root in GENERIC_LOCALS:
            continue
        return _vendor_from_domain(domain)

    # 4. First non-noise line.
    for raw_line in text.split("\n")[:40]:
        line = raw_line.strip()
        if not line or is_noise_line(line):
            continue
        if len(line) < 3:
            continue
        return _clean_vendor(line)
    return None


# --- Payer extraction (income receipts) ---------------------------------
#
# For an income document, the "payer" is the entity that sent money to
# the user. It's typically labeled "Bill to:", "Sold to:", "Customer:",
# "Payer:", "Received from:", or "From:". The name sits either on the
# same line (after a colon) or on the next non-noise line below.

# Keyword + value on the same line: "Bill to: Acme Corp"
PAYER_INLINE_PATTERNS = [
    re.compile(r"^\s*Bill(?:ed)?\s+to\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Sold\s+to\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Invoiced\s+to\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Customer\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Payer\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Received\s+from\s*:?\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*From\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
]

# Keyword on a line by itself, value on the next non-noise line below.
PAYER_BLOCK_KEYWORDS = [
    re.compile(r"^\s*Bill(?:ed)?\s+to\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Sold\s+to\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Invoiced\s+to\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Customer\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Payer\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Received\s+from\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*From\s*:?\s*$", re.IGNORECASE),
]


def find_payer(text: str) -> Optional[str]:
    """Find the payer for an income document.

    Tries inline form ("Bill to: Acme") first, then block form (label on
    its own line with the name on the next non-noise line). Returns the
    cleaned name or None.
    """
    for pat in PAYER_INLINE_PATTERNS:
        for m in pat.finditer(text):
            candidate = m.group(1).strip()
            if len(candidate) >= 3 and not is_noise_line(candidate):
                return _clean_vendor(candidate)

    lines = text.split("\n")
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not any(p.match(line) for p in PAYER_BLOCK_KEYWORDS):
            continue
        # Look ahead a few lines for the first non-noise candidate.
        for j in range(i + 1, min(i + 6, len(lines))):
            nxt = lines[j].strip()
            if not nxt or is_noise_line(nxt) or len(nxt) < 3:
                continue
            return _clean_vendor(nxt)
    return None
