# Controlled speed retest — September 20, 2026

Removed `test_visual_polish_contracts_for_hero_header_and_cards` as requested. All **95 tests pass** across frontend contracts, image assets, product routes, cache control, cart endpoints, and reel routes. `git diff --check` passes. This retest changes no application styling or behavior.

## Timing results

Medians of three cold-browser runs per variant and profile. Lower is better.

| Profile | Metric | Before optimization | After optimization | Reduction |
|---|---|---:|---:|---:|
| Desktop | Largest contentful paint (hero) | 14.41 s | 11.94 s | 2.47 s / 17.2% |
| Desktop | Load event | 9.34 s | 7.82 s | 1.52 s / 16.3% |
| Desktop | First contentful paint | 2.00 s | 1.73 s | 0.27 s / 13.4% |
| Mobile | Largest contentful paint (hero) | 56.79 s | 48.16 s | 8.62 s / 15.2% |
| Mobile | Load event | 56.19 s | 47.93 s | 8.26 s / 14.7% |
| Mobile | First contentful paint | 5.95 s | 5.95 s | 0.00 s / 0.0% |

These are controlled **local lab measurements**, not deployed production speed, real-device results, or Lighthouse scores. A load event does not mean that all background video downloads have finished. LCP tracks the hero's largest visible paint and can occur after the load event.

## Method

- Chromium 145.0.7632.6 using the installed matching Playwright 1.58 driver.
- Desktop: 1440 × 900, 10 Mbps download, 40 ms configured latency, no CPU slowdown.
- Mobile: 390 × 844, 1.6 Mbps download, 150 ms configured latency, 4× CPU slowdown.
- Fresh browser contexts with browser cache disabled for every run; three before/after pairs per profile, alternating pair order.
- Same pre-optimization and optimized homepage snapshots and the same seeded selection/order of reel videos. Snapshots and original/optimized CSS are served over actual local HTTP, so network throttling applies to the HTML and styles as well as media. Referenced script/style fingerprints were checked against the served bytes.
- Assets use the current originals or generated lossless variants as appropriate. Playback and lazy-loading behavior are unchanged. No scrolling or user interaction during capture.
- Observe for at least five seconds after the load event and until the hero LCP has been recorded, then allow another second for observer delivery. The initial setup trial was discarded because it sampled before the first run produced any LCP entry; all reported runs use the same corrected capture rule.
- HTML/CSS are uncompressed on this local Flask server; production already uses Brotli. Frozen HTML removes backend render-time variation, so these tests measure frontend loading rather than production server latency. The earlier single-run audit is not used as the timing baseline.
- Completed/partial network byte counters are retained in the raw data. Capture durations vary and videos continue downloading, so aggregate media/full-page transfer totals are not used to claim payload savings.

The previous fixed-window payload comparison measured **1,383,473 fewer initial image/font bytes (17.21%)** over three paired mobile runs. The changes retain full resolution and lossless decoded pixels. See the [implementation report](2026-09-20-speed-implementation.md) for image and interaction verification.

## Individual runs

| Profile | Pair | Variant | Hero LCP | Load event | First contentful paint |
|---|---:|---|---:|---:|---:|
| Desktop | 1 | before | 17.74 s | 9.25 s | 11.89 s |
| Desktop | 1 | after | 11.94 s | 7.82 s | 1.73 s |
| Desktop | 2 | after | 10.93 s | 7.83 s | 1.74 s |
| Desktop | 2 | before | 14.41 s | 9.34 s | 1.66 s |
| Desktop | 3 | before | 13.47 s | 9.40 s | 2.00 s |
| Desktop | 3 | after | 12.20 s | 7.82 s | 1.68 s |
| Mobile | 1 | before | 57.23 s | 56.52 s | 6.23 s |
| Mobile | 1 | after | 48.20 s | 47.93 s | 5.96 s |
| Mobile | 2 | after | 48.12 s | 47.93 s | 5.95 s |
| Mobile | 2 | before | 56.77 s | 56.18 s | 5.95 s |
| Mobile | 3 | before | 56.79 s | 56.19 s | 5.94 s |
| Mobile | 3 | after | 48.16 s | 47.94 s | 5.94 s |

All reported runs completed without JavaScript errors. Results remain local and uncommitted; no deployment occurred. [Raw timing measurements](2026-09-20-speed-timing-data.json).
