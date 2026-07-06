# invoice2data templates

Vendor-specific extraction templates used by Stage 2 enrichment.
Templates enrich the generic heuristic baseline — they are not required
for a receipt to parse.

## Adding a template

1. Create a `.yml` file in this directory named for the vendor
   (e.g. `acme-bookkeeping.yml`).
2. Match the [invoice2data template format][i2d]:

   ```yaml
   issuer: <human-readable vendor name>
   keywords:
     - <distinctive string from this vendor's receipts>
     - <second keyword, all must match>
   fields:
     amount: <regex capturing the total>
     date:   <regex capturing the date>
     payee:  <regex capturing the payee>
   options:
     currency: USD
     date_formats:
       - '%Y-%m-%d'
   ```

3. The filename (sans `.yml`) appears as `template:<name>` in the
   per-field `source` marker of the `/parse` response.

4. Rebuild the sidecar so the new file is baked in (templates are
   bundled at image-build time, not live-mounted). How to apply the
   rebuild depends on the orchestrator:

   * **Docker Compose:** `canasta restart` runs `docker compose up -d`
     without `--build`, so it will **not** pick up a changed build
     context. In the instance directory, rebuild the image first, then
     restart:

     ```
     docker compose build receipt-scanner
     canasta restart -i <id>
     ```

   * **Kubernetes:** `canasta restart -i <id>` is enough — the sidecar
     image is rebuilt on each start.

   To test the image in isolation, build from this directory's parent
   (the sidecar build context):

   ```
   docker build -t receipt-scanner:local .   # run from sidecars/receipt-scanner/
   ```

[i2d]: https://github.com/invoice-x/invoice2data#templates

## When to add a template

Don't template every vendor. Start with no templates, identify
recurring vendors where the generic heuristics get the wrong answer or
partial answers, and add a template per such vendor.

One-off vendors don't need templates — the generic baseline is good
enough, and the user reviews everything anyway.
