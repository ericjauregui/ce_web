# Production verification — September 20, 2026

Tested https://californiaearrings.com after the user confirmed deployment.

## Functional and deployment checks

- All 13 public route requests returned HTTP 200: homepage, search, product detail,
  cart, checkout, reels, trade shows, team, about, contact, FAQs, robots, and sitemap.
- Six fingerprinted deployed assets match local committed bytes: three hero images,
  reduced Bootstrap CSS, catalog JavaScript, and inline reel JavaScript.
- Homepage includes responsive product URLs and responsive reel poster attributes.
- HTML is compressed (Brotli in Chromium, gzip in curl) and retains private/no-store
  caching. Fingerprinted static assets return one-year immutable cache headers.
  Cloudflare HIT responses were observed for CSS, both tested scripts, and two heroes;
  the wide hero's first probe returned MISS, not an error.
- Chromium and WebKit live interaction checks passed: navigation toggle, catalog
  anchor, add/increment/clear quantity, mini-cart count, product detail image, search,
  keyboard drawer expansion, deferred offscreen video, muted autoplay, keyboard reel
  selection, manual mute, and next-reel advancement.
- Cart mutations used fresh isolated browser sessions and were cleared. No orders
  were submitted and no email was sent. Receipt delivery and durable order writes
  were not exercised; this is not a full production checkout acceptance test.
- No JavaScript errors or HTTP 4xx/5xx responses in the nine measured homepage loads.
  All retained 313 products and reported no horizontal overflow at tested widths.

## Production timing

Medians of three cold visits per profile, fresh Chromium contexts, disabled browser
cache, real production HTTPS. Production chooses random reels, so content is not
identical across runs. Viewports and network/CPU conditions are simulated, not physical
phone evidence. Desktop: 1440 x 900 / DPR 1, 20 Mbps, 40 ms configured latency, CPU 1x.
Fast mobile: 390 x 844 / DPR 3, 10 Mbps, 70 ms, CPU 2x. Slow mobile: same viewport/DPR,
1.6 Mbps, 150 ms, CPU 4x. LCP observation waits at least five seconds after load and
for a hero paint entry. Measurements include external network and origin latency.

| Profile | First content | Hero LCP | Load event | Initial response (TTFB) | CLS |
|---|---:|---:|---:|---:|---:|
| desktop | 1.68 s | 3.64 s | 2.13 s | 1.10 s | 0.024 |
| mobile-fast | 1.75 s | 3.83 s | 3.70 s | 1.15 s | 0.027 |
| mobile-slow | 2.20 s | 17.92 s | 17.82 s | 1.12 s | 0.036 |

The first desktop run was slower (LCP 7.87 s); it remains included, with three-run
medians reported. These production results are not an apples-to-apples before/after
comparison with earlier local tests: compression, network, pixel density, origin
processing and reel selection differ.

## Findings

The deployed optimizations are active and the checked interactions pass. Performance
is still above the sub-second objective. Initial response alone is about 1.1 seconds
in these profiles; origin processing/network contribution needs a separate measured
investigation. Slow-mobile image/video transfer and rendering remain substantial.
No new implementation or hosting changes were made during this verification.

[Raw route, interaction, header, timing, and resource data](2026-09-20-production-verification-data.json).
