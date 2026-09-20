# Trade-show sharing images

The approved GPT Images JIS Fall design is the current `/trade-shows` preview.
The page selects a separate prebuilt image for the event named by `active_event`
in `catalog/trade_shows.json`. JIS Fall, JIS Spring and JCK all have images.

## Update a show

1. Update its entry in `catalog/trade_shows.json`: name, dates, venue, city, booth,
   `hero_image` and `logo_asset`. Change `active_event` when switching shows.
2. Build the previews (only changed events render):

   ```sh
   uv run --extra dev python -m scripts.build_trade_show_social
   ```

3. Inspect the JPEG paths printed by the command, then stage the event data,
   generated images and `static/assets/social/trade-shows/manifest.json` together.
4. Verify, commit and push:

   ```sh
   uv run python -m scripts.build_trade_show_social --check
   uv run python -m unittest tests.test_trade_show_social tests.test_trade_show_routes
   ```

The builder uses the approved layout, the site's actual fonts and logos, and the
configured Miami or Las Vegas background. It typesets exact event details locally;
there is no API key, recurring AI charge or image generation during web requests.
The current approved JIS Fall image remains intact until its inputs change.
`--force --event EVENT_KEY` explicitly replaces even a current approved image with
an image produced by the reusable template.

## One-time developer setup

```sh
uv sync --extra dev
uv run --extra dev playwright install chromium
uv run --extra dev pre-commit install
```

The repository's pre-commit hook runs the builder automatically. If it changes
tracked assets, pre-commit stops the commit for review. Newly generated JPEGs are
untracked until you add them: always stage the printed output paths along with
the manifest and JSON, then retry the commit. The ordinary unit suite also checks
that every configured event has a current preview. Fresh clones must install the
hook; the hook configuration is versioned but Git hooks are local.

An existing Chrome installation can be used instead of bundled Chromium by
setting `CE_CHROME_PATH` to its executable, including when running the hook.
For example, on macOS:

```sh
export CE_CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

## Freshness and caching

The manifest fingerprints displayed details plus dates/address, source image and
logo bytes, font bytes, layout template and renderer version. Changed details,
missing output, altered output, or changed assets require a new image. Unrelated
video/product edits do not. Switching between prebuilt shows needs no render.
Generated filenames include the input fingerprint; `asset_url` also versions the
image URL by content. External social platforms may still require a re-scrape of
an already-shared page.

If someone bypasses checks and publishes stale or missing artwork, the route
falls back to the current show's hero image, without old dates or booth text.
It never serves another show's event card. Previews are generated ahead of
committing, not on Render startup or in a request handler.

## Optional future GPT Images redesign

Keep generated text-free backgrounds reusable whenever possible. A manually
reviewed full image can also be registered after checking every date, name and
booth against the event data:

```sh
uv run python -m scripts.build_trade_show_social \
  --event jis-fall-2026 \
  --adopt-image assets/social/trade-shows-jis-fall-v3.jpg
```

`--adopt-image` requires a 1200 x 630 JPEG and records its current source
fingerprint. Do not use it to dismiss a stale-image warning without actually
updating and visually checking the image. Preserve old images for existing shares.
