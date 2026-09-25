# California Earrings

Flask-based wholesale jewelry site for California Earrings. The app serves a server-rendered luxury wholesale catalog, product pages, reels landing page, team/contact pages, FAQ content, and a session-backed order workflow for buyers worldwide.

## What the app does

- Renders the wholesale catalog at `/` with in-page collection sections and query-driven inventory search.
- Serves product detail pages at `/product/<product_code>` with canonical redirects, product schema, and share-friendly metadata.
- Surfaces the latest short-form inventory videos on the homepage and the full reels experience at `/reels`.
- Supports a session-backed cart and order checkout flow with CSV/PDF order exports.
- Publishes crawlable marketing/support pages at `/about`, `/contact`, `/faqs`, `/team`, and `/team/<member_slug>`.
- Exposes SEO infrastructure at `/robots.txt`, `/sitemap.xml`, and `/sitemaps.xml`.

## Architecture

The codebase is kept modular so content and feature logic do not accumulate in `app.py`.

- `app.py`: route wiring, session lifecycle, template rendering, and endpoint composition.
- `domains/catalog.py`: catalog loading, normalization, search/filtering, and collection section assembly.
- `domains/homepage.py`: homepage context building and latest-reels selection.
- `domains/reels.py`: reel discovery and shuffled reel lists from `static/reels/`.
- `domains/cart.py`: cart state, item shaping, notes, CSV output, and PDF generation.
- `domains/team.py`: team normalization, slugs, WhatsApp/call links, and vCard generation.
- `domains/faqs.py`: FAQ loading.
- `domains/seo.py`: canonical base URL handling plus sitemap `lastmod` generation.
- `domains/emailing.py`: Microsoft Graph order email delivery and CSV attachments.
- `domains/orders.py`: durable PostgreSQL order snapshots, idempotency, retrieval, and delivery state.
- `domains/cache_control.py`: explicit public asset and private response caching policies.

## Content model

Most site content is JSON-backed and editable without changing templates:

- `catalog/products.json`: product inventory records.
- `catalog/collections.json`: homepage/catalog section ordering and display labels.
- `catalog/faqs.json`: FAQ accordion content and FAQ schema content.
- `catalog/social.json`: TikTok and Instagram profile URLs.
- `catalog/team.json`: team directory data, bios, titles, and contact info.

Static media lives in:

- `static/product_images/`: product photography.
- `static/reels/`: MP4 reels used on the homepage strip and `/reels` page.
- `static/team/`: team photos.

## Key templates and UX surfaces

- `templates/index.html`: homepage hero, catalog sections, and latest inventory reels strip.
- `templates/reels.html`: all-reels landing page with the newer swipe-and-play UX.
- `templates/product_detail.html`: product detail page with product schema.
- `templates/faqs.html`: FAQ accordion plus FAQPage schema.
- `templates/contact.html`: contact page plus local business/contact schema.
- `templates/team.html` and `templates/team_member.html`: team directory and individual contact-card pages.
- `templates/sitemap.xml` and `templates/robots.txt`: SEO endpoint templates.

## Requirements

- Python `>=3.13`
- `uv` for dependency management

Install runtime dependencies:

```bash
uv sync
```

Install development extras:

```bash
uv sync --extra dev
uv run python -m playwright install chromium webkit
```

## Environment variables

`load_dotenv()` is enabled in `app.py`, so variables can come from the shell or a local `.env` file.

Required:

- `SECRET_KEY`: Flask session secret. The app fails fast if it is missing or empty.
- `DATABASE_URL`: Render Postgres **internal** URL, configured only on the web service. Required for checkout and migrations; there is no production local-file fallback. Never put the URL in source control or browser code.

Optional:

- `PORT`: local bind port. Defaults to `5001`.
- `FLASK_DEBUG`: set to `1` to enable Flask debug mode.
- `SITE_BASE_URL`: public canonical base URL used for sitemap entries, canonical URLs, and absolute OG image links.
- `CLOUDFLARE_WEB_ANALYTICS_TOKEN`: overrides the configured Cloudflare Web Analytics token on site pages. The supplied token is enabled by default; set this variable to an empty value to disable it. Do not also enable Cloudflare's automatic snippet injection, which would load analytics twice.
- `/admin/analytics`: public aggregate analytics dashboard. It shows totals and grouped breakdowns; individual session identifiers and journeys are not exposed. The path is excluded from the sitemap and disallowed in `robots.txt`.

Order email settings (preserve the existing Render values):

- `EMAIL_TRANSPORT=graph`
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (existing `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` aliases also work)
- `GRAPH_SENDER_UPN`: mailbox used to send and receive order notifications; `SMTP_USER` is a legacy fallback for this mailbox only.
- `ORDER_BCC_EMAILS`: optional comma-separated staff recipients.
- `ORDER_EMAIL_MAX_RETRIES`, `ORDER_EMAIL_RETRY_DELAY_SECONDS`, `ORDER_EMAIL_REQUEST_TIMEOUT_SECONDS`: optional transport tuning; existing defaults are conservative.

