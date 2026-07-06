"""Response shapes returned by /parse."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedField:
    """One extracted field plus provenance.

    `source` is `generic` for heuristic output or `template:<name>` when
    an invoice2data template supplied the value. `currency` is set on
    monetary fields when a currency token was detected.
    """
    value: str
    source: str
    currency: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"value": self.value, "source": self.source}
        if self.currency is not None:
            d["currency"] = self.currency
        return d


@dataclass
class ParseResult:
    """Full /parse response: per-field extractions plus the text-extraction
    path used (`text-layer`, `ocr`, `tesseract`, `tesseract+heic`).
    `note` is set when no fields could be extracted.

    The OCR'd text is intentionally not in the response — the wiki side
    persists the whole payload to the queue table and has no consumer
    for the raw text. Keep diagnostic raw text in sidecar logs only.
    """
    text_source: str
    fields: dict[str, ParsedField] = field(default_factory=dict)
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "text_source": self.text_source,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "note": self.note,
        }
