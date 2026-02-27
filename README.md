# California Earrings (Flask Catalog)

## Project structure

```text
ce_web/
├── app.py
├── catalog/
├── domains/
│   ├── cart.py
│   ├── catalog.py
│   ├── emailing.py
│   ├── seo.py
│   └── team.py
├── static/
├── templates/
└── tests/
	├── e2e/
	└── ...
```

- `app.py`: Flask app entrypoint and route orchestration.
- `domains/`: domain logic modules (catalog, cart, team, seo, email).
- `catalog/`: JSON content source (products, collections, social, team).
- `static/` and `templates/`: frontend assets and Jinja templates.
- `tests/`: unit/contract tests plus Playwright E2E tests.

## Setup (uv)

Install dependencies:

```bash
uv sync
```

Install dev tooling (Playwright + pre-commit):

```bash
uv sync --extra dev
uv run python -m playwright install chromium webkit
```

## Key features
- SEO basics (titles, meta descriptions, Open Graph)
- Collections/sections (configured in `catalog/collections.json`)
- Responsive 2–4 column product grid with tap-to-expand description drawers
- Catalog interactions are maintained in `static/js/catalog.js`
- Search controls (`?q=...`)
- Sitemap + robots.txt
- Optional free analytics via env vars (Plausible or GoatCounter)
- Optional QR codes pointing customers to the catalog homepage

## Managing products
Edit `catalog/products.json`.

Recommended fields per product:
- `code`, `name`, `collection`
- `description`
- `tags` (for search)

### Collections
Edit `catalog/collections.json`:
- `order`: list of collection keys in desired order
- `labels`: mapping key -> display label

## Free analytics (optional)
Set ONE of these environment variables on Render:
- `PLAUSIBLE_DOMAIN=californiaearrings.com`
- OR `GOATCOUNTER_URL=https://YOURACCOUNT.goatcounter.com/count`

## Link preview thumbnail (Open Graph)
To show an image thumbnail when sharing links in iMessage, WhatsApp, Instagram DMs, etc., set:

- `SITE_BASE_URL=https://californiaearrings.com`

This ensures Open Graph/Twitter image URLs are absolute and crawlable.

## QR codes (optional)
Generate QR codes for catalog discovery:

```bash
uv run python scripts/generate_qr_codes.py --base-url https://californiaearrings.com
```

This writes QR images to `static/qr/`.


## Social reels (TikTok embeds)
Edit `catalog/social.json`:
- `tiktok.profile_url`
- `tiktok.videos` (list of TikTok video URLs)
- `instagram.profile_url`

Note: autoplay behavior is controlled by TikTok/Instagram and may require user interaction on some devices.

## Meet the team
Edit `catalog/team.json` to add members.
Optionally add headshots to `static/team/` and set `photo` to the filename.

## Automated tests
Run API smoke tests with:

```bash
uv run python -m unittest discover -s tests
```

## Browser E2E UX tests (Playwright)
Install optional dev dependencies and browser engines:

```bash
uv sync --extra dev
uv run python -m playwright install chromium webkit
```

Run browser UX tests:

```bash
uv run python -m unittest discover -s tests/e2e -p "e2e_*.py" -t .
```

These tests cover navbar/search centering stability, category chip/CTA alignment contracts, resize/scroll resilience, and lazy-loading hints for catalog images.

## Pre-commit hook (comprehensive suite)

Install and enable:

```bash
uv run pre-commit install
```

Manual run (optional):

```bash
uv run pre-commit run --all-files
```

Current hooks behavior:

- Runs unit/contract tests on every commit.
- Runs Playwright E2E only on branch `dev`.
- Skips Playwright E2E on non-`dev` branches.

Commands used by hooks:

```bash
uv run python -m unittest discover -s tests
CE_REQUIRE_E2E=1 uv run python -m unittest discover -s tests/e2e -p "e2e_*.py" -t .
```

If Playwright/browsers are missing, commit will fail until you run:

```bash
uv sync --extra dev
uv run python -m playwright install chromium webkit
```
