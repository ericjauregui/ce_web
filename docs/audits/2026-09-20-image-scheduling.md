# Homepage image scheduling — September 20, 2026

## Change

Catalog product images and collection thumbnails retain their full-quality responsive candidates, sizes, alt text, and server-rendered product content. The new loader waits to fetch offscreen images while the hero is pending; visible images always load. After the hero completes or fails, the loader uses a 400px vertical look-ahead. Scrolling enables look-ahead immediately, and same-page category clicks prepare the first four destination images. Native image markup remains in noscript. Browsers without IntersectionObserver load all images.

Reel posters load through a low-priority Image before assigning video.poster, avoiding the earlier normal-priority poster request. Offscreen poster look-ahead resumes after hero completion; visible posters and muted autoplay remain enabled. Hero files, compositions, aspect ratios, viewport dimensions, product assets, and CSS layout are unchanged.

## Measurement

Three alternating cold local runs per version, fixed reel selection, simulated 390x844 DPR3, 1.6 Mbps, 150 ms latency, 4x CPU. The HTML is a frozen rendered snapshot; static files come from the local Flask server without production compression. This isolates the browser-loading change and is **not a production timing forecast** or a physical-device test. The final scroll/anchor intent bypass was additionally verified through browser checks; it does not run during stationary timing visits.

| Median | Before | After |
| --- | ---: | ---: |
| Hero request duration | 16.77s | 14.71s |
| Product/collection image bytes whose requests started before hero completion | 853,352 | 121,580 |

Hero download improved **12.3%**. The image-byte measure counts full response bytes for requests initiated before hero completion, not bytes physically received by that instant. Visible reel previews still compete with the hero, so this does not remove the entire slow-connection bottleneck. Priority hints alone did not yield a measurable improvement in the earlier diagnostic.

## Verification

- 66 focused Python tests passed: frontend contracts, product routes, reel routes, image metadata cache, loading assets.
- Chromium and WebKit: pending-hero offscreen deferral, scrolling before hero completion, preserved DPR3 image selection, reaching the end of the catalog, no-JavaScript fallback, failed-hero recovery.
- Chromium and WebKit interaction regression checks: navigation, catalog anchor, cart add/increment/clear, mini-cart, detail image, search, drawer keyboard expansion, offscreen video deferral, muted autoplay, keyboard reel activation, manual mute, reel advancement.
- Generated Bootstrap manifest rebuilt; diff whitespace checks passed.

The scheduling changes are local. No deployment, real orders, email, or physical-device verification was performed for this change. Raw timing evidence: `2026-09-20-image-scheduling-data.json`.
