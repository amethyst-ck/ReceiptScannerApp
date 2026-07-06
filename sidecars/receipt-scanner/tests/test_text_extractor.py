"""Unit + integration tests for Stage 1 text extraction."""

import pytest

from receipt_scanner import text_extractor


class TestHasUsableTextLayer:
    def test_enough_text_with_currency(self):
        text = "Acme Bookkeeping " * 5 + " Total $17.20 USD"
        assert text_extractor.has_usable_text_layer(text)

    def test_too_short(self):
        assert not text_extractor.has_usable_text_layer("$5")

    def test_no_currency_token(self):
        assert not text_extractor.has_usable_text_layer("a" * 100)


class TestExtractText:
    def test_unsupported_suffix(self, tmp_path):
        bad = tmp_path / "x.xyz"
        bad.write_text("nope")
        with pytest.raises(ValueError):
            text_extractor.extract_text(bad)
