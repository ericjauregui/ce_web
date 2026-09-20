# Quality-first hero optimization — September 20, 2026

Implemented locally, not committed or deployed. Original assets remain unchanged.
The homepage now uses full-resolution quality-98 WebP encodes with libwebp's
`sharp_yuv` conversion. This retains more color-edge fidelity than the default
conversion in the trials. No resize, crop, image generation, viewport changes,
CSS changes, breakpoint changes, background-size changes, or background-position
changes were made for this task. Product image handling is unchanged.

## Asset savings

Comparison is against the previously served lossless WebP, not the original PNG.

| Composition | Unchanged dimensions | Before | After | Reduction |
|---|---|---:|---:|---:|
| Mobile | 1254 x 1254 | 1,847,234 bytes | 696,076 bytes | 62.3% |
| Tablet/original | 1536 x 1024 | 1,587,398 bytes | 597,682 bytes | 62.3% |
| Wide desktop | 2172 x 724 | 1,542,524 bytes | 539,942 bytes | 65.0% |

Full resolution was retained deliberately to prioritize quality at high display
densities. These are lossy encodes, not pixel-identical images. The earlier quality-85
293 KB mobile experiment was not adopted. File-level mean channel differences are
1.02–1.42 on a 0–255 scale; this supports integrity checks but does not itself prove
perceptual equivalence. Dark textures and jewelry-edge crops were visually reviewed,
as were rendered mobile, tablet, desktop, and ultrawide comparisons.

## Geometry and browser verification

Thirteen before/after configurations passed:

- Chromium: 320/3x, 390/3x, 575/2x, 576/2x, 768/2x, 1199/2x, 1200/2x,
  1440/2x, 1920/2x, 2560/1x, 3440/1x (CSS width / device pixel ratio).
- WebKit: 390/3x and 1440/2x.
- Exact equality of hero bounding rectangle, every hero descendant's geometry,
  background size/position/repeat, viewport meta configuration, and overflow state.
- Exactly one selected hero request per fresh page, with the preload and CSS URL
  pointing to the same fingerprinted asset. No JavaScript errors.
- Reviewed rendered comparisons at 390/3x, 768/2x, 1440/2x, and 3440/1x. Mean
  channel differences in these rendered screenshots were 0.20–0.27/255.

These are local browser-engine checks with simulated viewports, not physical-device
or production evidence. Original resolution limits on extremely large displays are
unchanged. Compression changes pixels slightly even when no degradation is apparent
in the reviewed comparisons.

## Tests and maintenance

70 focused tests passed across hero assets, existing image assets, loading assets,
frontend contracts, product routes, and cache controls. New tests verify dimensions,
metadata, fingerprints, conservative image-error bounds, and stale/missing/corrupt
fallback. `git diff --check` passed. The Bootstrap source manifest was rebuilt and
verified current so the existing CSS optimization remains active.

Run `uv run python -m scripts.optimize_heroes` after source hero edits; requires
libwebp's `cwebp` and Pillow only during generation. Review the output visually before
shipping. The runtime helper falls back to the lossless alternative or original if
an optimized asset is unavailable or stale. Both HTML preloads and background custom
properties use this helper. There is no production runtime conversion dependency.

## Evidence

- [Source detail comparisons, original left / optimized right](2026-09-20-hero-details.webp)
- [Browser geometry and asset-selection results](2026-09-20-hero-verification-data.json)
- [Rendered image difference measurements](2026-09-20-hero-pixel-data.json)

## Local timing retest

Three cold Chromium runs per version, 390 x 844 at DPR 1, 1.6 Mbps download, 150 ms latency, and 4x CPU slowdown. Same seeded reels and alternating before/after ordering. Before HTML is a snapshot taken immediately before this task; after HTML is rendered locally. Capture waits at least five seconds after load and for hero LCP. Local HTML/CSS is uncompressed; production already uses Brotli. These are not production or physical-device timings.

| Metric | Before | After | Improvement |
|---|---:|---:|---:|
| Hero paint (LCP) | 23.73 s | 11.09 s | 53.3% |
| Load event | 23.61 s | 14.54 s | 38.4% |

An unrelated workspace edit invalidated the CSS manifest in the last initial sample. The manifest was refreshed and that whole pair repeated; excluded measurements and the reason are retained in the raw evidence. All retained samples use the same reduced Bootstrap stylesheet.

[Timing and network evidence](2026-09-20-hero-timing-data.json).