See [PostgreSQL deployment](docs/postgres-deployment.md) for exact Render settings, migrations, verification, and failure recovery, and [persistence audit](docs/persistence-audit.md) for ranked follow-up work.

## Running locally

Set a secret key:

```bash
export SECRET_KEY="dev-secret"
```

Start the development server:

```bash
uv run python app.py
```

Run production-style locally:

```bash
uv run gunicorn --bind 0.0.0.0:5001 app:app
```

## Public routes

Marketing and catalog routes:

- `/`
- `/catalog/` redirect to the first homepage catalog section
- `/product/<product_code>`
- `/reels`
- `/team`
- `/team/<member_slug>`
- `/team/<member_slug>/contact.vcf`
- `/about`
- `/contact`
- `/faqs`
- `/faq` redirect to `/faqs`

Order workflow routes:

- `/cart`
- `/checkout`
- `/download/order/<token>.csv`
- `/download/order/<token>.pdf`

SEO routes:

- `/robots.txt`
- `/sitemap.xml`
- `/sitemaps.xml`

Cart API routes:

- `/api/cart/count`
- `/api/cart/add`
- `/api/cart/set`
- `/api/cart/remove`
- `/api/cart/clear`
- `/api/cart/note`

## SEO and search behavior

- Canonical URLs are built from `SITE_BASE_URL` when present, otherwise from the current request root.
- Search-result URLs like `/?q=...` canonicalize back to `/`.
- Transactional and non-landing routes are excluded from crawling through `robots.txt` and per-page `robots` meta tags.
- The sitemap includes the homepage, FAQ page, reels page, team pages, and all product detail pages.
- Structured data is emitted for organization/site-wide info, product pages, FAQ content, contact/local business info, team members, and collection-style landing pages.
- Public-facing copy is intentionally positioned as worldwide coverage.
- Internal market emphasis and strongest legacy volume currently center on California, Texas, Florida, Puerto Rico, Trinidad, the wider Caribbean, Mexico, and Central America.

## Updating site content

- Add or remove product records in `catalog/products.json`.
- Change collection order or labels in `catalog/collections.json`.
- Update FAQs in `catalog/faqs.json`.
- Drop new MP4 files into `static/reels/` to update the homepage strip and `/reels` page.
- Update team bios/contact details in `catalog/team.json`.
- Refresh social profiles in `catalog/social.json`.

## Tests

Tests are intended to run locally in this repo. No GitHub Actions or other CI workflow is maintained here.

Run the browser E2E suite (the default test command):

```bash
uv run python -m tests.run e2e
```

Run the remaining focused isolated checks only when their specific failure modes matter:

```bash
uv run python -m tests.run standard
```

Run everything together:

```bash
uv run python -m tests.run all
```

Useful E2E options:

```bash
uv run python -m tests.run e2e --browser webkit
uv run python -m tests.run e2e --headed
uv run python -m tests.run e2e --keep-artifacts
uv run python -m tests.verify_e2e_artifacts --check-source
```

Every E2E test writes a screenshot, rendered HTML, browser event log, and SHA-256 evidence record into `.test-artifacts/e2e/`. The runner writes a run manifest with the source fingerprint and evidence hashes. The E2E command fails if Playwright or browser binaries are missing.
That directory is cleaned automatically at the start of each new E2E run unless you pass `--keep-artifacts`.

The browser suite covers customer workflows, route behavior, and cross-browser layout/resilience. Focused isolated checks remain for failure modes a browser cannot reliably expose.

## Troubleshooting

- If startup fails with `SECRET_KEY env var not set`, define `SECRET_KEY` in your shell or `.env`.
- If canonical URLs or sitemap entries point to localhost in production, set `SITE_BASE_URL` to the public domain.
- If a saved order has no email notification, confirm the Graph settings and inspect its delivery status. Do not resubmit the order: PostgreSQL retains it even if notification fails.
- If Playwright-based tests are skipped or fail due to missing browsers, run `uv sync --extra dev` and install Chromium/WebKit with Playwright.

## Deployment

### Responsive product images and lossless hero assets

Homepage heroes use smaller, full-resolution lossless WebP copies when available.
All catalog and curated trade-show product photos also have proportional 160,
320, 480, 640, and 960px variants where smaller than the original. Thumbnail
surfaces use `srcset` and `sizes` to select a suitable resolution for the rendered
size and screen density. Resizing uses Lanczos followed by lossless WebP encoding;
images are never stretched, cropped, or upscaled by the generator. Originals
remain authoritative for product details, exports, and full-resolution fallback.
After changing source product/hero images, fonts, or the background logo, regenerate
the alternatives and nested CSS fingerprints:

