FROM python:3.11.11-slim-bookworm AS base

# System dependencies: Tesseract (OCR) and libheif (HEIC decoding) for
# the image path; curl for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libheif1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY receipt_scanner /app/receipt_scanner
COPY templates /app/templates

# Parse untrusted files as an unprivileged user.
RUN useradd -r -u 10001 app && chown -R app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "60", \
     "receipt_scanner.app:app"]
