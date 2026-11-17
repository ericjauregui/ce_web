# Test suite audit

Reviewed 2026-11-17 against the current browser journeys and isolated checks. The default `e2e` suite runs browser journeys; `all` also runs the isolation suite. Case counts alone do not measure work: several tests cover multiple paths, widths, or failure injections.

| Area | Decision and coverage retained |
| --- | --- |
| Checkout and email | Consolidated desktop country and phone filtering into the real checkout, and large-order plain-text completeness into the 67-item email journey. Retained WebKit mobile selection, Graph wire serialization, unsafe image paths, image codec failures, winter time conversion, missing configuration, and large PDF stress: these exercise different conditions. |
| Cart, drawer, undo | Retained separate normal, delayed, failed, expired, and concurrent edit scenarios. Their independent synthetic sessions and fault injection distinguish lost notes, duplicate writes, stale undo, and recovery. |
| Search and catalog | Retained search/recovery, detail imagery and cart navigation, and pending-write failure cases. The latter exercise ordering and uncertain responses not covered by ordinary searches. |
| Navigation, titles and widths | Removed duplicate page-title geometry passes across five pages and 11 widths; the single-line title journey already invokes the same geometry assertion. Kept empty/populated cart and breakpoint cases, mobile collection scrolling, and cross-page clipping checks. |
| Media and hero | Retained autoplay gating, failed hero, video poster race, reduced motion and save-data cases; these vary loading order and user preference and cannot be inferred from one successful playback. |
| Content and team | Retained public pages, contact downloads, event switching, stale preview fallback, generated QR idempotence, duplicate slugs and missing photos. Production-shaped content alone does not cover generated-input failures. |
| Analytics | Retained session attribution, dashboard aggregation, probe classification, interaction recording and private-token redaction. Each validates a distinct reporting or privacy boundary with synthetic data. |
| Assets and cache | Retained all-asset pixel/metadata validation, corrupt and stale fallback, cache invalidation and concurrent access. Browser rendering selects only a subset of derivatives and cannot prove byte fidelity. |
| Database and migration | Retained PostgreSQL rollback, concurrency, cross-connection persistence, legacy migration, input validation and command failure checks. SQLite browser runs cannot reproduce PostgreSQL transactions or an old schema. |
| Social preview generation | Retained stale input, billing avoidance, logo verification, API failure and secret redaction. Browser navigation observes generated output but does not exercise the generator's failure paths. |

The consolidated title tests preserve the original per-width geometry evidence. The checkout journey preserves the receipt evidence and uses intercepted email and a local synthetic database. Run the full suite and verify the manifest using the commands in `AGENTS.md`; PostgreSQL checks require a dedicated test database.
