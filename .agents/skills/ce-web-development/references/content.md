# Catalog and trade-show content

## Catalog identity and copy

`catalog/products.json` owns inventory; `catalog/collections.json` owns ordering/labels. `domains/catalog.py` loads, normalizes, and searches them; `domains/homepage.py` assembles homepage context.

User-established copy constraints:

- Unique name and unique description for every product, not merely every visual style.
- ASCII-only names/descriptions with no accents or embedded item codes. Keep SKU in its separate field/badge.
- Concise wholesale-oriented copy grounded in supplied images/data. Preserve bilingual English/Spanish search through tags without rendering tag lists in cards.
- Preserve codes, images, collections, ordering, and original tags during copy-only rewrites. Recount current records; do not hardcode historical counts.

After bulk edits, verify uniqueness, ASCII text, no embedded codes, and asset existence. Prior search examples: `corazon`, `mariposa`, `Virgen de Guadalupe`, `zirconia cubica`, `joyeria al por mayor`.

The label is `Telephone Earrings`, not `Drop Earrings` or abbreviated `Telephones`. Preserve `telephone-earrings` and `#section-telephone-earrings`. Trade-show cards have independent `label` overrides; changing collections alone will not update them.

## Reusable events

Use `catalog/trade_shows.json` -> `domains/trade_shows.py` -> `templates/trade_shows.html`. `active_event` selects from `events`; avoid separate hardcoded templates per event. Check current registration in `domains/site_routes.py` rather than assuming every event key has a route.

- Dates/display dates, venue, booth, official URLs, logos, hero/mobile hero, curated products, optional video belong in event data.
- Curated entries resolve actual product codes and existing images, link to collections, and may override displayed names using `label`.
- Reuse official/supplied show logos and existing brand assets; do not invent organizer marks or substitute unrelated jewelry.
- `static/css/styles/trade_shows.css` owns styling. `.trade-show-collection-intro` shares the contact panel's gold border, rounded corners, and radial glow.
- The mini-card request was interpreted as wrapping the collection heading, description, and Browse Catalog button. It is not a new lead form. Clarify the target if future requests refer to unspecified “text boxes.”
- Current contact content links to email/WhatsApp and includes shared contact details. No submitted lead form/database lead workflow is implemented.
- `static/js/trade_shows.js` handles calendar export, owner-video visibility playback, and the mobile booth/message bar. Preserve the calendar's exclusive end date and bar suppression during relevant contact/editing/menu states.

## SEO and assets

Use `asset_url(...)` for template-linked static resources. Fingerprints are now content-derived in `domains/file_cache.py`; old timestamp-based assumptions are stale.

Canonical origin uses `SITE_BASE_URL` when configured. Search URLs canonicalize to `/`; private order routes are not SEO landing pages. Inspect `domains/seo.py`, `templates/base.html`, and per-page schema when changing URLs, names, dates, or share assets.

Use `catalog_start` for generic catalog entry links where appropriate, while preserving collection-specific anchors for contextual return links.
