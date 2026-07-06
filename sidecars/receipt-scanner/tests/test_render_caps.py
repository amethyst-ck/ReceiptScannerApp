"""OCR render guardrails: page cap and per-page pixel clamp."""

import fitz

from receipt_scanner.text_extractor import (
    MAX_OCR_PAGES,
    MAX_RENDER_PIXELS,
    _ocr_pdf,
)


def _make_pdf(path, pages, width=612, height=792):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=width, height=height)
    doc.save(str(path))
    doc.close()


def _record_sizes(monkeypatch):
    """Stub Tesseract so we can inspect the rendered image sizes."""
    sizes = []

    def fake_image_to_string(img, config=None):
        sizes.append(img.size[0] * img.size[1])
        return ""

    import pytesseract
    monkeypatch.setattr(pytesseract, "image_to_string", fake_image_to_string)
    return sizes


def test_huge_page_is_clamped(tmp_path, monkeypatch):
    # A single enormous page (72k x 72k pt ~= 300k x 300k px at 300dpi)
    # must be scaled down under the pixel cap, not rendered at full size.
    pdf = tmp_path / "huge.pdf"
    _make_pdf(pdf, pages=1, width=72000, height=72000)
    sizes = _record_sizes(monkeypatch)
    _ocr_pdf(pdf)
    # Clamped to ~the cap (integer pixmap rounding allows a hair over),
    # not the raw multi-billion-pixel render.
    assert sizes and all(px <= MAX_RENDER_PIXELS * 1.01 for px in sizes)


def test_page_count_is_capped(tmp_path, monkeypatch):
    pdf = tmp_path / "many.pdf"
    _make_pdf(pdf, pages=MAX_OCR_PAGES + 5)
    sizes = _record_sizes(monkeypatch)
    _ocr_pdf(pdf)
    assert len(sizes) == MAX_OCR_PAGES
