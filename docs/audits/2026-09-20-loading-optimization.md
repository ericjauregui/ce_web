# Deferred reels, smaller CSS, and catalog rendering — September 20, 2026

Local working-tree implementation only; not committed or deployed. Earlier image
optimizations and unrelated existing edits are preserved. Hero assets are unchanged.

## Changes

- All 61 reels have real frame posters extracted at 0.08 seconds. Lossless WebP
  variants at 160, 320, and up to 540 pixels preserve proportions. Near-viewport
  previews select a variant using rendered width and device density. Resize updates
  the selection. Offscreen previews wait; only an active reel loads its video.
- Visible muted autoplay, explicit activation, native/touch sound controls, search
  focus pausing, out-of-view pausing, and reel advancement remain. Missing or failed
  posters retain near-viewport frame extraction. Content hashes tie posters to their
  source video, so a replaced clip cannot reuse a stale poster.
- Bootstrap is reduced from 232,803 to 50,966 bytes (78.1%) before transport
  compression. Declarations and cascade order are preserved. Functional selectors
  and Bootstrap state classes are retained conservatively. The original stylesheet
  remains the automatic fallback when source inventory or output fingerprints change.
- Catalog initialization no longer measures every closed drawer. Opening a drawer
  measures its current contents; open drawers still update on resize. Fixed square
  image wrappers use `content-visibility: auto` without estimated card heights.
  Product text, controls, anchors, and all catalog entries remain in the document.

## Verification

- Before/after layout checks cover homepage, search, cart, reels, and trade shows
  in Chromium at 320, 390, 768, and 1440 CSS pixels and WebKit at 390 pixels.
  Non-reel sampled geometry and typography matched across all 25 pairs. Reel
  differences reflect asynchronous video activity and deferred offscreen posters;
  active reel geometry remains governed by the same styles. No JavaScript errors.
- Chromium and WebKit checks cover navigation, catalog anchor, add/increment/clear
  cart, mini-cart count, product detail, search, keyboard drawer expansion, offscreen
  video deferral, muted autoplay, keyboard reel activation, manual mute, and advancement.
- Before/after homepage screenshots were visually reviewed. These are local desktop
  browser engines with simulated viewports, not physical-phone or production evidence.
- No real orders, outbound email, or deployment were performed.

## Measurement limits

Cold Chromium tests use a 390 x 844 viewport at DPR 1, 1.6 Mbps download, 150 ms
latency and 4x CPU slowdown, alternating before/after order for three pairs. Before
uses frozen HTML from the start of this task; after uses current rendered HTML.
Both use the same seeded reels and local assets. Local HTML/CSS is uncompressed;
production already uses Brotli. Capture waits at least five seconds after load and
for the hero LCP entry. Video bytes observed by capture are not complete media sizes
and vary with playback and sampling duration. Playback-start latency on real slow
mobile networks remains device-dependent; reduced transfer does not guarantee zero
latency on first activation of a previously unloaded reel.

Maintenance commands are documented in README.md. The CSS parser and FFmpeg are
needed only for offline asset generation, not at production request time.

## Final timing results

Medians from three cold runs per version:

| Metric | Before | After | Reduction |
|---|---:|---:|---:|
| First contentful paint | 5.95 s | 3.28 s | 44.8% |
| Hero paint (LCP) | 28.78 s | 23.78 s | 17.4% |
| Load event | 28.68 s | 23.62 s | 17.6% |

Median measured CLS remained approximately 0.022 before and 0.022 after. These changes improve startup, but the unchanged large hero and visible active video still dominate slow-network loading.

[Raw timing and request data](2026-09-20-loading-timing-data.json).

## Final checks

109 focused tests passed (loading assets, image assets, frontend contracts, product routes, caching, cart, reels, trade shows). `git diff --check` passed. Final Chromium and WebKit interaction checks passed after responsive poster sizing. The optimized CSS manifest is current.

Browser instrumentation measured 626 product-drawer height reads at startup before and zero after, retaining 313 products. Chromium skipped rendering 305 offscreen product images at initial load.

[Layout, interaction, and rendering evidence](2026-09-20-loading-verification-data.json).
