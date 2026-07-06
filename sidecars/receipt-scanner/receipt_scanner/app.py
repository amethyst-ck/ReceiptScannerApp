"""
Flask app exposing the /parse and /health endpoints.

POST /parse  multipart/form-data with file=<pdf|jpg|png|heic>
GET  /health status check, also used by Docker healthcheck.

If RECEIPT_SCANNER_SHARED_SECRET is set in the environment, /parse
requires an X-ReceiptScanner-HMAC header carrying an HMAC-SHA256 over
the canonical string `kind + "\n" + filename + "\n"` followed by the
raw file bytes, keyed by that secret. The wiki extension sends the
header whenever $wgReceiptScannerSidecarSecret is non-empty; the two
values must match.
"""

import hmac
import os
import tempfile
from pathlib import Path

import fitz
import pytesseract
from flask import Flask, jsonify, request
from PIL import Image, UnidentifiedImageError

from . import __version__
from .field_extractor import parse_file
from .templates_engine import INVOICE2DATA_AVAILABLE, template_count, template_names
from .text_extractor import TEXT_SOURCES

MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "20"))
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024

ALLOWED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".heic"}
ALLOWED_KINDS = {"expense", "income"}


def _probe_tesseract() -> bool:
    """The tesseract binary is a system dependency, not pip-installable;
    probe it once at startup so /health can report OCR capability."""
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


TESSERACT_AVAILABLE = _probe_tesseract()


def create_app() -> Flask:
    """Build and configure the Flask app, registering the two endpoints."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES

    @app.route("/health", methods=["GET"])
    def health():
        strategies = ["generic"]
        if INVOICE2DATA_AVAILABLE:
            strategies.append("invoice2data")
        # Without tesseract nothing can be OCR'd, so report unhealthy
        # (503) and let the Docker healthcheck flag the container.
        ok = TESSERACT_AVAILABLE
        return jsonify({
            "status": "ok" if ok else "unavailable",
            "version": __version__,
            "tesseract": TESSERACT_AVAILABLE,
            "text_extractors": list(TEXT_SOURCES),
            "field_strategies": strategies,
            "templates_loaded": template_count(),
            "templates": template_names(),
        }), 200 if ok else 503

    @app.route("/parse", methods=["POST"])
    def parse():
        if "file" not in request.files:
            return jsonify({"error": "missing 'file' field"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "empty filename"}), 400

        suffix = Path(f.filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            return jsonify({
                "error": f"unsupported file type: {suffix}",
                "allowed": sorted(ALLOWED_SUFFIXES),
            }), 400

        kind = (request.form.get("kind") or "expense").lower()
        if kind not in ALLOWED_KINDS:
            return jsonify({
                "error": f"unsupported kind: {kind}",
                "allowed": sorted(ALLOWED_KINDS),
            }), 400

        contents = f.read()

        # The wiki signs a canonical string binding the kind and the
        # multipart filename to the raw file bytes:
        #   kind + "\n" + filename + "\n" + contents
        # so a tampered kind or filename fails the check. We recompute
        # against the values actually received and compare in constant
        # time. When the env var is unset the header is ignored —
        # matches the wiki side, which only emits the header when
        # $wgReceiptScannerSidecarSecret is non-empty.
        secret = os.environ.get("RECEIPT_SCANNER_SHARED_SECRET", "")
        if secret:
            provided = request.headers.get("X-ReceiptScanner-HMAC", "")
            signed_input = (
                kind.encode() + b"\n" + f.filename.encode() + b"\n" + contents
            )
            expected = hmac.new(
                secret.encode(), signed_input, "sha256"
            ).hexdigest()
            # Compare as bytes: compare_digest raises TypeError on a
            # non-ASCII header, which would otherwise surface as a 500.
            if not provided or not hmac.compare_digest(
                expected.encode(), provided.encode("utf-8", "replace")
            ):
                return jsonify({
                    "error": "invalid or missing HMAC signature"
                }), 401

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(contents)
        try:
            result = parse_file(tmp_path, kind=kind)
            return jsonify(result.to_dict())
        except pytesseract.pytesseract.TesseractNotFoundError:
            # Missing tesseract binary is a deployment fault, not a bad
            # upload — and it subclasses OSError, so catch it first.
            app.logger.exception("parse failed")
            return jsonify({"error": "internal error"}), 500
        except (
            fitz.FileDataError,
            fitz.mupdf.FzErrorBase,
            UnidentifiedImageError,
            Image.DecompressionBombError,
            OSError,
            pytesseract.TesseractError,
        ) as exc:
            # Undecodable client input: corrupt/empty PDF, bytes that
            # aren't an image, mid-decode MuPDF failures (FzErrorBase,
            # e.g. JPEG bytes named .pdf), truncated image data (plain
            # OSError from PIL), or tesseract choking on the decoded
            # input. The code is a stable machine token the extension
            # maps to i18n.
            app.logger.info("unreadable upload %r: %s", f.filename, exc)
            return jsonify({
                "error": "unreadable or corrupt file",
                "code": "unreadable-file",
            }), 400
        except Exception:
            # Log the full traceback server-side; return a generic error
            # so exception internals never reach the client.
            app.logger.exception("parse failed")
            return jsonify({"error": "internal error"}), 500
        finally:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass

    @app.errorhandler(413)
    def _too_large(_):
        return jsonify({"error": f"file exceeds {MAX_FILE_MB}MB"}), 413

    return app


# Module-level app for gunicorn: `gunicorn receipt_scanner.app:app`
app = create_app()