```bash
uv run python -m scripts.optimize_images
uv run python -m unittest tests.test_image_assets
```

Commit the generated `static/optimized/` files and CSS changes with the source
changes. Generation verifies lossless encoding against each resized intermediate
(or the full-resolution source for hero/original alternatives) and keeps only
smaller files. `responsive-manifest.json` records dimensions and content versions.
Missing/modified candidates are omitted; stale source entries fall back to the
original automatically. `sizes="auto, ..."` uses the measured lazy-image slot on
supporting browsers, with CSS breakpoint/width fallbacks for other browsers.
This is an offline maintenance step, not a request-time image conversion or a new
Render build requirement. See [responsive image results](docs/audits/2026-09-20-responsive-images.md)
and the [earlier lossless optimization results](docs/audits/2026-09-20-speed-implementation.md).

### Render

`render.yaml` installs with `uv sync --frozen` and starts the migration-gated web service with:

```bash
sh scripts/start_render.sh
```

Configure `DATABASE_URL` from the existing Render database's internal URL before deploying. The start script applies Alembic migrations and starts one Gunicorn worker with two threads. See [deployment and production verification](docs/postgres-deployment.md) for the complete runbook and Cache-Control table.

### Video previews and blocking CSS

Reel previews use real frames extracted at 0.08 seconds, encoded as lossless WebP.
After adding or replacing MP4 files, run `uv run python scripts/build_reel_posters.py`
(requires FFmpeg and Pillow), and include `static/reels/posters/` in the deployment.
Video fingerprints prevent a replaced clip from using an old poster. Missing posters
fall back to extracting a frame in the browser only near the viewport. Visible active
reels retain muted autoplay; other clips load on activation.

On the homepage, `catalog_images.js` limits product and collection-thumbnail
requests to visible images while the hero is downloading, then enables a 400px
look-ahead. Scrolling or selecting a category enables look-ahead immediately;
category clicks also prepare the first four destination images. Image sources,
responsive candidates, and catalog text remain server-rendered, with native
image markup in `noscript` for visitors without JavaScript. Reel posters reuse
the same image bytes through a low-priority image request; offscreen poster
look-ahead resumes after the hero. Visible autoplay is unchanged.

After changing templates, application modules, JavaScript, or custom CSS, run:

```sh
uv run --with tinycss2 python scripts/build_site_css.py
```

Include `static/css/bootstrap.site.min.css` and its manifest. This preserves Bootstrap
rule order and declarations, conservatively retaining functional selectors and framework
states. If its source inventory or output changes without rebuilding, the app serves the
original Bootstrap stylesheet. This is an offline optimization; no extra production
package or CSS build step is required. Keep the original vendor stylesheet for fallback.

Catalog drawers measure their contents when opened, instead of measuring all products
on startup. Fixed-aspect-ratio product image wrappers use `content-visibility: auto`;
product text, controls, section anchors, and document structure stay available.

### Quality-first hero compression

The homepage uses full-resolution quality-98 WebP copies of its three existing hero
compositions. No resizing, cropping, breakpoint, CSS background positioning, or viewport
changes are involved. `cwebp -sharp_yuv` preserves color edges more accurately during
conversion. Encoding is lossy; the originals and earlier lossless alternatives remain
available, and stale/missing/corrupt optimized heroes fall back automatically.

After editing a source hero, run `uv run python -m scripts.optimize_heroes` (requires
libwebp's `cwebp` and Pillow), visually review jewelry edges/dark texture at mobile,
tablet, desktop, and high-density sizes, then rebuild the CSS manifest if its inputs
changed. Include `static/optimized/heroes/` and `hero-manifest.json` in deployment.
The generator verifies unchanged dimensions/metadata and a conservative pixel-error
limit; this numerical guard does not replace visual review. Both preload URLs and
background URLs use the same fingerprinted hero helper to avoid duplicate requests.

### Server-side image metadata cache

Image URLs and responsive candidate sets are cached per worker, with bounded,
thread-safe storage. Each request checks the three manifest file stamps once and
checks the relevant source/derivative file stamps before reusing a selection.
Fingerprint validation and URL generation repeat only when inputs change. Repeated
uses of an image within one request share the same selection. This preserves the
existing missing/corrupt/stale-image fallbacks without caching customer HTML or carts.

`warm_runtime_caches()` prepares catalog image metadata and hero URLs when the app
loads, before the production worker accepts traffic. Warmup is best-effort; normal
requests populate any missing entries. Changes published through the asset-generation
scripts (which update file timestamps and manifests) invalidate the cache automatically.
URL caches also separate different static URL/mount prefixes. No new service, database
cache, environment setting, or frontend change is required.
