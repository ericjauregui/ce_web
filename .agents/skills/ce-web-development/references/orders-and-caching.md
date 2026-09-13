# Orders, exports, and caching

## Source map and permanent constraints

`domains/cart.py` handles cart shaping/exports; `cart_routes.py` checkout/download orchestration; `orders.py` durable SQLAlchemy snapshots/idempotency/email state; `emailing.py` existing Graph delivery. Schema lifecycle uses `migrations/`, `scripts/database.py`, and `scripts/start_render.sh`.

Orders never record prices, currency, unit prices, amounts, or line totals, including nested metadata. Historical migrations may contain removed columns; retain migration history and add proper revisions.

Keep internal identity/UUID separate from readable numbers such as `#CE00000001`. Store address components individually. Distinct-item counts differ from total quantities.

## Durability and retry behavior

- Commit order and all line-item snapshots atomically before email.
- Persistence failure retains the cart and returns a retryable error, not success.
- Matching retries on the same idempotency key return the saved order without duplicate writes/email. Reusing an accepted key with changed payload conflicts.
- Email failure leaves the order committed. Persisted transport acceptance does not guarantee inbox delivery.
- Downloads use saved snapshots and private access checks. Do not reconstruct historical orders from mutable catalog data or put customer records in signed client cookies.
- PostgreSQL has no production local-file fallback; SQLite is explicitly test-only.

## Exports

Country helpers in `domains/cart.py` abbreviate countries in CSV/PDF as ISO alpha-3, e.g. `USA`, `MEX`. Preserve friendly input labels; abbreviation is an export concern.

ReportLab PDFs include the company logo, centered Order Summary, customer summary, item images/table, and counts/quantities. Render a temporary synthetic export for layout changes; extraction alone cannot prove no clipping/wrapping. Never place private exports in `static/`.

## Cache policy

`domains/cache_control.py` is the authority:

| Response | Policy |
| --- | --- |
| Static asset with matching current content fingerprint | Public, one year, immutable |
| Unversioned or mismatched static version | Public, five minutes, must revalidate |
| Cart-aware HTML, APIs, checkout, confirmations, private exports, errors | Private, no-store |
| Explicit public metadata/staff contact routes | Endpoint-specific public lifetimes |

Arbitrary `?v=` does not justify immutable caching. Nested CSS images/fonts and direct reel URLs need their actual policy checked. Render Common static files includes CSV/PDF; public placement is unsafe for private exports regardless of headers. Existing convention is Common static files, not All files.

## Operational pointers

Read `docs/postgres-deployment.md` for Render setup, variable names, migrations, and verification; read `docs/persistence-audit.md` for reliability/cache work. Do not duplicate secrets or old dashboard state into skill notes.

`scripts/start_render.sh` migrates before Gunicorn. `uv run python -m scripts.database check` validates connection/schema; `verify --order-number '#CE00000001'` checks counts without customer records. Migration writes to the configured database: establish the intended environment first.

Email outbox/retry workers and authenticated staff order administration are follow-up ideas, not completed features. Crashes between commit and email can leave delivery pending; reconcile before resending. Consult the audit for current limitations.
