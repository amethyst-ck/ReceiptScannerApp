# Starter wiki content

The wiki pages the ReceiptScanner form needs to function. These are
seed content — the deployer creates them once, then users adapt them.
Each file under `pages/` is one page whose path mirrors its title; the
import list lives in `content.pages` in [`../wicker.yaml`](../wicker.yaml).
See the [Wicker docs](https://github.com/amethyst-ck/Wicker#application-layout)
for the layout convention.

## What the pages do

- **`Template/Expense`, `Template/Income`** — the Cargo `Expenses` /
  `Income` table declarations plus the rendered entry display.
- **`Form/Expense`, `Form/Income`** — the PageForms forms used to
  review and edit an entry.
- **`Project/Expense categories`, `Project/Income categories`** — the
  hierarchical category vocabularies.
- **`Template/Receipt dashboard`** (+ `…/styles.css`) — the six-tile
  launcher grid (Upload / New expense / New income / Review / Ledger /
  Unlinked files). Embedded on `Main Page` via `{{Receipt dashboard}}`.
- **`Template/User receipts`** (+ the two `…row…` sub-templates and
  `…/styles.css`) — a per-user Cargo-query summary for `User:` pages
  (pair with CreateUserPage).
- **`Template/Receipt entry/styles.css`** — TemplateStyles CSS shared
  across rendered Expense / Income pages.
- **`Category/Expenses`, `Category/Income`** — container categories
  populated automatically by the templates.
- **`Help/Receipts`** — user-facing help.
- **`Main Page`** — front-page seed embedding the dashboard.
- **`MediaWiki/Pf formedit edittitle`** — overrides PageForms' form-edit
  page title so it reads "Edit Expense: …" instead of the raw page name.

## Keep the Expense / Income pairs in sync

`Form/Expense` ↔ `Form/Income` and `Template/Expense` ↔ `Template/Income`
are near-identical pairs — each sibling differs only in a few per-kind
values: the party label/column (`payee` ↔ `payer`), the Cargo table
(`Expenses` ↔ `Income`), the category vocabulary page, and kind-specific
prose. When you edit one, mirror the change into its sibling so the two
don't drift.

## Cargo tables

The `Expenses` / `Income` Cargo tables are created from the imported
templates by `cargoRecreateData` (run as a `content.postInstall` step,
and re-run after any later edit to a `Template:Expense` / `Template:Income`
Cargo schema — see the repo README's *Operating* section).
