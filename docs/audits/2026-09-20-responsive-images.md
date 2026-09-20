# Responsive product images — September 20, 2026

Implemented locally on the existing working tree. Not committed or deployed. Existing concurrent changes outside this work were preserved.

## Implementation

- Generated **1,530 responsive variants for all 313 catalog product images and six curated trade-show photos** (319 source images).
- Width targets: 160, 320, 480, 640, and 960 pixels. Every variant maintains the source aspect ratio, uses Lanczos resampling and lossless WebP encoding, and is retained only when smaller than the source. The generator never upscales, stretches, crops, sharpens, or regenerates jewelry content.
- Product cards, collection icons, cart, checkout, order-confirmation thumbnails, and the trade-show product collection use `srcset` and `sizes`. Lazy loading and existing CSS geometry remain in place. Product detail images, metadata, exports, and hero resolution remain unchanged.
- Browser-selected sizes account for rendered width and screen density. Native `sizes="auto"` has explicit breakpoint/width fallbacks. The full-resolution original or verified lossless alternative remains the largest candidate.
- Source fingerprints invalidate stale variants. Missing or modified variants are omitted, with normal image fallback retained. All URLs keep the existing content-fingerprinted cache policy.
- Source EXIF orientation is applied before resizing; ICC color profiles are retained. Stale EXIF dimensions/embedded previews are omitted from thumbnails. Full-resolution source files retain their metadata.

## Initial product-image payload

Fresh contexts, deterministic homepage/reel content, no scrolling before the initial capture, sampled two seconds after load. These counts sum image response Content-Length values for requested product assets; they are not total page bytes or video bytes. Each before/after pair uses identical viewport and pixel density. Separate icon/card variants can add one small request while substantially reducing total bytes.

| Browser / viewport / density | Before responsive sizing | After | Reduction |
|---|---:|---:|---:|
| Chromium, 320px, 3x | 5,183,722 bytes | 543,932 bytes | 89.5% |
| Chromium, 390px, 3x | 4,570,303 bytes | 663,636 bytes | 85.5% |
| Chromium, 768px, 2x | 5,064,088 bytes | 522,218 bytes | 89.7% |
| Chromium, 1440px, 1x | 5,593,224 bytes | 351,858 bytes | 93.7% |
| WebKit, 390px, 3x | 3,877,575 bytes | 430,916 bytes | 88.9% |

## Mobile timing retest

Medians of three paired cold Chromium runs at 390 x 844, device scale factor 1, 1.6 Mbps download, 150ms configured latency, and 4x CPU slowdown. Before is the prior full-resolution lossless implementation, not the original unoptimized site. Identical frozen homepage/reel content was served over local HTTP, with browser cache disabled and alternating pair order. Capture waited at least five seconds after load and for the hero LCP entry.

| Metric | Before | Responsive images | Reduction |
|---|---:|---:|---:|
| Hero paint (LCP) | 48.02 s | 28.62 s | 40.4% |
| Load event | 47.91 s | 28.50 s | 40.5% |
| First contentful paint | 5.89 s | 5.89 s | 0.1% |

Local Flask HTML/CSS is uncompressed; production already uses Brotli. These results quantify a local frontend comparison and are not production or physical-device speed measurements. Frozen HTML avoids backend render-time variation. Videos continue downloading after load, so aggregate observed media bytes are not used as a savings metric.

## Quality and behavior checks

- Final working-tree verification: **106 tests passed** across image assets, frontend contracts, product routes, cache control, cart endpoints, reels, and trade-show routes. `git diff --check` passed. Earlier trade-show social-image errors were reproducible without these responsive edits; the final combined rerun passed with the latest concurrent workspace changes.
- Chromium: before/after at 320px/3x, 390px/3x, 768px/2x, and 1440px/1x. WebKit: 390px/3x. DOM counts, all product-card/collection-icon dimensions, hero geometry, overflow measurements, sampled image rectangles, and object-fit values match before/after.
- Compared 101SB, 508WB, and 1886WB image screenshots at each configuration. Browser selections were 480px for 136px-wide cards at 3x, 640px for 171px cards at 3x, 480px for 216px cards at 2x, and 320px for 306px desktop cards. No source image upscaling was needed for these samples.
- Chromium and WebKit navigation, collection links, add/increment/clear cart, mini-cart count, product-detail image, and search checks passed. No orders were submitted, and no JavaScript errors occurred in those runs.
- File checks cover every generated asset: source/output fingerprints, dimensions, proportional aspect ratio, no upscaling, smaller file size, color profile preservation, and WebP format. Encoding is verified against the resized pixels during generation. Tests cover rotated source images, unchanged originals, missing/corrupt/stale fallback, and responsive attributes on thumbnail routes.
- Resizing necessarily changes pixels; the guarantee here is preserving composition/aspect ratio and lossless encoding after high-quality resizing, not pixel-identical full-resolution images. Browser rendering and actual-device appearance still depend on the device.

## Maintenance and evidence

Run `uv run python -m scripts.optimize_images` after changing source product images, hero images, fonts, or background-logo assets. Commit the generated `static/optimized/` files and manifests with the source changes. There is no new external service, runtime resizing endpoint, or deployment build dependency. Responsive variants add approximately 122 MiB of stored assets; a browser selects suitable individual candidates rather than downloading the entire generated set.

- [Quality, selection, layout, and interaction data](2026-09-20-responsive-images-data.json)
- [Paired timing data](2026-09-20-responsive-timing-data.json)
