# Repository testing rules

- Never write unit tests after you write code.
- Highly prefer E2E tests as the sole testing mechanism. Use them to verify complex features work. At the end of E2E tests, produce a verifiable and repeatable artifact.
- If you must test a system in isolation, first write down all the ways it could fail, then write the code.

Run the browser suite with `UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m tests.run e2e`. It requires Playwright and browser binaries. Each test writes a screenshot, rendered HTML, browser events, and a SHA-256 evidence record. The runner writes `.test-artifacts/e2e/run-manifest.json`; verify it with `UV_CACHE_DIR=/tmp/ce-web-uv-cache uv run python -m tests.verify_e2e_artifacts`. Use `standard` only for narrowly justified isolated checks whose failure cannot be observed reliably in an E2E workflow. Keep E2E data local and synthetic; never submit live orders or send real email from tests.
