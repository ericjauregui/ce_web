# Persistence and cache audit

Reviewed September 12, 2026. This audit describes the repository, not a live inspection of the Render account. Deployment instructions are in `postgres-deployment.md`.

## Additional persistence opportunities

Effort estimates are engineering days, including focused tests, and exclude business approval or a full administration UI.

| Data | Rank | Reason / proposed scope | Estimated effort |
| --- | --- | --- | --- |
| Email delivery outbox and retry worker | HIGH VALUE | Orders now survive email failure and retain delivery state. A transactional outbox plus an operator retry workflow would recover process crashes between commit and sending. Graph accepting an email does not prove inbox delivery. Avoid blind retries after ambiguous transport timeouts. | 2–4 days |
| Order status history and internal order queue | HIGH VALUE | Submitted status is stored; an authenticated staff workflow with append-only transitions would track review, confirmation, fulfillment, and cancellation. No existing admin routes or authentication were found. | 3–6 days |
| Historical order import | HIGH VALUE | Earlier orders live in CSV attachments/local CSV files; old SQLite stores only sequence allocations. Back up available legacy exports before replacing ephemeral instances, deduplicate, and import only after reconciling source files. New database setup does not import these automatically. | 1–3 days after gathering exports |
| Businesses/customers | MEDIUM VALUE | Current order snapshots preserve all supplied business/contact fields. Separate customer identities become useful for repeat-customer lookup; company names and optional email are not reliable unique identifiers. Requires matching rules and permissions. | 3–5 days |
| Inquiries and trade-show leads | MEDIUM VALUE | Current contact/trade-show pages link to email and WhatsApp; there is no submitted lead form to migrate. Add a small explicit lead capture workflow and follow-up status if staff need a shared queue. Do not scrape or infer lead records from visitors. | 2–4 days |
| Durable carts / abandoned inquiries | MEDIUM VALUE | Carts currently use signed browser sessions. Server-side carts would reduce cookie-size limits and permit cross-device recovery after an identity/consent design. No customer data is collected for a mere cart. Avoid collecting abandoned checkout fields without a deliberate policy. | 3–5 days |
| Catalog / product data | NOT WORTH IT now | JSON is version-controlled, cached in memory, and serves a read-heavy catalog. There is no authenticated live editor. Keep product snapshots in orders so later catalog edits do not rewrite historical purchases. Reconsider if staff need frequent concurrent edits. | 4–7 days for DB + editor |
| Inventory / reservations | NOT WORTH IT now | Product records are a catalog, not a stock ledger. No authoritative quantity, price, reservation, or fulfillment feed exists. First define the stock source and reconciliation rules; a database alone cannot provide accurate availability. | 5–10+ days after source decisions |
| Images, video, fonts, PDFs | NOT WORTH IT as DB blobs | Public media belongs in static hosting/object storage and CDN. Private order CSV/PDF downloads are regenerated from durable order snapshots. Keep bulky binary files out of the 256 MB database. | No migration recommended |
| Team, FAQs, collections, social links, show content | NOT WORTH IT | Small public, version-controlled JSON content; no concurrency or durability problem needing PostgreSQL. Generated QR assets remain static and source-driven. | No migration recommended |
| UI preferences / search caches | NOT WORTH IT | WhatsApp bubble position is a browser preference; parsed catalog/search caches are derived and can be rebuilt. | No migration recommended |

## Remaining operational and security work

- No authenticated staff order browser, status editor, email retry queue, or audit trail is included. Use the private Render shell/repository verification tools until an authorized admin workflow is built.
- Email delivery still occurs synchronously. A process interruption after commit can leave delivery pending; an ambiguous Graph timeout can mean an email was accepted even when the client observed failure. The durable order must be reconciled before any manual resend.
- Legacy local CSV files and email event logs are not durable on Render's ephemeral filesystem. They contain customer information and need access control, retention rules, and secure backup if retained. PostgreSQL is the authority for new orders.
- Database backup retention and restore drills need to be confirmed in the Render account. Restrict external database access where practical; the web service uses the internal connection in the same region.
- Cart mutation endpoints have no dedicated rate limiter or CSRF-token framework. Checkout's session-bound submission token protects order creation, and SameSite=Lax helps, but site-wide abuse controls and origin/CSRF protection for all mutations remain useful follow-up work.
- Signed Flask cart cookies are readable by the browser and have a practical size limit. Submitted customer data and order contents are removed from cookies by this change; large carts still warrant server-side cart storage if they are common.
- The repository contains about 104 MB of reels and 101 MB of product images. Public asset caching reduces repeat transfer; responsive image formats/sizes and video delivery optimization would improve first-load bandwidth independently of PostgreSQL.
- The checked-in Render blueprint previously declared a free web plan, while the reported enabled edge cache implies a paid live service. Verify the existing service's plan; this change does not alter the plan or create another database.

## Asset versioning follow-up

The application generates content versions for template-linked public assets. Immutable caching is granted only when a requested version matches the file's content fingerprint. Unversioned nested CSS imports, CSS background images, font URLs, direct product/reel URLs, and legacy QR redirects retain mutable/revalidation policies. A future build manifest should emit hashed filenames and rewrite **all** nested references together; retain old hashed files during rolling deploys. Arbitrary `?v=` strings are not proof of immutable content.

Never place private CSVs, PDFs, or customer documents under `static/`. The static directory is public regardless of cache policy. Render's Common static files setting includes CSV and PDF, which makes explicit private download headers essential. Keep that setting; do not enable All files.

References: [Render edge caching](https://render.com/docs/web-service-caching), [Render PostgreSQL internal connections](https://render.com/docs/postgresql-creating-connecting), [Render deployment phases](https://render.com/docs/deploys).
