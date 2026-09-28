# Hero rendering changes — 2026-09-27

Local implementation; not deployed by this task.

## Scope

- Preserve all hero image files, responsive breakpoints, dimensions, crop, blur, overlays, typography and colors.
- Let the selected full-resolution hero decode and pass through a browser paint opportunity before expanding speculative image look-ahead and starting automatic reel playback.
- Keep explicit reel playback and collection navigation available while a hero download is pending; failed images release the gate.
- Render complete initial cart state on the server, avoiding a redundant rewrite of every product card during DOMContentLoaded. Keep initialization for dynamically replaced content.
- Defer the three homepage utility scripts and read collection section positions before writing the measured header height.

Other concurrent storefront changes in this shared checkout are outside this task's scope and have been preserved.

## Visual verification

The before/after hero screenshots at 390 and 1280 CSS pixels have identical decoded pixels. `visual-comparison.json` also records file hashes. This task changed no hero styles or optimized hero assets. Concurrent work also edits shared styles outside the hero rules. The browser test checks full image dimensions and byte-for-byte equality to the source assets at 320, 390, 768 and 1280 CSS pixels, plus cart restoration and direct collection navigation.

## Timing limits

`before-profile.json` and `after-profile.json` retain five local Chromium runs per viewport, using a 4x CPU slowdown and no network throttling. They are diagnostic observations, not a controlled production benchmark: one mobile run in each group did not emit an LCP entry, startup varied substantially, random reel selection varied, and unrelated work was active in this shared checkout. The mobile LCP median among observed entries was 380 ms before and 506 ms after; desktop was 516 ms before and 540 ms after. These measurements do **not** demonstrate an LCP improvement. No production LCP or PageSpeed gain is claimed.

The reliable results are behavioral: the hero gets a decode/paint opportunity before automatic video work, the initial catalog rewrite is eliminated, and the hero appearance and image data are preserved. Production impact needs repeated measurements after deployment.

## Repeatable browser verification

Use the repository's local synthetic E2E runner (no live orders or real email):

```sh
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m tests.run e2e --artifacts-dir .test-artifacts/hero-rendering
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m tests.verify_e2e_artifacts --artifacts-dir .test-artifacts/hero-rendering --check-source
```

The retained run manifest, screenshots, rendered HTML and browser-event records live in `.test-artifacts/hero-rendering/`. Hero-specific scenarios are defined in `tests/e2e/e2e_hero_rendering.py`.

## Validation results

- Initial full run: 35/35 tests passed; artifact hashes verified in `.test-artifacts/hero-rendering/`. Concurrent storefront edits made that run's source fingerprint stale.
- Full rerun on the updated shared checkout: 37 tests, one hero test error and one separate quantity-control layout failure, recorded in `.test-artifacts/hero-rendering-current/`.
- The hero test error was a 30-second timeout in `APIRequestContext.get` while requesting a second copy of a hero image from the single-threaded local server during video streaming. The test now checks the actual image response already delivered to the browser, preserving the byte-for-byte assertion without an extra download.
- Final targeted rerun: all three hero scenarios passed in `.test-artifacts/hero-rendering-confirmed/`, with screenshots, rendered HTML, browser events, and hashes. The new test is `tests/e2e/e2e_hero_rendering.py` and can be repeated with `UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m unittest tests.e2e.e2e_hero_rendering` or as part of the full runner above.
- The broader rerun also flagged `test_mobile_touch_controls_fit_and_have_names`: a quantity control extended outside its product card. This is in the concurrently edited cart-control layout, outside the hero-loading changes. It remains an outstanding broader-suite failure from that run; the entire latest suite is not claimed to be green.
- No physical-device performance or production LCP improvement is claimed. The full suite includes Chromium journeys and its existing WebKit resilience check.

Final hero artifact integrity verification passed. The optional whole-checkout `--check-source` check detected further concurrent edits after the final targeted run: tests/e2e/e2e_ux.py. This does not invalidate the saved test evidence, but it means that evidence is a snapshot rather than verification of every subsequent workspace edit. `git diff --check` also passed.
