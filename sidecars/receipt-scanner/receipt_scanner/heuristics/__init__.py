"""
Generic field-extraction heuristics — the always-on Stage 2 baseline
that runs whether or not an invoice2data template matches.

This package replaces the previous single-file heuristics.py. The
internal layout is:

  _amounts.py     — amount regex, total/subtotal/tax/fees keyword cascades
  _date.py        — date keyword cascade + token regex
  _party.py       — vendor (expense payee) + payer (income) + noise filter
  _currency.py    — receipt-level currency detection
  _orchestrator.py — extract_fields() entry point

The public surface is unchanged: callers should keep importing from
`receipt_scanner.heuristics`.
"""

from ._amounts import amount_after_keyword, find_amounts, find_total
from ._currency import detect_currency
from ._date import find_date
from ._orchestrator import extract_fields
from ._party import find_payer, find_vendor, is_noise_line

__all__ = [
    "amount_after_keyword",
    "detect_currency",
    "extract_fields",
    "find_amounts",
    "find_date",
    "find_payer",
    "find_total",
    "find_vendor",
    "is_noise_line",
]
