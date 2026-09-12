# PostgreSQL deployment and verification

## Implemented behavior

Flask remains the application framework. SQLAlchemy and psycopg connect to PostgreSQL using only the server's `DATABASE_URL`. Orders and all line-item snapshots commit in one transaction before any confirmation or email attempt. Database failure returns a generic retryable error and retains the cart. A unique submission key plus payload fingerprint prevents duplicate writes; a changed payload cannot reuse an accepted key. Email failure leaves the order intact. CSV/PDF downloads read saved snapshots with private access checks instead of storing customer data in the signed browser cookie.

Orders never store prices, monetary amounts, or currency. Only item counts and quantities are recorded. Migration `20260912_0002` removes the former monetary columns and monetary metadata keys; the earlier migration remains as historical migration tracking. New confirmation numbers use `#CE00000001` format to avoid collisions with legacy `#00001` numbers. Existing CSV/PDF layouts and Graph notification behavior are retained.

## Tables

| Table | Stored data and constraints |
| --- | --- |
| `orders` | Internal sequence key, UUID, unique order number, unique idempotency key, payload hash, unique download access token, submitted status, UTC created/submitted timestamps, existing name/company/contact fields, separate address_line_1/address_line_2/city/state/postal_code/country/country_key columns, order notes/metadata, item/quantity totals, email state/timestamps, CSV snapshot/name. |
| `order_items` | Parent foreign key with cascade, ordered position, SKU, product name/description/collection/variant snapshots, quantity, notes/image reference/metadata. Unique parent + position supports ordered retrieval. |
| `alembic_version` | Applied schema revision, managed by Alembic. |

Unique lookup constraints support actual idempotency, order retrieval, and private token lookup. There are no speculative customer/email/search indexes. The pool allows **one connection per process with zero overflow**, a five-second checkout wait, connection health checks, and bounded PostgreSQL connection/statement timeouts. The supplied start script uses one worker and two request threads; email work does not hold the database transaction open. Rolling deploys and migrations can temporarily add another connection.

## Manual Render setup

