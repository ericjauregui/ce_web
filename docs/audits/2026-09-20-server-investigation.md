# Server response investigation — September 20, 2026

The user confirmed a paid Render web-service plan and paid database. No account
settings or paid plan details were queried. Free-service idle sleep is not the
working explanation. No application code, production configuration, or deployment
was changed during this investigation.

## Production comparison

Three sequential curl requests per route, alternating routes each round, with
compression negotiated. Times include DNS, TLS, network, edge and origin processing;
these are not isolated server execution times. All returned HTTP 200.

| Route | Median first-byte time |
|---|---:|
| `/` | 0.899 s |
| `/about` | 0.183 s |
| `/?q=101SB` | 0.162 s |
| `/robots.txt` | 0.166 s |

The same production service handles lightweight dynamic pages and one-product search
much faster than the full catalog. This argues against a fixed one-second Render
platform floor. Hosting CPU allocation can amplify application costs; no claim is
made that hosting contributes zero latency.

## Local profile

The warmed homepage took approximately 152 ms unprofiled in the first measurement.
A separate instrumented request took 346 ms because profiling adds overhead.
In that instrumented request, product_image_attributes accumulated 213 ms and
optimized_image_url 69 ms. get_path_version was called 3,742 times, Path.resolve
4,720 times, stat 13,431 times and lstat 38,804 times. Timings overlap and must not
be added as independent costs.

Fingerprint contents are already cached, but each lookup still resolves paths and
checks filesystem state. Template rendering repeats these validations for the
responsive variants of 313 products. The CSS safety scan is another reusable cost,
but product-image helper work dominates this profile.

The homepage route loads catalog/collection JSON and cookie-session cart quantities;
its inspected normal render path does not query the orders database. This finding
does not assess checkout/database performance or concurrent production traffic.

## Disposable cache experiment

Only the two image helper functions were memoized in a temporary local Python
process. Seven warm requests were measured per case with seeded reels, after cache
warm-up. No source files were patched.

| Cart state | Baseline median | Cached-image median | HTML |
|---|---:|---:|---|
| Empty | 139.5 ms | 16.4 ms | Byte-identical |
| 101SB quantity 2 | 140.8 ms | 20.4 ms | Byte-identical |

This demonstrates an 85–88% reduction in local warm application processing for these
cases, not an equivalent reduction in production TTFB or total page load. The
experiment is not production-ready: cache invalidation, missing/corrupt asset fallback,
URL-prefix context, cache bounds and thread behavior need an explicit implementation.

## Recommended implementation

Cache validated image metadata and generated responsive URL sets per deployment or
manifest version. Retain original-image fallback and explicit invalidation. Keep
cart quantities and all personalized HTML freshly rendered/private; do not enable
shared full-page caching. Validate empty/populated carts, search, asset replacement,
missing/corrupt variants and manifest updates before re-measuring production.

There is concrete application-side work to optimize before considering a hosting or
database upgrade. Render-side request timing/CPU metrics would refine the remaining
hosting contribution after this work is removed.

[Raw measurements](2026-09-20-server-investigation-data.json).
