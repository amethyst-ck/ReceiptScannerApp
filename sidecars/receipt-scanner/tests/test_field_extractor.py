"""Tests for the Stage 2 orchestration in field_extractor.parse_file.

extract_text and extract_with_templates are monkeypatched so these
tests exercise the merge/overlay logic without touching real files or
invoice2data templates.
"""

from datetime import date, datetime
from pathlib import Path

import pytest

from receipt_scanner import field_extractor
from receipt_scanner.field_extractor import _normalize_template_value, parse_file


@pytest.fixture
def patch_pipeline(monkeypatch):
    """Return a helper that stubs extract_text + extract_with_templates."""

    def _apply(generic, tpl_result, text_source="text-layer"):
        monkeypatch.setattr(
            field_extractor, "extract_text",
            lambda path: ("raw text", text_source),
        )
        monkeypatch.setattr(
            field_extractor, "extract_fields",
            lambda text, kind="expense": dict(generic),
        )
        monkeypatch.setattr(
            field_extractor, "extract_with_templates",
            lambda text: tpl_result,
        )

    return _apply


class TestNormalizeTemplateValue:
    def test_datetime_to_iso_date(self):
        assert _normalize_template_value("date", datetime(2024, 3, 5, 9, 0)) == "2024-03-05"

    def test_date_to_iso_date(self):
        assert _normalize_template_value("date", date(2024, 3, 5)) == "2024-03-05"

    def test_float_amount_two_decimals(self):
        assert _normalize_template_value("total", 17.2) == "17.20"

    def test_numeric_string_amount_two_decimals(self):
        assert _normalize_template_value("tax", "1.5") == "1.50"

    def test_non_numeric_amount_passthrough(self):
        assert _normalize_template_value("total", "N/A") == "N/A"

    def test_non_amount_field_passthrough(self):
        assert _normalize_template_value("payee", "Acme Co") == "Acme Co"


class TestParseFileOverlay:
    def test_template_overlays_generic(self, patch_pipeline):
        generic = {"total": {"value": "10.00", "source": "generic"}}
        tpl = {"template": "acme", "fields": {"amount": 12.5}}
        patch_pipeline(generic, tpl)

        result = parse_file(Path("x.pdf"), kind="expense")
        total = result.fields["total"]
        assert total.value == "12.50"
        assert total.source == "template:acme"

    def test_generic_preserved_where_template_silent(self, patch_pipeline):
        generic = {
            "total": {"value": "10.00", "source": "generic"},
            "date": {"value": "2024-01-01", "source": "generic"},
        }
        tpl = {"template": "acme", "fields": {"amount": 12.5}}
        patch_pipeline(generic, tpl)

        result = parse_file(Path("x.pdf"))
        assert result.fields["total"].source == "template:acme"
        assert result.fields["date"].value == "2024-01-01"
        assert result.fields["date"].source == "generic"

    def test_empty_and_none_template_fields_skipped(self, patch_pipeline):
        generic = {"total": {"value": "10.00", "source": "generic"}}
        tpl = {"template": "acme", "fields": {"amount": None, "date": ""}}
        patch_pipeline(generic, tpl)

        result = parse_file(Path("x.pdf"))
        # None/empty template values leave the generic total untouched and
        # add no date.
        assert result.fields["total"].source == "generic"
        assert "date" not in result.fields

    def test_income_discards_template_payee(self, patch_pipeline):
        generic = {"payer": {"value": "Client LLC", "source": "generic"}}
        tpl = {"template": "acme", "fields": {"payee": "Seller Inc", "issuer": "Seller Inc"}}
        patch_pipeline(generic, tpl)

        result = parse_file(Path("x.pdf"), kind="income")
        # Template payee/issuer map to `payee`, which is skipped for income.
        assert "payee" not in result.fields
        assert result.fields["payer"].value == "Client LLC"

    def test_expense_keeps_template_payee(self, patch_pipeline):
        generic = {}
        tpl = {"template": "acme", "fields": {"payee": "Seller Inc"}}
        patch_pipeline(generic, tpl)

        result = parse_file(Path("x.pdf"), kind="expense")
        assert result.fields["payee"].value == "Seller Inc"
        assert result.fields["payee"].source == "template:acme"

    def test_template_currency_preferred(self, patch_pipeline):
        generic = {"total": {"value": "10.00", "source": "generic", "currency": "USD"}}
        tpl = {"template": "acme", "fields": {"amount": 12.5, "currency": "EUR"}}
        patch_pipeline(generic, tpl)

        result = parse_file(Path("x.pdf"))
        assert result.fields["total"].currency == "EUR"

    def test_generic_currency_carried_forward(self, patch_pipeline):
        generic = {"total": {"value": "10.00", "source": "generic", "currency": "USD"}}
        tpl = {"template": "acme", "fields": {"amount": 12.5}}
        patch_pipeline(generic, tpl)

        result = parse_file(Path("x.pdf"))
        # No template currency → carry forward the generic detection.
        assert result.fields["total"].currency == "USD"

    def test_no_template_match_keeps_generic(self, patch_pipeline):
        generic = {"total": {"value": "10.00", "source": "generic"}}
        patch_pipeline(generic, None)

        result = parse_file(Path("x.pdf"))
        assert result.fields["total"].value == "10.00"
        assert result.fields["total"].source == "generic"

    def test_no_fields_extracted_note(self, patch_pipeline):
        patch_pipeline({}, None)

        result = parse_file(Path("x.pdf"))
        assert result.fields == {}
        assert result.note == "no fields extracted"

    def test_text_source_propagated(self, patch_pipeline):
        patch_pipeline({}, None, text_source="tesseract+heic")

        result = parse_file(Path("x.heic"))
        assert result.text_source == "tesseract+heic"