1. Open the **existing Render Postgres database → Info → Connections**. Use its **Internal Database URL**. The web service must be in the same Render region/private network as the database. Do not use the External Database URL for the web service. See [Render's connection guidance](https://render.com/docs/postgresql-creating-connecting).
2. Open **California Earrings web service → Environment → Add Environment Variable** and set `DATABASE_URL` to that internal URL directly in Render. Do not paste it into chat, source files, build commands, or client JavaScript. If already attached, retain that value. This work did not inspect or modify the live Render account.
3. Keep a stable, strong `SECRET_KEY` shared by all instances. Keep `FLASK_DEBUG=0` and set `SESSION_COOKIE_SECURE=true` (also automatic when Render sets `RENDER=true`). Preserve `SITE_BASE_URL=https://californiaearrings.com` or the existing canonical production domain.
4. Preserve existing Graph settings: `EMAIL_TRANSPORT=graph`; `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (or the existing `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` aliases); `GRAPH_SENDER_UPN`; optional `ORDER_BCC_EMAILS`. Do not replace working mailbox credentials.
5. **Settings → Build & Deploy**: set Build Command to the command below and set Start Command to `sh scripts/start_render.sh`. The checked-in blueprint includes these settings and manual secret placeholders. It references no new database and does not change the existing service plan. If the service is not blueprint-managed, apply the settings in the dashboard.
6. **Settings → Edge Caching → Cacheable file types**: keep **Common static files**. Do not select All files. A successful new deployment purges Render's edge cache; verify headers after deployment. See [Render caching](https://render.com/docs/web-service-caching).
7. Confirm database backup/retention and restrict public database access as appropriate in Render. Preserve legacy local CSVs/email attachments separately before retiring the old instance; this migration creates tables and does not import historical orders.

Required new variable: `DATABASE_URL`. Recommended explicit production variable: `SESSION_COOKIE_SECURE=true`. Existing required `SECRET_KEY` and email values remain. Pool limits are deliberately fixed in code; no pool tuning variables are required for this small database.

## Commands

Build Command (replace the dashboard’s older `pip install -r requirements.txt` command):

```sh
curl -Ls https://astral.sh/uv/install.sh | sh && ~/.local/bin/uv sync --frozen
```

Start Command:

```sh
sh scripts/start_render.sh
```

The start script runs the safe migration wrapper, then starts Gunicorn with one worker, two threads, and a 60-second worker timeout. Migration errors return a nonzero exit without printing driver errors or the connection URL. An advisory transaction lock serializes migration attempts; initial table creation and subsequent migrations are transaction-scoped. The monetary-field removal is intentionally destructive only to those fields; order identities, address fields, items, and quantities remain intact. Re-running upgrade is safe.

For a paid service, optionally set **Pre-Deploy Command** to the following; the startup migration remains a safe no-op when already current. Render recommends pre-deploy for migrations and makes it available on paid services. See [deployment phases](https://render.com/docs/deploys).

```sh
.venv/bin/python -m scripts.database migrate
```

Private shell commands, with `DATABASE_URL` already present in that shell's environment:

```sh
.venv/bin/python -m scripts.database migrate
.venv/bin/python -m scripts.database check
.venv/bin/python -m scripts.database verify
```

For direct Alembic use in a private development environment, `uv run alembic upgrade head` applies the same migration. Use the sanitized wrapper in production. Do not run `downgrade` in production: it drops order data. Roll application code forward and take a backup before destructive schema changes. If the earlier monetary-field version is already live, pause order traffic and stop its workers before applying revision 0002, then start the updated code: old workers still expect the removed columns. For the first deployment, the start script applies both revisions automatically. Rolling back to the old checkout code would resume file-only order handling, so do not use it as a persistence fallback.

## Verify production writes

1. After deploy, run `scripts.database check` in the **web service's Render Shell**. It verifies the configured database connection and current migration revision without printing credentials.
2. Submit a clearly labeled test order through the actual website with two different SKUs and known quantities. This uses normal order processing and emails; coordinate the test with staff.
3. Note its `#CE…` confirmation number and run (substitute that number):

```sh
.venv/bin/python -m scripts.database verify --order-number '#CE00000001'
```

The command prints only the order number, timestamp, order/email states, and counts. It checks child rows and quantities against the order totals without printing customer information. Because it uses the web service's configured `DATABASE_URL`, verify that variable points to the intended internal database in Render before relying on this result.

4. Reload/retry the same submitted form: it should show the same number, not send another email or create another order. Download CSV and PDF in the submitting browser and verify the two line items. Another browser must not be able to use the private download link.
5. Repeat the verification after a web service restart/redeploy. The saved order and items should still exist even though local files may be gone. An expired browser session/download token does not delete the order.
6. Inspect `email_status`: `sent` means the existing transport reported acceptance, not guaranteed inbox delivery; `failed` needs follow-up; stale `pending` may indicate interruption between commit and sending. Check staff email and reconcile before resending. No automatic retry worker is included.

## Route and asset cache policy

| Route / asset | `Cache-Control` |
| --- | --- |
| Public `/static/*` image/CSS/JS/font/video/QR with matching current content `?v=` fingerprint | `public, max-age=31536000, immutable` |
| Unversioned, outdated-version, or arbitrary-version public static assets; CSS imports, raw CSS font/background URLs, direct reel URLs | `public, max-age=300, must-revalidate` |
| `/favicon.ico`, `/robots.txt`, `/sitemap.xml`, `/sitemaps.xml`, legacy `/team/<slug>/contact-qr.svg` redirect | `public, max-age=300, must-revalidate` |
| Public staff `/team/<slug>/contact.vcf` | `public, max-age=3600, must-revalidate` |
| `/`, `/product/*`, marketing/team/trade-show/reels/FAQ pages and redirects with shared cart-aware layout | `private, no-store, max-age=0` |
| `/cart`, `/checkout` including confirmation and validation/DB failure responses, all `/api/cart/*` | `private, no-store, max-age=0` |
| `/download/order/<token>.csv`, `/download/order/<token>.pdf` | `private, no-store, max-age=0` |
| All errors and unclassified dynamic endpoints, including future admin/customer/order-detail routes | `private, no-store, max-age=0` |
| Future public static CSV/PDF documents | Same verified-version/mutable static rules above; **only genuinely public files may be placed in `static/`** |

No private PDFs/CSVs reside under `static/` in the audited source. Fonts are WOFF2; images include JPEG, PNG, SVG, WebP and ICO; media includes MP4/MOV. Browser conditional revalidation remains available for mutable static files. Public static/metadata responses do not set session cookies. Inspect response headers with the browser Network panel; private routes must never show a public cache policy even on errors.

For ranked persistence recommendations and remaining security/performance issues, see [the audit](persistence-audit.md).

## Validation performed

Local PostgreSQL 17 was used for fresh migration, repeat migration, schema revision/drift checks, durable retrieval, item-insert rollback, and concurrent duplicate submissions through separate connection pools. A Flask checkout integration test verified that another connection sees both committed line items before email is attempted; forced email failure retained the saved order and downloads after reconnecting.

The initial implementation's standard suite, with PostgreSQL integration enabled, ran **139 tests: 137 passed, 2 failed, 0 skipped**. All persistence, checkout, email, cache, and deployment-command tests passed. The two failures are existing expectations outside this change: a hero-width CSS assertion and `Organization` structured data while the current template emits `LocalBusiness`. Their UI/content was left intact. Dependency lock, shell syntax, and diff whitespace checks passed. No live Render writes, real email delivery, or browser E2E run was performed in this task.

Run the normal suite with `uv run python -m tests.run standard`. PostgreSQL tests are opt-in via `TEST_DATABASE_URL` and require a dedicated, migrated test database; never point them at production. Use `DATABASE_URL` for the migration command in that test shell, then `TEST_DATABASE_URL` for the test runner. Integration tests use synthetic data and clean up their own records.

The monetary-field removal follow-up passed 61 focused tests, including PostgreSQL migration of an existing order, preservation of individual address fields, retry identity, rollback, concurrency, checkout, and email behavior. Alembic found no schema/model differences after revision 0002. Monetary keys are rejected in structured order-item inputs and metadata, including nested values.
