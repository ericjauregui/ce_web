# Lossless speed optimization — September 20, 2026

Implemented locally on the existing `dev` working tree. Not committed or deployed. Existing unrelated edits were preserved.

## Scope and experience

- Hero and catalog/collection images use full-resolution, lossless WebP alternatives only when smaller. Originals remain available; product-detail pages, exports, and social metadata retain their original images.
- Generated alternatives preserve decoded pixels, dimensions, ICC profiles, and EXIF payloads. No resizing, quality reduction, image replacement, or crop changes.
- Font and background-logo CSS URLs now use the same content fingerprints as their HTML references. This removes two duplicate font downloads and one duplicate logo download.
- No changes to interaction scripts, video loading/playback, catalog rendering order, lazy-loading behavior, fonts, text, spacing, or layout were made for this optimization.
- Production already returned `Content-Encoding: br` for HTML and CSS, and `Vary: Accept-Encoding`, when checked on September 20. HTML retained `private, no-store, max-age=0`. No server compression or cache-policy changes were necessary.

The audit's much larger lossy/resized-image estimates were deliberately not used because preserving the current experience took priority.

## Results

Three paired cold-browser runs used the same captured homepage and deterministic reel selection at 390 × 844. No scrolling or interaction occurred before measurement, five seconds after the load event. All three runs produced identical image/font payload totals:

| Initial assets | Before | After | Saved |
|---|---:|---:|---:|
| Images | 7,918,477 bytes | 6,587,444 bytes | 1,331,033 bytes |
| Fonts | 119,048 bytes | 66,608 bytes | 52,440 bytes |
| Images + fonts | 8,037,525 bytes | 6,654,052 bytes | **1,383,473 bytes / 17.21%** |

These are sums of response content lengths for requested assets, not full-page transfer totals, video bytes, or an LCP improvement claim. The local development server and unthrottled browser do not establish production speed. Measurements are in [the implementation data](2026-09-20-speed-implementation-data.json).

A subsequent [controlled timing retest](2026-09-20-speed-retest.md) measured median load-event improvements of **16.3% desktop** and **14.7% slow mobile**, and hero LCP improvements of **17.2% desktop** and **15.2% slow mobile**, across three paired cold-browser runs per profile.

| Hero | Original | Lossless copy | Saved |
|---|---:|---:|---:|
| Mobile compact | 2,424,258 bytes | 1,847,234 bytes | 23.8% |
| Original/tablet | 2,208,276 bytes | 1,587,398 bytes | 28.1% |
| Wide desktop | 2,079,661 bytes | 1,542,524 bytes | 25.8% |

316 images were evaluated; 245 had smaller lossless alternatives. Across the complete input set, the selected originals/alternatives total 102,337,999 bytes instead of 112,042,278 bytes (8.7% less). Keeping originals adds approximately 68 MiB of generated assets to the repository; browsers request only the selected variant for each homepage image.

## Verification

- All 245 generated alternatives passed decoded pixel equality, dimensions, source/output fingerprints, and color/EXIF metadata checks. Alternatives are always smaller than their sources.
- Chromium before/after comparisons at 390, 768, and 1440 pixels: identical hero screenshot pixels, hero geometry, DOM/card counts, loaded fonts, and tested product image dimensions. No JavaScript errors.
- Mobile WebKit at 390 pixels also passed the before/after layout, font, dimensions, and error checks; its hero screenshots were pixel-identical. The product screenshot mean channel difference was below 0.008/255. The initial WebKit tool/browser mismatch was resolved by using the installed matching Playwright 1.58 driver.
- All 2,245 homepage text blocks and 325 image alt attributes match the baseline.
- Product screenshots show very small JPEG-vs-WebP browser-decoder/resampling differences (mean channel error below 0.07 on a 0–255 scale), despite pixel-identical decoded source/alternative files in Pillow. Do not interpret lossless source checks as a promise of identical screenshot bytes for every browser decoder.
- Chromium and WebKit navigation, collection anchor, add/increment/clear cart, mini-cart count, original product-detail image, and search passed in isolated local sessions. No orders were submitted.
- 59 focused tests passed: `tests.test_image_assets`, `tests.test_product_routes`, `tests.test_cache_control`, `tests.test_cart_endpoints`, and `tests.test_reels_routes`.
- The initial verification found one pre-existing frontend-contract failure expecting old hero CSS. At the user's request, `test_visual_polish_contracts_for_hero_header_and_cards` was subsequently removed. All 95 tests across the 36 remaining frontend contracts and the 59 focused tests now pass. The site's styling was not changed by removing the test.
- `git diff --check` passed. Real phones and live deployed optimized assets were not tested.

## Maintenance

Run `uv run python -m scripts.optimize_images` after changing source catalog/hero images, fonts, or the background logo. Commit the generated `static/optimized/` directory and CSS fingerprints together. The script verifies lossless decoding before publishing its manifest. Missing, changed, or stale alternatives fall back to the original image through `optimized_image_url`; no runtime conversion or new Render build step is required.
