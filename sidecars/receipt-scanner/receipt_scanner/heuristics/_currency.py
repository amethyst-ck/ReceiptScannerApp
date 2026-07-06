"""Receipt-level currency detection."""

import re


def detect_currency(text: str, fallback: str = "USD") -> str:
    """Determine the currency of the receipt as a whole."""
    isos = re.findall(r"\b(USD|EUR|GBP|CAD|AUD)\b", text)
    if isos:
        # Mode (most frequent) wins for the receipt-level currency.
        return max(set(isos), key=isos.count)
    if "€" in text:
        return "EUR"
    if "£" in text:
        return "GBP"
    return fallback
