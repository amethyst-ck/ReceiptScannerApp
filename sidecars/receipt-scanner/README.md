# receipt-scanner sidecar

Flask service that the ReceiptScanner MediaWiki extension calls to
extract structured fields from uploaded receipts. Runs as a separate
container alongside the wiki: on Docker Compose the wiki reaches it at
`http://receipt-scanner:8000/parse` over the shared compose network;
on Kubernetes it is a sidecar Service the wiki reaches by Service DNS
name.

## Layout

```
receipt_scanner/
  app.py                # Flask routes (/health, /parse)
  text_extractor.py     # Stage 1 — get text from a PDF / image
  field_extractor.py    # Stage 2 — orchestrate field extraction
  templates_engine.py   # Stage 2 enrichment — invoice2data templates
  heuristics/           # Stage 2 baseline — per-field regex extractors
  models.py             # Response dataclasses
templates/              # Bundled invoice2data templates
tests/                  # pytest suite
Dockerfile              # python:3.11-slim + tesseract / libheif
```

## Endpoints

- `GET /health` — readiness probe (also wired into the Docker
  `HEALTHCHECK`). Reports loaded-templates inventory.
- `POST /parse` — `multipart/form-data` with a `file` part (`.pdf`,
  `.jpg`, `.jpeg`, `.png`, `.heic`) and an optional `kind=expense|income`
  form field. Returns the per-field extraction JSON.

## Pipeline

```
            request body bytes
                   │
        ┌──────────▼──────────┐
        │ text_extractor      │  text-layer → OCR fallback
        └──────────┬──────────┘
                   │ raw text
        ┌──────────▼──────────┐
        │ field_extractor     │  drives Stage 2
        └──────┬───────┬──────┘
               │       │
               ▼       ▼
        heuristics   templates_engine
        (baseline)   (per-vendor enrichment, overlays baseline)
               │       │
               └───┬───┘
                   ▼
                response JSON
```

Templates enrich the heuristic baseline; the response always carries
heuristic values when no template matches.

## Configuration

| Variable | When read | Default | Purpose |
|---|---|---|---|
| `MAX_FILE_MB` | startup | `20` | Per-request upload cap. Changing it requires a container restart. |
| `RECEIPT_SCANNER_SHARED_SECRET` | per request | `""` | When non-empty, `/parse` requires a valid `X-ReceiptScanner-HMAC` signature (see below). Must match `$wgReceiptScannerSidecarSecret` on the wiki side. Rotating the value takes effect on the next request — no restart needed. Leave empty to skip the check (relies on the docker network boundary). |

### Request signing

The `X-ReceiptScanner-HMAC` header carries an HMAC-SHA256, keyed by the
shared secret, over the canonical string `kind + "\n" + filename + "\n"`
followed by the raw file bytes. `filename` is the sanitized multipart
filename (`"` escaped to `%22`, CR/LF stripped). Binding the kind and
filename into the signature stops either from being tampered with without
invalidating it.

## Tests

The suite lives under `tests/` and uses the `pytest.ini` in this
directory, so run from `sidecars/receipt-scanner/`:

```bash
cd sidecars/receipt-scanner
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Fixture-free — every test runs against in-memory inputs or synthetic
strings.

## Adding an invoice2data template

See [`templates/README.md`](templates/README.md).
