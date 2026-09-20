# GPT Images trade-show previews

All trade-show artwork is generated with the GPT Images API (`gpt-image-2`).
The original official show logo is composited afterwards into a reserved area.
There is no HTML/browser-renderer fallback and no AI-redrawn organizer logo.

## Normal workflow

1. Edit the relevant event in `catalog/trade_shows.json`. Switch `active_event`
   when moving to another show. Each event chooses its official logo and skyline.
2. Run `git commit`. The installed pre-commit hook calls GPT Images for stale or
   missing previews, exports 1200x630 JPEGs and updates the manifest. Unchanged
   previews cause no API call.
3. If generation changes files, the hook pauses the commit. Inspect the printed
   image paths for correct dates, venue, booth and layout; stage the new JPEGs,
   `.prompt.txt` files and manifest along with the JSON, then retry the commit.

To generate ahead of committing:

```sh
uv run --extra dev --extra imagegen python -m scripts.build_trade_show_social
```

Generate just one event with `--event jis-fall-2026`. `--force` deliberately makes
another billable request even if its image is current. Image generation may take
several minutes. Review is still needed: generated typography can contain errors.

## One-time setup

Set `OPENAI_API_KEY` in your local environment or ignored `.env` file. Never commit
or paste the key. API usage is billed to that key's account.

```sh
uv sync --extra dev --extra imagegen
uv run --extra dev --extra imagegen pre-commit install
```

The builder invokes the installed Codex ImageGen CLI at
`$CODEX_HOME/skills/.system/imagegen/scripts/image_gen.py`, defaulting to
`~/.codex/skills/.system/imagegen/scripts/image_gen.py`. Set `CE_IMAGE_GEN_CLI` if
installed elsewhere. Fresh clones need this CLI, a configured API key, and local
hook installation. No browser is required. API failure/missing credentials blocks
the commit without replacing the existing image with a browser-rendered fallback.
Each completed event is checkpointed so a later failure does not regenerate it.

## Official logos

`catalog/trade_show_logo_sources.json` records the exact official download URL,
source page, verified date and SHA-256 for each logo. Existing JIS Fall, JIS Spring
and white JCK files were re-downloaded from their official sites on 2026-09-20;
the repository bytes matched exactly.

GPT Images leaves a blank area in the right event card. The builder places the
original logo there with alpha transparency and proportional scaling only. It
checks the file hash against the source registry before any billable request.
To add/change a show logo, download it from the official organizer's website,
verify it, and update the source registry with its URL and hash. Do not substitute
AI-generated marks or reinterpret the logo through the image model.

## Freshness and caching

The manifest fingerprints event details, source artwork, official-logo registry,
company logo, approved style reference, prompt and pipeline version. Output hashes
and `generator: gpt-images` / `official_logo_composited` identify the generated
assets. These fields are an audit record, not cryptographic proof of AI provenance.
Changing event details or assets invalidates the old preview. Video/product edits
do not. `asset_url` fingerprints final bytes, and new files have unique names.
Already-shared links may still need an external platform re-scrape.

```sh
uv run python -m scripts.build_trade_show_social --check
uv run python -m unittest tests.test_trade_show_social tests.test_trade_show_routes
```

`--check` and normal site requests never call the API. If someone bypasses checks,
the page uses the current show's text-free hero image rather than a stale card.
Generation runs locally before committing, never on Render startup or requests.
The removed HTML renderer and its old outputs are not used by this workflow.
