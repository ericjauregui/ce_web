# Isolated test failure inventory

Browser E2E tests are the primary suite. These isolated checks remain because their concrete failure modes cannot be reliably induced or observed through a synthetic customer browser run. Review this inventory before adding another isolated test. Write its failure modes here first, then write the test code.

## PostgreSQL orders and migration

- PostgreSQL can expose an incomplete parent/child order across connections, fail to roll back a parent row after a child insert error, or create duplicate orders when simultaneous requests share an idempotency key. SQLite browser tests do not reproduce PostgreSQL locking and commit behavior.
- A legacy schema migration can leave monetary columns in place, lose customer addresses, or break retry keys. A current-schema checkout cannot exercise the historical pre-upgrade database.
- Direct repository calls can accept nested monetary metadata, malformed quantity values, or unsafe database configuration that the public checkout does not accept. These can corrupt persisted records or expose database details.
- The migration command can claim success when database configuration is missing or print private driver diagnostics on failure. A browser request does not run the deployment command.

## Email and export boundary

- Graph transport can send malformed MIME or break base64 and inline image references; a large order can silently omit product rows. A browser test with a stubbed Graph boundary proves the customer flow but not Graph wire serialization or 100-line completeness.
- Attachment paths can escape the asset directory, and Pacific timestamps can be wrong across daylight saving time. The browser checkout now covers customer text escaping in the intercepted email; ordinary runs do not cover crafted attachment paths or seasonal dates reliably.
- A large image-heavy order can repeatedly embed full-resolution JPEGs, make the private PDF too large to download, fail while resizing source images, or stop producing valid PDF bytes. The ordinary two-item browser checkout does not cover that stress case.

## Image generation and cache

- A manifest can omit or retain stale product, hero, poster, font, or logo versions. Generated derivatives can be distorted, upscaled, corrupt, lose EXIF/ICC metadata, alter pixels unexpectedly, or overwrite originals. A browser can display one selected image without proving all derivatives and source bytes are valid.
- Missing or corrupt derivatives may fail to fall back to originals. The in-process asset cache may retain stale paths after source or manifest changes, allow caller mutation to poison future attributes, ignore a mount prefix, or return inconsistent results under concurrent reads. Browser E2E cannot safely mutate shared files or force those internal races.

## Team assets and trade-show previews

- Duplicate member first names can collide into one route; a portrait-free vCard can contain a broken PHOTO property; unchanged team data can regenerate QR files or changed data can leave them stale. Current production-shaped browser data does not contain those cases, and E2E should not rewrite shared generated assets.
- A changed event or asset can leave a stale social preview; malformed manifests can be accepted; unchanged inputs can trigger a billable generation call; unverified official logos can reach that call; failed API calls can damage a good manifest or leak a secret; compositing can alter the official logo. Browser E2E sees only committed successful output and cannot safely induce these generation failures.
