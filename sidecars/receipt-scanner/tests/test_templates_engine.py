"""Unit tests for the Stage-2 invoice2data template-matching layer.

The bundled templates load at import time, so the basic public-API
tests just assert shape. The `extract_with_templates` behavior is
covered by monkeypatching the module-level template list with fake
templates that emulate the invoice2data dict-like surface
(`matches_input`, `extract`, dict access for `template_name`).
"""

import pytest

from receipt_scanner import templates_engine


class TestTemplateInventory:
    def test_template_count_matches_names(self):
        assert templates_engine.template_count() == len(
            templates_engine.template_names()
        )

    def test_template_names_are_strings(self):
        for name in templates_engine.template_names():
            assert isinstance(name, str) and name


class TestTemplateNameHelper:
    def test_dict_with_template_name(self):
        tpl = {"template_name": "freshbooks_v1", "issuer": "FreshBooks"}
        assert templates_engine._template_name(tpl) == "freshbooks_v1"

    def test_dict_falls_back_to_issuer(self):
        tpl = {"issuer": "Acme"}
        assert templates_engine._template_name(tpl) == "Acme"

    def test_dict_with_neither_returns_unknown(self):
        assert templates_engine._template_name({}) == "unknown"

    def test_non_dict_object_uses_getattr(self):
        class Tpl:
            template_name = "obj_tpl"
        assert templates_engine._template_name(Tpl()) == "obj_tpl"


class FakeTemplate(dict):
    """Dict-like stand-in for an invoice2data template."""

    def __init__(self, name, matches=True, extract_result=None, raise_on=None):
        super().__init__(template_name=name)
        self._matches = matches
        self._extract = extract_result
        self._raise_on = raise_on  # "matches" | "extract" | None

    def matches_input(self, text):
        if self._raise_on == "matches":
            raise RuntimeError("boom")
        return self._matches

    def extract(self, text):
        if self._raise_on == "extract":
            raise RuntimeError("boom")
        return self._extract


@pytest.fixture
def patch_templates(monkeypatch):
    """Replace _TEMPLATES for the duration of one test."""
    def _set(templates):
        monkeypatch.setattr(templates_engine, "_TEMPLATES", templates)
    return _set


class TestExtractWithTemplates:
    def test_returns_none_when_no_templates(self, patch_templates):
        patch_templates([])
        assert templates_engine.extract_with_templates("any text") is None

    def test_returns_none_when_no_template_matches(self, patch_templates):
        patch_templates([
            FakeTemplate("a", matches=False),
            FakeTemplate("b", matches=False),
        ])
        assert templates_engine.extract_with_templates("text") is None

    def test_first_match_wins(self, patch_templates):
        patch_templates([
            FakeTemplate("first", matches=True,
                         extract_result={"total": "10.00"}),
            FakeTemplate("second", matches=True,
                         extract_result={"total": "99.00"}),
        ])
        result = templates_engine.extract_with_templates("text")
        assert result == {"template": "first", "fields": {"total": "10.00"}}

    def test_skips_non_matching_and_returns_later_match(self, patch_templates):
        patch_templates([
            FakeTemplate("skip_me", matches=False,
                         extract_result={"total": "99"}),
            FakeTemplate("real_match", matches=True,
                         extract_result={"date": "2026-01-01"}),
        ])
        result = templates_engine.extract_with_templates("text")
        assert result == {"template": "real_match",
                          "fields": {"date": "2026-01-01"}}

    def test_returns_none_when_match_yields_empty_extract(self, patch_templates):
        # A matching template whose extract() returns falsy should be
        # treated as a non-match, not propagated as a successful result.
        patch_templates([
            FakeTemplate("matches_but_empty", matches=True, extract_result={}),
        ])
        assert templates_engine.extract_with_templates("text") is None

    def test_swallows_exception_in_matches_input(self, patch_templates):
        # A template whose matches_input raises must not abort the loop;
        # subsequent templates still get a chance.
        patch_templates([
            FakeTemplate("broken", raise_on="matches"),
            FakeTemplate("good", matches=True,
                         extract_result={"total": "5.00"}),
        ])
        result = templates_engine.extract_with_templates("text")
        assert result == {"template": "good", "fields": {"total": "5.00"}}

    def test_swallows_exception_in_extract(self, patch_templates):
        patch_templates([
            FakeTemplate("matches_but_extract_throws",
                         matches=True, raise_on="extract"),
            FakeTemplate("good", matches=True,
                         extract_result={"total": "5.00"}),
        ])
        result = templates_engine.extract_with_templates("text")
        assert result == {"template": "good", "fields": {"total": "5.00"}}
