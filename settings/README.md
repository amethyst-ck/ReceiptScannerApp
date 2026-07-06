# Operator settings

`Settings.php` is this app's operator config fragment, installed via the
`settings` entry in [`../wicker.yaml`](../wicker.yaml).

## What it sets up

- Loads the ReceiptScanner extension and its MediaWiki dependencies
  (PageForms, Cargo, ParserFunctions).
- Loads the page-presentation companions (DisplayTitle, TitleIcon,
  PdfHandler, TemplateStyles) and CreateUserPage.
- Enables Vector 2022's responsive viewport + table-wrap settings so the
  dashboard / forms / ledger render usefully on phones.
- Registers `MediaWiki\Extension\ReceiptScanner\HeicHandler` for the
  `image/heic` and `image/heif` MIME types so iPhone uploads get
  thumbnails.

## Site-specific overrides

Edit the file inline for per-site values — for example an alternate
sidecar URL (`$wgReceiptScannerSidecarUrl`).

Do **not** inline the HMAC secret. `$wgReceiptScannerSidecarSecret`
reads the `RECEIPT_SCANNER_SHARED_SECRET` environment variable, which is
delivered to both the wiki and the sidecar at deploy time via the
`wicker.yaml` `secrets:` flow (set with `--secret` on deploy).
Hardcoding it here would diverge from the value the sidecar receives.

The full configuration reference is in
[`../extensions/ReceiptScanner/README.md`](../extensions/ReceiptScanner/README.md).
