# Request limits

Write limits are enabled automatically:

- Checkout POST: 30 attempts per rolling 10 minutes per IP address.
- Cart POST endpoints: 300 updates per rolling minute per IP address, shared across add, set, remove, clear, and note.
- Browsing, static assets, and cart-count reads are not limited.

Rejected requests return HTTP 429 and Retry-After. Checkout shows a branded message; cart APIs return JSON. Rejected writes do not change the cart or create orders. Failed form submissions also count.

Flask-Limiter uses thread-safe process-local memory, matching the current Render startup configuration (one worker, two threads). Counters reset on restart/deploy. Before adding workers or instances, switch to a shared store such as Redis; these limits are basic abuse mitigation, not distributed DDoS protection.

When RENDER=true, the limiter uses the rightmost X-Forwarded-For address, assuming the Render ingress appends the connecting client's address. Elsewhere it uses the socket address and ignores forwarded headers. Confirm that assumption in the deployed proxy chain before relying on per-client limits; additional proxies require revisiting this configuration. Never switch to trusting arbitrary leftmost headers.

Local verification: `uv run python -m unittest tests.test_rate_limiting`. Ordinary tests bypass limits; this focused suite explicitly enables them and resets counters between tests. It does not send real orders or emails.
