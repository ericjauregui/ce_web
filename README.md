# California Earrings (Flask Catalog)

JSON-backed wholesale product catalog built with Flask and server-rendered templates.

## Architecture overview

This repository is a modular Flask monolith:

- `app.py` wires routes, session state, template rendering, and domain services.
- `domains/` holds business logic split by concern:
	- `catalog.py`: product normalization, loading, filtering, and section building
	- `cart.py`: cart/session normalization, notes, CSV/PDF generation
	- `team.py`: team-member shaping, slug generation, WhatsApp links, vCard output
	- `seo.py`: canonical URL and sitemap URL/lastmod generation
	- `emailing.py`: SMTP order-email delivery with CSV attachment
- `catalog/` stores editable content (`products.json`, `collections.json`, `social.json`, `team.json`).
- `templates/` contains Jinja views for catalog, product detail, cart/checkout, and SEO pages.
- `static/` contains CSS, JS, images, logos, and team photos.
- `tests/` contains HTTP contract tests and Playwright E2E UX tests.

## Project structure

```text
ce_web/
├── app.py
├── pyproject.toml
├── render.yaml
├── catalog/
│   ├── products.json
│   ├── collections.json
│   ├── social.json
│   └── team.json
├── domains/
│   ├── cart.py
│   ├── catalog.py
│   ├── emailing.py
│   ├── seo.py
│   └── team.py
├── static/
│   ├── css/
│   ├── js/
│   ├── assets/
│   ├── product_images/
│   └── team/
├── templates/
│   ├── index.html
│   ├── product_detail.html
│   ├── cart.html
│   ├── checkout.html
│   ├── team.html
│   ├── team_member.html
│   └── sitemap.xml
└── tests/
    ├── test_*.py
    └── e2e/
        └── e2e_*.py
```

## Runtime behavior

- Catalog/search page is rendered at `/` with optional query `?q=...`.
- Product detail page is rendered at `/product/<product_code>` with canonical-code redirect support.
- Cart state is session-backed and modified via `/api/cart/*` endpoints.
- Checkout (`/checkout`) stores an order snapshot in session and supports CSV/PDF download links.
- Team pages are generated from `catalog/team.json` and include downloadable contact cards (`.vcf`).
- SEO endpoints include `/robots.txt`, `/sitemap.xml`, and `/sitemaps.xml`.

## Requirements

- Python `>=3.13`
- `uv` for dependency management

Install runtime dependencies:

```bash
uv sync
```

Install development extras (Playwright + pre-commit):

```bash
uv sync --extra dev
uv run python -m playwright install chromium webkit
```

## Environment variables

`app.py` calls `load_dotenv()`, so variables can be provided via shell env or a local `.env` file.

Required:

- `SECRET_KEY`: Flask session secret (app fails fast if missing/empty)

Optional:

- `PORT`: server port (default `5001` when running `python app.py`)
- `FLASK_DEBUG`: set to `1` for debug mode
- `SITE_BASE_URL`: canonical public base URL for sitemap and absolute OG image links
- `PLAUSIBLE_DOMAIN`: enables Plausible script injection in base template

Order email delivery (optional; send is skipped if incomplete):

- `SMTP_HOST`
- `SMTP_PORT` (default `587`)
- `SMTP_USER`
- `SMTP_PASS`
- `EMAIL_TO`
- `EMAIL_FROM` (defaults to `SMTP_USER`)

## Running locally

Set a secret key (or place it in `.env`):

```bash
export SECRET_KEY="dev-secret"
```

Start the app:

```bash
uv run python app.py
```

Or run production-style locally:

```bash
uv run gunicorn --bind 0.0.0.0:5001 app:app
```

## Managing catalog content

- Edit `catalog/products.json` for product records.
	- Typical fields: `code`, `name`, `collection`, `description`, `image`, `tags`
- Edit `catalog/collections.json` for section ordering/labels.
	- `order`: ordered list of collection keys
	- `labels`: map of collection key -> display label
- Edit `catalog/social.json` for TikTok/Instagram profile/video links.
- Edit `catalog/team.json` for team cards/profile pages.

## Key routes

Page routes:

- `/`
- `/catalog/`
- `/product/<product_code>`
- `/cart`
- `/checkout` (`GET`, `POST`)
- `/download/order/<token>.csv`
- `/download/order/<token>.pdf`
- `/team`
- `/team/<member_slug>`
- `/team/<member_slug>/contact.vcf`
- `/about`
- `/contact`
- `/robots.txt`
- `/sitemap.xml` and `/sitemaps.xml`

Cart API routes:

- `/api/cart/count` (`GET`)
- `/api/cart/add` (`POST`)
- `/api/cart/set` (`POST`)
- `/api/cart/remove` (`POST`)
- `/api/cart/clear` (`POST`)
- `/api/cart/note` (`POST`)

## Tests

Run unit/contract tests:

```bash
uv run python -m unittest discover -s tests
```

Run E2E tests:

```bash
uv run python -m unittest discover -s tests/e2e -p "e2e_*.py" -t .
```

E2E tests cover nav/search layout stability, resize/scroll resilience, and core catalog UX contracts in Chromium and WebKit.

## Pre-commit hooks

Install hooks:

```bash
uv run pre-commit install
```

Run manually:

```bash
uv run pre-commit run --all-files
```

Configured behavior in `.pre-commit-config.yaml`:

- Always runs `python -m unittest discover -s tests`
- Runs Playwright E2E only when current branch is `dev`
- Uses `CE_REQUIRE_E2E=1` on `dev` so missing Playwright deps fail the commit

## Troubleshooting

- **App fails at startup with `SECRET_KEY env var not set`**
	- Set `SECRET_KEY` in your shell or `.env` (loaded via `load_dotenv()` in `app.py`).
	- Example: `export SECRET_KEY="dev-secret"`

- **E2E tests are skipped or fail due to missing Playwright/browser binaries**
	- Install dev extras and browsers:
		- `uv sync --extra dev`
		- `uv run python -m playwright install chromium webkit`

- **Order submission works but no email is sent**
	- This is expected when SMTP variables are incomplete.
	- Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`, and optionally `EMAIL_FROM`.

- **Sitemap or OG image URLs show localhost in non-local environments**
	- Set `SITE_BASE_URL` to your public domain (for example `https://californiaearrings.com`).

- **Pre-commit appears to skip Playwright E2E**
	- E2E hooks only run on branch `dev` by design.
	- To force locally: `CE_REQUIRE_E2E=1 uv run python -m unittest discover -s tests/e2e -p "e2e_*.py" -t .`

## Deployment (Render)

`render.yaml` is configured for a Python web service using `uv sync --frozen` and starts with:

```bash
.venv/bin/gunicorn --bind 0.0.0.0:$PORT app:app
```
