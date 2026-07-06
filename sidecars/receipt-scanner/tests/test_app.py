"""Tests for the Flask /parse and /health endpoints via the test client."""

import hmac
import io

import fitz
import pytest

import receipt_scanner.app as app_module
from receipt_scanner.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


class TestHealth:
    def test_ok(self, client, monkeypatch):
        monkeypatch.setattr(app_module, "TESSERACT_AVAILABLE", True)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["tesseract"] is True
        assert "generic" in data["field_strategies"]

    def test_503_when_tesseract_missing(self, client, monkeypatch):
        # OCR is the core function; a sidecar without tesseract must
        # fail its healthcheck rather than accept work it can't do.
        monkeypatch.setattr(app_module, "TESSERACT_AVAILABLE", False)
        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.get_json()["tesseract"] is False


class TestParseValidation:
    def test_missing_file(self, client):
        resp = client.post("/parse", data={})
        assert resp.status_code == 400

    def test_unsupported_type(self, client):
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"x"), "x.xyz")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert ".pdf" in str(resp.get_json().get("allowed", ""))

    def test_unsupported_kind(self, client):
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"x"), "x.pdf"), "kind": "refund"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "expense" in str(resp.get_json().get("allowed", ""))

    def test_oversized_upload_is_413(self, client):
        client.application.config["MAX_CONTENT_LENGTH"] = 1024
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"x" * 2048), "big.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 413

    def test_corrupt_pdf_is_400(self, client):
        # Garbage bytes with a .pdf name pass the suffix check but fail
        # PyMuPDF decode — a client error, not a 500.
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"not a pdf at all"), "receipt.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "unreadable-file"

    def test_jpeg_bytes_named_pdf_is_400(self, client):
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"\xff\xd8\xff\xe0garbage"), "photo.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "unreadable-file"


class TestParseHappyPath:
    def test_text_layer_pdf(self, client):
        # A synthetic PDF with a real text layer takes the text-layer
        # fast path, so this runs end-to-end without tesseract.
        doc = fitz.open()
        page = doc.new_page()
        lines = (
            "Receipt from Acme Office Supplies",
            "Date: 2026-01-15",
            "Subtotal: $40.00",
            "Tax: $2.00",
            "Total: $42.00",
        )
        for i, line in enumerate(lines):
            page.insert_text((72, 72 + 18 * i), line)
        pdf_bytes = doc.tobytes()
        doc.close()
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(pdf_bytes), "receipt.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["text_source"] == "text-layer"
        assert isinstance(data["fields"], dict)
        assert data["fields"]  # at least one field extracted


class TestHmacGate:
    """X-ReceiptScanner-HMAC verification on /parse.

    Use a `.pdf` suffix so the suffix-check passes; the body is not a
    real PDF, so when HMAC succeeds the request reaches parse_file and
    fails there with a non-401 status. That's fine — we're testing the
    auth gate, not the parser.
    """

    SECRET = "test-shared-secret"

    @pytest.fixture
    def secret_env(self, monkeypatch):
        monkeypatch.setenv("RECEIPT_SCANNER_SHARED_SECRET", self.SECRET)

    @staticmethod
    def _sign(secret, kind, filename, body):
        # Mirror the server-side canonical string: kind\nfilename\nbody.
        signed = kind.encode() + b"\n" + filename.encode() + b"\n" + body
        return hmac.new(secret.encode(), signed, "sha256").hexdigest()

    def test_rejects_missing_header(self, client, secret_env):
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"hello"), "receipt.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 401
        assert "HMAC" in resp.get_json()["error"]

    def test_rejects_wrong_signature(self, client, secret_env):
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"hello"), "receipt.pdf")},
            headers={"X-ReceiptScanner-HMAC": "deadbeef"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 401

    def test_rejects_signature_over_wrong_payload(self, client, secret_env):
        # Sign one payload, submit another — common shape of a replay or
        # tampering attempt.
        sig = self._sign(self.SECRET, "expense", "receipt.pdf", b"other")
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"hello"), "receipt.pdf")},
            headers={"X-ReceiptScanner-HMAC": sig},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 401

    def test_rejects_signature_over_body_only(self, client, secret_env):
        # A signature over just the body (the old scheme) must now fail —
        # kind and filename are bound into the signed string.
        body = b"hello"
        sig = hmac.new(self.SECRET.encode(), body, "sha256").hexdigest()
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(body), "receipt.pdf")},
            headers={"X-ReceiptScanner-HMAC": sig},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 401

    def test_rejects_signature_over_wrong_kind(self, client, secret_env):
        # Sign for one kind, submit another — the bound kind must matter.
        body = b"hello"
        sig = self._sign(self.SECRET, "income", "receipt.pdf", body)
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(body), "receipt.pdf"), "kind": "expense"},
            headers={"X-ReceiptScanner-HMAC": sig},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 401

    def test_accepts_correct_signature(self, client, secret_env):
        body = b"hello"
        sig = self._sign(self.SECRET, "expense", "receipt.pdf", body)
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(body), "receipt.pdf")},
            headers={"X-ReceiptScanner-HMAC": sig},
            content_type="multipart/form-data",
        )
        # Auth accepted; parsing the non-PDF bytes fails downstream —
        # any non-401 status proves we got past the auth gate.
        assert resp.status_code != 401

    def test_accepts_correct_signature_income_kind(self, client, secret_env):
        body = b"hello"
        sig = self._sign(self.SECRET, "income", "receipt.pdf", body)
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(body), "receipt.pdf"), "kind": "income"},
            headers={"X-ReceiptScanner-HMAC": sig},
            content_type="multipart/form-data",
        )
        assert resp.status_code != 401

    def test_non_ascii_header_is_401_not_500(self, client, secret_env):
        # A non-ASCII signature header must be rejected as unauthorized,
        # not crash the constant-time comparison into a 500.
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"hello"), "receipt.pdf")},
            headers={"X-ReceiptScanner-HMAC": "héllo"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 401

    def test_header_ignored_when_no_secret_configured(self, client, monkeypatch):
        # No env var → the header is ignored entirely; request flows
        # through validation and reaches parse_file (which fails on the
        # fake PDF). Header-with-garbage must NOT cause a 401.
        monkeypatch.delenv("RECEIPT_SCANNER_SHARED_SECRET", raising=False)
        resp = client.post(
            "/parse",
            data={"file": (io.BytesIO(b"x"), "receipt.pdf")},
            headers={"X-ReceiptScanner-HMAC": "anything"},
            content_type="multipart/form-data",
        )
        assert resp.status_code != 401
