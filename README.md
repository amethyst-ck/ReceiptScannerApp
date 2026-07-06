# ReceiptScanner

OCR-driven receipt entry for a private MediaWiki / Canasta wiki.
Receipts uploaded by users are parsed by a Python sidecar, pre-filled
into a PageForms form, and stored in Cargo tables (`Expenses` and
`Income`) that drive a built-in ledger view.

## What the extension provides

- **`Special:UploadReceipt`** — single or bulk upload that enqueues each
  file for the sidecar to parse.
- **`Special:ReceiptReview`** — triage queue: Pending / Processing /
  Ready / Failed. Ready rows offer Toggle, Reprocess, Review-in-form,
  and Dismiss; Failed rows offer Retry. (Consumed is an internal
  terminal state and is not shown.)
- **`Special:Ledger`** — combined Expenses + Income view with date /
  amount / category / kind / notes filters, per-category and per-month
  rollups, CSV export, a printable Schedule-C-style summary view, and
  bulk category / assignee / party edits.
- **`Special:UnlinkedFiles`** — files in the wiki that don't appear in
  any Expense or Income page; one-click re-enqueue or delete.
- **`Expense` and `Income` namespaces** registered automatically (index
  3000–3003 by default, configurable via
  `$wgReceiptScannerNamespaceIndex`).
- Parser functions for the form / template layer:
  `{{#receiptscanner_categories:}}`, `{{#receiptscanner_users:}}`,
  `{{#receiptscanner_currency_symbol:}}`,
  `{{#receiptscanner_format_amount:}}`,
  `{{#receiptscanner_system_currency:}}`,
  `{{#receiptscanner_truncate:}}`,
  `{{#receiptscanner_dashboard:}}`,
  `{{#receiptscanner_form_actions:}}`,
  `{{#receiptscanner_file_url:}}`.

See the [ReceiptScanner extension README](https://github.com/amethyst-ck/ReceiptScanner)
for install, configuration, and the full parser-function reference.

## What the sidecar provides

A Flask service exposing `POST /parse` (multipart) that runs OCR via
Tesseract, then a layered extraction pipeline (per-vendor
invoice2data templates with a heuristic fallback) to return total,
subtotal, tax, fees, date, currency, and party (payee for expenses,
payer for income). See
[`sidecars/receipt-scanner/README.md`](sidecars/receipt-scanner/README.md).

## Getting started

Pre-reqs on the host: `canasta` (CLI 4.9.1 or above), `docker`, `python3`,
`git`, and a checkout of
[Wicker](https://github.com/amethyst-ck/Wicker) (run as `./wicker`, or put it on
your `PATH`).

Clone this repo, then run `wicker deploy` from the directory you cloned into.
Its first positional argument is the app directory — the one holding
`wicker.yaml` — a local path, not a URL. `-n` is the instance domain (required,
one per wiki; ReceiptScanner is single-wiki, so pass one):

```
wicker deploy ReceiptScannerApp -i rsdev -n localhost
```

The instance is created under the current directory as `./rsdev`; the `-p`
parent directory defaults to `.` (matching `canasta create`), so pass
`-p <dir>` only to place it elsewhere. That builds the derived web image,
creates the instance, installs the extension + settings, declares the
`receipt-scanner` sidecar, imports the starter content, and creates the Cargo
tables — leaving a working `http://localhost/wiki/Main_Page`. Log in as
`WikiSysop` using the password in `./rsdev/admin-password_main`.

Preview the steps without touching Docker or canasta with `--dry-run`.
See the [Wicker README](https://github.com/amethyst-ck/Wicker) for flags
(`-n/--domain-name`, `-p/--path`, `-o/--orchestrator`, `--var`, `--secret`,
`--skip-build`).

### Request signing (optional)

The wiki and the sidecar can authenticate `/parse` requests with a shared
HMAC secret. To enable it, provide a value at deploy time:

```
wicker deploy ReceiptScannerApp -i rsdev -n localhost \
  --secret RECEIPT_SCANNER_SHARED_SECRET=<value>
```

(or export `RECEIPT_SCANNER_SHARED_SECRET` before deploying). The manifest
declares it as a `secrets:` entry targeting both the wiki and the sidecar, so
Wicker delivers the same value to each — on Kubernetes via a per-instance
Secret (`secretKeyRef`), on Compose via the gitignored `.env`. Leave it unset
to skip signing and rely on the container network boundary. The mechanism is
documented in the
[sidecar](sidecars/receipt-scanner/README.md) and
[extension](https://github.com/amethyst-ck/ReceiptScanner) READMEs.

## Operating

Re-run `cargoRecreateData.php` after any later edit to the
`Template:Expense` / `Template:Income` Cargo schema (until it runs, the
`#cargo_store` calls silently no-op and `Special:Ledger` is empty):

```
canasta maintenance extension -i <id> -w main Cargo:cargoRecreateData --table=Expenses
canasta maintenance extension -i <id> -w main Cargo:cargoRecreateData --table=Income
```

## License

GPL-2.0-or-later (matches MediaWiki).
