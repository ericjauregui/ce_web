# California Earrings

Flask-based wholesale jewelry site for California Earrings. The app serves a server-rendered luxury wholesale catalog, product pages, reels landing page, team/contact pages, FAQ content, and a session-backed order workflow for buyers worldwide.

## What the app does

- Renders the wholesale catalog at `/` with in-page collection sections and query-driven inventory search.
- Serves product detail pages at `/product/<product_code>` with canonical redirects, product schema, and share-friendly metadata.
- Surfaces the latest short-form inventory videos on the homepage and the full reels experience at `/reels`.
- Supports a session-backed cart and inquiry checkout flow with CSV/PDF order exports.
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
- `domains/emailing.py`: optional SMTP order email delivery.

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

Optional:

- `PORT`: local bind port. Defaults to `5001`.
- `FLASK_DEBUG`: set to `1` to enable Flask debug mode.
- `SITE_BASE_URL`: public canonical base URL used for sitemap entries, canonical URLs, and absolute OG image links.
- `PLAUSIBLE_DOMAIN`: enables Plausible analytics injection in the base template.

Optional SMTP settings for order emails:

- `SMTP_HOST`
- `SMTP_PORT` with default `587`
- `SMTP_USER`
- `SMTP_PASS`
- `EMAIL_TO`
- `EMAIL_FROM` with fallback to `SMTP_USER`

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

Use the unified runner for the standard route/contract suite:

```bash
uv run python -m tests.run standard
```

Run the Playwright E2E suite:

```bash
uv run python -m tests.run e2e
```

Run everything together:

```bash
uv run python -m tests.run all
```

Useful E2E options:

```bash
uv run python -m tests.run e2e --require-e2e
uv run python -m tests.run e2e --browser webkit
uv run python -m tests.run e2e --headed
uv run python -m tests.run e2e --keep-artifacts
```

Failing E2E tests write screenshots, page HTML, and browser event logs into `.test-artifacts/e2e/` by default.
That directory is cleaned automatically at the start of each new E2E run unless you pass `--keep-artifacts`.

The test suite covers route contracts, metadata endpoints, reels/homepage frontend contracts, and cross-browser E2E layout/resilience behavior, including mobile checkout field behavior.

## Troubleshooting

- If startup fails with `SECRET_KEY env var not set`, define `SECRET_KEY` in your shell or `.env`.
- If canonical URLs or sitemap entries point to localhost in production, set `SITE_BASE_URL` to the public domain.
- If order submission succeeds but no email is sent, confirm the SMTP variables are fully configured.
- If Playwright-based tests are skipped or fail due to missing browsers, run `uv sync --extra dev` and install Chromium/WebKit with Playwright.

## Deployment

`render.yaml` runs the site as a Python web service using `uv sync --frozen` and starts Gunicorn with:

```bash
.venv/bin/gunicorn --bind 0.0.0.0:$PORT app:app
```
