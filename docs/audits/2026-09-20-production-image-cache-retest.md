# Production image-cache retest — September 20, 2026

Target: https://californiaearrings.com/

The live Bootstrap manifest matches the committed manifest byte for byte and includes the new image-cache module. Expected commit: `94bc0e8`. This verifies matching deployed source fingerprints, rather than a remote Git SHA endpoint.

Homepage curl time to first byte: previous median **898.925 ms**, current median **294.869 ms**, a **67.2% reduction** over three requests. Current samples: 380.512, 209.691, 294.869 ms.

## Browser medians

Three cold visits per profile, disabled browser cache, real production content. Times in seconds.

| Profile | First content before | First content after | Hero LCP before | Hero LCP after |
| --- | ---: | ---: | ---: | ---: |
| Desktop | 1.684 | 0.876 | 3.640 | 3.100 |
| Fast mobile | 1.752 | 0.720 | 3.832 | 3.060 |
| Slow mobile | 2.196 | 1.496 | 17.916 | 18.088 |

Profiles: desktop 1440x900/DPR1, 20 Mbps/40 ms/1x CPU; mobile 390x844/DPR3, fast 10 Mbps/70 ms/2x CPU, slow 1.6 Mbps/150 ms/4x CPU.

First content improved substantially. Full hero rendering remains above one second; slow-mobile hero LCP is effectively unchanged within run variability. These are observational before/after runs with variable network and randomly selected reels, not a controlled A/B experiment or physical-phone measurements. All samples, including a first-desktop rendering outlier, remain in the evidence.

## Functional checks

Chromium and WebKit passed navigation, catalog anchor, add/increment/clear cart, mini-cart, product detail image, search, drawer keyboard expansion, offscreen video deferral, muted autoplay, reel keyboard activation, manual mute, and reel advancement. Fresh isolated browser contexts were used; no orders or emails were submitted.

All nine timing visits retained 313 products, had no horizontal overflow, and recorded no JavaScript errors or failed HTTP responses. HTML remains `private, no-store, max-age=0` and Brotli compressed. These checks found no functional regressions; they do not establish exhaustive visual equivalence across every device.

Raw evidence: `2026-09-20-production-image-cache-retest-data.json`.
