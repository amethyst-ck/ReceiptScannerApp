<?php
/**
 * ReceiptScanner operator settings for a Canasta install.
 *
 * Drop into `<instance>/config/settings/global/Settings.php`. Loads
 * every extension ReceiptScanner depends on, the ReceiptScanner
 * extension itself, and the companion extensions. Starter wiki content
 * is installed separately by the deployer (Wicker).
 *
 * Single source of truth — listing the loads + their related config
 * here (instead of via `canasta extension enable` + scattered files)
 * keeps the stack reproducible from one file in the repo.
 *
 * Requires the following extensions (all Canasta-bundled except
 * ReceiptScanner itself, which Wicker installs from this app's
 * extensions/ directory per the wicker.yaml manifest):
 *   - PageForms, Cargo, ParserFunctions (extension deps)
 *   - DisplayTitle, TitleIcon (page-presentation companions)
 *   - PdfHandler (PDF thumbnails — Ghostscript + poppler ship in the
 *     stock Canasta image)
 *   - TemplateStyles (lets {{User receipts}} ship its own CSS)
 *   - CreateUserPage (auto-creates User: pages on first login)
 *   - ReceiptScanner (this project)
 */

// ---- MediaWiki dependencies of the ReceiptScanner extension ----

wfLoadExtension( 'PageForms' );
wfLoadExtension( 'Cargo' );
wfLoadExtension( 'ParserFunctions' );

// ---- Page-presentation companions ----

// DisplayTitle: each Expense / Income page sets {{DISPLAYTITLE:…}} to a
// human-readable date / party / amount instead of the 9-digit page name.
// Both knobs are needed when the extension is loaded — $wgAllowDisplayTitle
// defaults true in MW core, but the extension re-checks it; and
// $wgRestrictDisplayTitle = false lets a title differ from the page name
// (the default true mode requires they match after normalization).
wfLoadExtension( 'DisplayTitle' );
$wgAllowDisplayTitle = true;
$wgRestrictDisplayTitle = false;
// Hide the auto-subtitle ("Redirected from … / X displays as …") that
// DisplayTitle adds by default — the H1 already shows the DISPLAYTITLE.
$wgDisplayTitleHideSubtitle = true;

// Open external links (including the receipt-thumbnail link on Expense /
// Income pages) in a new tab. The thumb is rendered via external-link
// wikitext [URL <image>] so the reader doesn't lose the entry page when
// zooming into the receipt.
$wgExternalLinkTarget = '_blank';

// Vector 2022 emits `<meta name="viewport" content="width=1120">` by
// default, which forces phones to render the page as if the viewport
// were a 1120-CSS-pixel desktop — every @media (max-width: 720px) rule
// in the extension's stylesheets is dead because the viewport is
// always 1120. Enabling Vector's responsive mode switches the tag to
// `width=device-width, initial-scale=1` and the dashboard tiles,
// receipt-entry layout, and form-input stacking all start working
// at phone widths.
$wgVectorResponsive = true;
// Vector's own opt-in for wrapping tables in a horizontally-scrolling
// container when they don't fit. Complements our .rs-ledger-scroll
// (which targets the ledger results / rollup tables explicitly) by
// catching any tables we haven't wrapped ourselves — including
// PageForms' formtable and the Special:ReceiptReview wikitables.
$wgVectorWrapTablesTemporary = true;

// TitleIcon: emoji / image next to the page heading on Expense / Income
// pages. The starter content (Category:Expenses, Category:Income) sets
// the icons via {{#titleicon_unicode:…}}; TitleIcon propagates them down
// to the categorized pages.
wfLoadExtension( 'TitleIcon' );

// PdfHandler: page-1 thumbnails for the receipt-form preview.
// Ghostscript + poppler-utils ship in the stock Canasta image.
wfLoadExtension( 'PdfHandler' );

// TemplateStyles: lets {{User receipts}} (and any other operator-
// supplied template) ship its own CSS via <templatestyles src="…" />.
wfLoadExtension( 'TemplateStyles' );

// ---- ReceiptScanner ----

wfLoadExtension( 'ReceiptScanner' );

// Sidecar reachable by service DNS at its name — Canasta deploys the
// `receipt-scanner` sidecar (declared in wicker.yaml) on the same network
// (Compose) or as a Service (Kubernetes).
$wgReceiptScannerSidecarUrl = 'http://receipt-scanner:8000';

// Optional shared secret. When non-empty, every /parse request is
// signed with HMAC-SHA256 over kind + "\n" + filename + "\n" + file
// bytes (so a tampered kind or filename also fails); the sidecar
// rejects mismatching requests with 401. Both sides read it from the
// RECEIPT_SCANNER_SHARED_SECRET env var (the sidecar from its container
// env, the wiki from getenv here). Leave the env var unset to disable
// signing when the network boundary is the only control you need.
$wgReceiptScannerSidecarSecret = getenv( 'RECEIPT_SCANNER_SHARED_SECRET' ) ?: '';

// Allow PDF + image MIME types the parser handles (extends MW core's
// stock $wgFileExtensions; do not replace).
$wgFileExtensions = array_values( array_unique( array_merge(
	$wgFileExtensions ?? [],
	[ 'pdf', 'jpg', 'jpeg', 'png', 'heic' ]
) ) );

// MediaWiki ships no handler for image/heic. Pointing the default
// BitmapHandler at it gets thumbnails generating (the ImageMagick
// convert path handles HEIF via libheif, present on the Canasta
// image) — but the size-detection inside BitmapHandler uses PHP's
// getimagesize(), which can't read HEIF, so every upload would land
// in the image table with width=height=0 and no thumbnail would
// render. HeicHandler delegates getSizeAndMetadata to ImageMagick's
// `identify`, which IS HEIF-aware. .heif covers the same code path
// for cameras that report image/heif.
$wgMediaHandlers['image/heic'] = MediaWiki\Extension\ReceiptScanner\HeicHandler::class;
$wgMediaHandlers['image/heif'] = MediaWiki\Extension\ReceiptScanner\HeicHandler::class;

// ---- Permissions ----

// Let regular users delete pages — most importantly mis-uploaded receipt
// files via the "Delete file" button on Special:UnlinkedFiles. Deletions
// stay recoverable by sysops through Special:Undelete.
$wgGroupPermissions['user']['delete'] = true;

// ---- Branding ----

// Wiki logo and favicon, shipped in the app's public_assets/ (copied into
// the instance by Wicker). Canasta serves public assets at /public_assets/;
// an Apache rewrite maps that to the per-wiki dir public_assets/<wiki-id>/,
// so reference the files without the wiki-id — it is injected by the rewrite.
// Header logo is the two-tone "RS" lettering; the amethyst "RS" tile is the
// favicon/app icon. Vector 2022 draws the header mark from `wordmark`; `1x`
// is the fallback for other skins.
$wgLogos = [
	'wordmark' => [
		'src'    => '/public_assets/logo.png',
		'width'  => 54,
		'height' => 48,
	],
	'1x'       => '/public_assets/logo.png',
];
$wgFavicon = '/public_assets/favicon.ico';

// ---- CreateUserPage ----

// Auto-create the User: page on first login with the per-user receipts
// summary template (Template:User receipts ships in the starter content).
wfLoadExtension( 'CreateUserPage' );
$wgCreateUserPage_PageContent = '{{User receipts}}';
