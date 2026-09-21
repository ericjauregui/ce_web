# Server-side image metadata cache — September 20, 2026

Implemented locally, not committed, pushed, or deployed. No image, template, layout,
viewport, search, or cart behavior changes are part of this implementation.

## Implementation

- Added a bounded, thread-safe cache of immutable image selections and responsive
  candidates. It stores asset metadata only, never customer data or rendered pages.
- Three manifest stamps are checked once per request. Each unique requested image
  checks lightweight source/derivative stamps before reuse; changed, missing, repaired,
  or replaced files trigger normal fingerprint validation and fallback.
- File validation retains the existing mtime-nanoseconds/file-size change-detection
  contract. Generator updates and deployments change those stamps. A manual same-size
  rewrite that deliberately restores the original timestamp is outside that contract,
  as it was for the existing file fingerprint cache.
- Request-local reuse avoids duplicate checks for the same image. URL and srcset
  caches are bounded and keyed by asset versions plus static URL/mount prefix; Flask
  still performs URL escaping on misses. Attribute dictionaries returned to callers
  are fresh rather than mutable shared cache objects.
- Existing app startup warmup now prepares product and hero image metadata before a
  production worker accepts requests. Warmup is best-effort; ordinary requests can
  recover/populate cache entries if startup preparation is unavailable.
- Original uncached domain helpers remain available and are used as a reference for
  byte-identical rendering and fallback tests.
- Refreshed the Bootstrap manifest to keep the existing reduced stylesheet active.
  The initial saved HTML used its stale-manifest full-CSS fallback; controlled cache
  comparisons therefore use the same current stylesheet in both variants.

## Local warm-request results

Nine requests per variant/case, same app/process, seeded reels and matching cart state.
These measure application processing, not network time, production TTFB, or page load.

| Case | Original image helpers | Cached helpers | Reduction | Rendered HTML |
|---|---:|---:|---:|---|
| empty | 144.9 ms | 23.8 ms | 83.6% | Identical |
| cart | 143.6 ms | 23.9 ms | 83.4% | Identical |
| search | 10.9 ms | 8.5 ms | 22.0% | Identical |
| prefix | 141.1 ms | 25.0 ms | 82.3% | Identical |

## Verification

118 focused tests passed across image caching, existing image/hero/loading assets,
frontend contracts, product routes, caching headers, cart endpoints, reels, and trade
shows. New tests exercise file corruption/removal/repair, source changes, manifest
replacement/removal, hero fallback, concurrent readers, bounded storage, immutable
results, mount-prefix isolation and empty/populated-cart HTML equivalence.

No production configuration, shared HTML caching, database writes, or email sending
was introduced. Production speed must be re-measured after deployment; the local
83% processing reduction is not a promised 83% reduction in page-load time.

[Measurement data](2026-09-20-image-metadata-cache-data.json).

Local Chromium and WebKit checks passed for navigation, catalog anchors, cart add/increment/clear, mini-cart totals, product detail image, search, keyboard drawer expansion, offscreen reel deferral, muted autoplay, keyboard reel activation, manual mute and advancement. No JavaScript errors. No orders submitted or email sent.
