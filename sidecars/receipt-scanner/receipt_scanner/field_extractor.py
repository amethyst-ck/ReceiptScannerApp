"""
Stage 2 orchestration: run all field-extraction strategies and merge.

- Generic heuristics always run (baseline).
- invoice2data templates run when keywords match.
- Template values overlay generic values per field.
- Each returned field carries a `source` marker ("generic" or
  "template:<name>") so the UI can show provenance.
"""

from datetime import date as _date_type, datetime
from pathlib import Path

from .heuristics import extract_fields
from .models import ParsedField, ParseResult
from .templates_engine import extract_with_templates
from .text_extractor import extract_text


# invoice2data field name → our field name.
INVOICE2DATA_FIELD_MAP = {
    "amount": "total",
    "amount_total": "total",
    "amount_subtotal": "subtotal",
    "amount_tax": "tax",
    "date": "date",
    "payee": "payee",
    "issuer": "payee",
}


def _normalize_template_value(field_name: str, value) -> str:
    """Coerce invoice2data's typed values to our string format."""
    if field_name == "date":
        if isinstance(value, (datetime, _date_type)):
            return value.strftime("%Y-%m-%d")
        return str(value)
    if field_name in ("total", "subtotal", "tax"):
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def parse_file(path: Path, kind: str = "expense") -> ParseResult:
    """Top-level pipeline entry point: extract text, run heuristics,
    overlay any matching invoice2data template, return a ParseResult."""
    raw_text, text_source = extract_text(path)

    # Generic baseline — always runs. extract_fields returns a fresh dict.
    merged: dict[str, dict] = extract_fields(raw_text, kind=kind)

    # Template enrichment — overlays per field, preserves generic where
    # the template didn't speak.
    tpl_result = extract_with_templates(raw_text)
    if tpl_result:
        template_name = tpl_result["template"]
        tpl_fields = tpl_result["fields"] or {}
        for inv_field, our_field in INVOICE2DATA_FIELD_MAP.items():
            if inv_field not in tpl_fields or tpl_fields[inv_field] in (None, ""):
                continue
            # For income, invoice2data's `payee`/`issuer` is still the
            # seller (== the user) — meaningless as the income payer.
            # Skip that overlay; the heuristic handles the payer via
            # Bill-to/Sold-to/etc.
            if kind == "income" and our_field == "payee":
                continue
            value_str = _normalize_template_value(our_field, tpl_fields[inv_field])
            entry: dict = {
                "value": value_str,
                "source": f"template:{template_name}",
            }
            # Preserve currency: prefer template's, else carry forward
            # whatever the generic heuristic detected for that field.
            tpl_currency = tpl_fields.get("currency")
            if tpl_currency:
                entry["currency"] = tpl_currency
            elif our_field in merged and "currency" in merged[our_field]:
                entry["currency"] = merged[our_field]["currency"]
            merged[our_field] = entry

    fields = {
        name: ParsedField(
            value=data["value"],
            source=data["source"],
            currency=data.get("currency"),
        )
        for name, data in merged.items()
    }
    note = None if fields else "no fields extracted"
    return ParseResult(
        text_source=text_source,
        fields=fields,
        note=note,
    )
