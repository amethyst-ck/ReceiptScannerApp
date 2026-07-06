"""Top-level extract_fields() that combines all per-field extractors."""

from ._amounts import (
    FEES_KEYWORDS,
    SUBTOTAL_KEYWORDS,
    TAX_KEYWORDS,
    amount_after_keyword,
    find_amounts,
    find_total,
)
from ._currency import detect_currency
from ._date import find_date
from ._party import find_payer, find_vendor


def extract_fields(text: str, kind: str = "expense") -> dict[str, dict]:
    """
    Run all heuristic extractors on the raw text. Return a dict shaped
    for the response (value + source + optional currency), keyed by
    field name. Missing fields are simply absent.

    For kind="expense", emits `payee` (vendor at top of document).
    For kind="income", emits `payer` (Bill-to / Sold-to / Customer).
    Other fields (total, subtotal, tax, date) are extracted the same way
    for both kinds.
    """
    amounts = find_amounts(text)
    receipt_currency = detect_currency(text)

    out: dict[str, dict] = {}

    total = find_total(text, amounts)
    if total:
        value, currency = total
        out["total"] = {
            "value": f"{value:.2f}",
            "source": "generic",
            "currency": currency or receipt_currency,
        }

    # subtotal/tax legitimately can be 0 — a fully-discounted line or a
    # tax-exempt transaction. Disable the positive-only filter so we
    # don't skip the real value and pick the total instead.
    subtotal = amount_after_keyword(
        text, SUBTOTAL_KEYWORDS, amounts, require_positive=False
    )
    if subtotal:
        out["subtotal"] = {"value": f"{subtotal[0]:.2f}", "source": "generic"}

    tax = amount_after_keyword(
        text, TAX_KEYWORDS, amounts, require_positive=False
    )
    if tax:
        out["tax"] = {"value": f"{tax[0]:.2f}", "source": "generic"}

    fees = amount_after_keyword(
        text, FEES_KEYWORDS, amounts, require_positive=False
    )
    if fees:
        out["fees"] = {"value": f"{fees[0]:.2f}", "source": "generic"}

    date = find_date(text)
    if date:
        out["date"] = {"value": date, "source": "generic"}

    if kind == "income":
        payer = find_payer(text)
        if payer:
            out["payer"] = {"value": payer, "source": "generic"}
    else:
        vendor = find_vendor(text)
        if vendor:
            out["payee"] = {"value": vendor, "source": "generic"}

    return out
