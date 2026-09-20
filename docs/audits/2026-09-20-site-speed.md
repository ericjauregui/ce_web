# Site speed and initial-load audit — September 20, 2026

The highest-impact work is reducing hero and product-image bytes, followed by removing video downloads used only to display thumbnails. Preserve the supplied photography, responsive hero composition, and existing page content.

## Measurement scope

Local current `dev` working tree, including existing uncommitted changes. Other workspace edits occurred during the audit, so this is a diagnostic snapshot, not a frozen release benchmark. No application code or assets were changed by this audit, and nothing was deployed.

Chromium, fresh browser contexts, cache disabled, no user interaction. Mobile: 390 × 844 CSS pixels, 1.6 Mbps download, 150 ms configured latency, 4× CPU slowdown. Desktop: 1440 × 844, unthrottled. Measurements sampled five seconds after the load event. Transfer totals count completed requests and exclude unfinished or aborted media transfers; they are lower bounds. Reels are randomized, so payload varies between runs. Single runs are directional, not statistical benchmarks.

Local Flask serves uncompressed text over HTTP/1.1; production compression, CDN, protocol, hosting latency, and real-device performance were not verified. Do not interpret these timings as production Core Web Vitals or Lighthouse scores.

| Initial navigation | LCP | Load event | Completed transfer | Requests | DOM elements |
|---|---:|---:|---:|---:|---:|
| Homepage, mobile simulation | 55.22 s | 54.98 s | 9.33 MB | 45 | 5,726 |
| Homepage, desktop unthrottled | 4.45 s | 0.69 s | 11.99 MB | 51 | 5,726 |
| Catalog entry, mobile simulation | Not captured | 61.53 s | 11.78 MB | 50 | 5,726 |
| Reels, mobile simulation | 7.99 s | 7.34 s | 0.92 MB | 22 | 435 |

The catalog entry redirects to a homepage collection anchor. Its LCP observer returned no entry, so no value is inferred. Reels transfer totals especially undercount media still loading at capture. Raw measurements are saved in `2026-09-20-site-speed-data.json` beside this report.

The responsive hero background was the final observed LCP element in both homepage runs. CLS was 0.023 mobile and 0.030 desktop. Desktop LCP can occur after the load event. These results show why load-event timing alone is insufficient.

## Ranked recommendations

### 1. Convert responsive hero PNGs to WebP — very high impact, low effort

Keep the same images, dimensions, crops, and breakpoint-specific preloads. Offline WebP quality-85 trials, without resizing:

| Asset | Current | Trial WebP | Reduction |
|---|---:|---:|---:|
| Mobile compact hero | 2,424 KB | 293 KB | 87.9% |
| Tablet/original hero | 2,208 KB | 206 KB | 90.7% |
| Wide desktop hero | 2,080 KB | 179 KB | 91.4% |

Only one responsive hero is needed per viewport. Mobile savings are approximately 2.13 MB per cold visit. At the simulated bandwidth, that is 10.7 seconds of transfer capacity; it is not a promised LCP reduction because competing requests and rendering also matter. Review jewelry detail and gradients visually before choosing final quality. Update CSS URLs and preloads together to avoid duplicate downloads.

Locations: `templates/index.html`, `static/css/styles/base.css`, `static/assets/hero_bg*.png`.

### 2. Serve appropriately sized WebP product thumbnails — very high impact, moderate effort

The initial homepage downloads numerous full-resolution JPEGs despite native lazy loading. Seven actual requested images total 2.61 MB. The same images encoded at WebP quality 85 total 286 KB without resizing, or 99 KB at a maximum 600 × 600 pixels: reductions of 89% and 96%, respectively. This sample demonstrates opportunity; it is not a measured whole-catalog reduction.

Generate thumbnail variants, for example 300 and 600 pixels wide, and supply accurate `srcset`/`sizes` for the product cards. Retain originals for detail views. Keep lazy loading for below-fold cards; prioritize images actually visible when landing at the catalog anchor. Review visual quality at high device pixel ratios. Browser lazy loading fetches near-viewport content too, so it does not replace proper image sizing.

Location: `templates/partials/product_card.html`. The source catalog contains 313 products.

### 3. Replace reel thumbnail priming with static posters — high impact, moderate effort

`static/js/inline_reels.js` sets `AUTOPRIME_CARD_COUNT = 5` and immediately initializes those videos, bypassing the intent of `preload="none"`. All five had video data in the homepage runs. The desktop run completed approximately 1.75 MB from just two video range responses; other partial transfers are not included in that figure.

Generate small real frame posters, render them initially, and attach the MP4 source when playback is requested. If autoplay is required, activate only the visible selected reel after critical images finish. Observe the page viewport as well as the horizontal reel track. Validate playback, thumbnail appearance, advancing reels, touch audio controls, and fullscreen behavior. Preserve the owner video's corrected audio/video timing; poster generation requires no video re-encoding.

Locations: `templates/partials/latest_videos_strip.html`, `static/js/inline_reels.js`, `static/js/home_reels.js`, and the full reels page.

### 4. Verify production text compression — high impact if absent, low effort

The homepage HTML is approximately 752 KB uncompressed and 36.6 KB in an offline gzip trial, a 95% reduction. The bundled Bootstrap CSS and JS total 314 KB raw versus 54.6 KB gzipped. Confirm actual `Content-Encoding: br` or `gzip` on production HTML, CSS, and JS before changing infrastructure; Render may already provide it. The local Flask result does not prove a production defect.

Retain `private, no-store` for cart-aware HTML and private endpoints. Compression is compatible with private responses and does not require making them publicly cacheable. Current fingerprinted static assets already receive one-year immutable caching.

### 5. Reduce work for the full catalog during initial rendering — medium impact, moderate effort

The homepage builds 5,726 DOM elements and includes the complete catalog. First profile layout and scripting after reducing network payload. Consider `content-visibility: auto` on offscreen sections with suitable intrinsic sizes, and initializing card behavior when sections approach the viewport. Preserve collection anchors, search, keyboard navigation, cart state, and access to every product. Pagination would change the experience and is not the first recommendation.

Local in-process homepage rendering was approximately 53–59 ms when warm and 395 ms on the first test-client request. These are not production server timings; they do not justify a hosting upgrade on their own.

### 6. Match font preload URLs and CSS font URLs — smaller impact, low effort

`templates/base.html` preloads fingerprinted Lato and Playfair font URLs, while `static/css/styles/fonts.css` references unversioned URLs. The browser requested both variants of both fonts. Make each preload URL exactly match the corresponding `@font-face` URL, preferably using consistent fingerprinted references. Audit the logo shape for the same duplicate-URL pattern. Fonts already use `font-display: swap`.

After these changes, consider reducing unused Bootstrap CSS and page-specific styling, based on coverage measurements. These are smaller opportunities than the multi-megabyte image payloads.

## Validation for implementation

Repeat at least three cold and warm runs against a fixed revision and deterministic reel selection. Compare mobile and desktop LCP, bytes by resource type, and layout stability. Verify production compression and cache headers separately. Visually check hero composition and jewelry detail at 390, 768, and 1440 pixels; test catalog navigation and reel controls. A browser mobile simulation is not physical-device evidence.

Guidance: [Optimize Largest Contentful Paint](https://web.dev/articles/optimize-lcp), [responsive images](https://web.dev/learn/design/responsive-images), [native lazy-loading behavior](https://web.dev/articles/browser-level-image-lazy-loading), and [Chrome network measurement](https://developer.chrome.com/docs/devtools/network/reference).
