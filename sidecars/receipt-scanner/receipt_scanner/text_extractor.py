"""
Stage 1 of the pipeline: pull a raw_text string out of the input file.

Two paths:
  - PDF: text-layer fast path (PyMuPDF blocks) → OCR fallback if the
    text layer is missing or insufficient. The OCR fallback renders
    each page to an image and runs Tesseract.
  - Image (JPEG / PNG / HEIC): direct Tesseract via Pillow. HEIC is
    handled via pillow-heif (registered on import).

The OCR path requires Tesseract installed. The Docker image bundles it;
for local dev, run the sidecar in Docker (or install via `brew install
tesseract`).
"""

from pathlib import Path
from typing import Tuple

import fitz  # PyMuPDF


try:
    from PIL import Image, ImageOps
    # Receipts never legitimately approach this; cap it so a crafted
    # image can't expand into hundreds of MB during decode.
    Image.MAX_IMAGE_PIXELS = 50_000_000
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass


# Canonical text_source values reported in /parse responses and /health.
TEXT_SOURCES = ("text-layer", "ocr", "tesseract", "tesseract+heic")

MIN_ALNUM_CHARS = 50
CURRENCY_TOKENS = ("$", "€", "£", "USD", "EUR", "GBP", "CAD", "AUD")

# DPI for rendering PDF pages to images before OCR. 300dpi is the
# standard sweet spot for OCR quality vs speed.
OCR_RENDER_DPI = 300

# Guardrails against hostile PDFs: cap how many pages we OCR, and clamp
# each rendered page so a tiny file declaring a huge MediaBox (or many
# pages) can't exhaust memory.
MAX_OCR_PAGES = 20
MAX_RENDER_PIXELS = 50_000_000

# Tesseract page segmentation mode 6 = "uniform block of text" — best
# fit for tall narrow receipts; better than the default which tries to
# detect layout.
TESSERACT_PSM = "--psm 6"


def has_usable_text_layer(text: str) -> bool:
    """True if the text layer has meaningful content plus a currency-like token."""
    alphanum = sum(1 for c in text if c.isalnum())
    has_currency = any(tok in text for tok in CURRENCY_TOKENS)
    return alphanum >= MIN_ALNUM_CHARS and has_currency


def _extract_text_layer(path: Path) -> str:
    """Pull text from a PDF's text layer using position-aware blocks.

    PyMuPDF's plain get_text() appends redaction-replacement text at the
    end of the content stream, which scrambles flows like "Receipt from
    <vendor>" into "Receipt from <newline>...<vendor>". Sorting blocks
    by (y, x) reconstructs the natural reading order from page layout.
    """
    doc = fitz.open(path)
    try:
        pieces = []
        for page in doc:
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (round(b[1], 1), b[0]))
            page_text = "\n".join(b[4].strip() for b in blocks if b[4].strip())
            pieces.append(page_text)
    finally:
        doc.close()
    return "\n".join(pieces)


def _preprocess_image(img):
    """EXIF-aware rotation + autocontrast. Cheap, always-on per §3.2."""
    if ImageOps is None:
        return img
    img = ImageOps.exif_transpose(img)
    img = ImageOps.autocontrast(img)
    return img


def _ocr_pdf(path: Path) -> str:
    """OCR a PDF by rendering each page to an image, then Tesseract."""
    import pytesseract
    if Image is None:
        raise RuntimeError("Pillow is required for OCR but is not installed")

    doc = fitz.open(path)
    try:
        pieces = []
        for page_index, page in enumerate(doc):
            if page_index >= MAX_OCR_PAGES:
                break
            # Scale from PDF points (72/inch) to the target DPI, then
            # shrink further if the page would exceed the pixel cap.
            zoom = OCR_RENDER_DPI / 72.0
            rect = page.rect
            projected = (rect.width * zoom) * (rect.height * zoom)
            if projected > MAX_RENDER_PIXELS:
                zoom *= (MAX_RENDER_PIXELS / projected) ** 0.5
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img = _preprocess_image(img)
            pieces.append(pytesseract.image_to_string(img, config=TESSERACT_PSM))
    finally:
        doc.close()
    return "\n".join(pieces)


def _ocr_image(path: Path) -> Tuple[str, str]:
    """OCR a JPEG/PNG/HEIC. Returns (text, text_source)."""
    import pytesseract
    if Image is None:
        raise RuntimeError("Pillow is required for OCR but is not installed")

    is_heic = path.suffix.lower() == ".heic"
    with Image.open(path) as img:
        if is_heic or img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img = _preprocess_image(img)
        text = pytesseract.image_to_string(img, config=TESSERACT_PSM)
    return text, "tesseract+heic" if is_heic else "tesseract"


def extract_pdf_text(path: Path) -> Tuple[str, str]:
    """Return (raw_text, text_source) for a PDF.

    text_source is `text-layer` when the PDF has a usable text layer,
    `ocr` when we had to OCR the rendered pages.
    """
    text = _extract_text_layer(path)
    if has_usable_text_layer(text):
        return text, "text-layer"
    return _ocr_pdf(path), "ocr"


def extract_text(path: Path) -> Tuple[str, str]:
    """Dispatch on file type."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix in {".jpg", ".jpeg", ".png", ".heic"}:
        return _ocr_image(path)
    raise ValueError(f"unsupported file type: {suffix}")
