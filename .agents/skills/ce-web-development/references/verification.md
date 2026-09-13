# Local verification

## Commands

The project declares Python >=3.13, uses `uv`, and tests with `unittest`, not pytest. Run from repo root. `UV_CACHE_DIR=/tmp/ce-web-uv-cache` is a local workaround for an inaccessible default cache, not an app requirement.

```sh
# Preview using the configured development secret/environment.
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run flask --app app run --host 127.0.0.1 --port 5001

# Choose relevant modules, not necessarily all of these.
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m unittest tests.test_frontend_contracts tests.test_trade_show_routes
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m unittest tests.test_team_routes
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m unittest tests.test_product_routes

# Broader suite when warranted.
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m tests.run standard

# Existing E2E harness when dependencies are installed.
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m tests.run e2e --browser chromium --require-e2e --keep-artifacts
UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m tests.run e2e --browser webkit --require-e2e --keep-artifacts

git diff --check
```

App startup requires `SECRET_KEY`; checkout needs a configured database. Do not print `.env` while diagnosing configuration. Check process/port ownership before starting/stopping a preview.

For orders, choose repository, checkout, email, cache, migration, and database-command tests. PostgreSQL integration is opt-in via `TEST_DATABASE_URL` against a dedicated migrated test database, never production. Inspect E2E database/email mocking before submitting a test order; local UI work does not authorize real staff notifications.

Dev extras include Playwright. Do not assume Node, pytest, browser binaries, or an old app-bundled runtime path exists. Inspect installed tools. Browser dependencies can be skipped by tests; use `--require-e2e` when browser coverage is required.

Artifacts default to `.test-artifacts/e2e/` and are normally cleaned on E2E startup. `--keep-artifacts` preserves prior evidence. Never aim automatic cleanup at unrelated user folders.

## Browser checks

Useful representative widths are 320, 390, 767, 768, and 1280 CSS pixels. Select narrow mobile, relevant breakpoint boundaries, and desktop for the changed surface.

- Capture after layout settles; resizing may briefly yield a scaled/stale screenshot. Check `innerWidth`/geometry if it looks wrong.
- Inspect text bounds, row heights, wrapping, horizontal overflow, and footer clearance. Check empty/populated cart variants when relevant.
- Exercise real UI interactions: menu, category scrolling, pointer drag, native media controls, keyboard. CSS string assertions are insufficient.
- Audio checks: muted start, unmute, deliberate mute, positive volume adjustment, reel advance. Observe state/native control presentation; screenshots do not prove audible output.
- A mobile viewport is not an iPhone camera, physical key, touch device, or actual Safari/Edge executable. Name the tested browser and evidence precisely.
- Restore viewport overrides, close temporary tabs, stop only your preview process, and preserve pre-existing cart/browser state. Prefer isolated synthetic state for mutations.

## Historical failures and limits

Earlier runs found a stale hero-width assertion (`width: clamp(172px, 41vw, 352px);`) and Organization-vs-LocalBusiness schema expectation. These are diagnostic leads, not approved exclusions or guaranteed current failures. Reproduce and compare baseline before calling failures pre-existing; do not weaken tests merely to get green output.

Prior local checks covered Chromium dragging, resized layouts, native audio slider/mute state, rendered PDFs, and QR presentation. They did not prove deployment status or physical phone QR/volume behavior. Recheck current changes; never reuse historical pass counts as current evidence.
