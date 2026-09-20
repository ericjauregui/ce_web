# Social link previews

1200 x 630 JPEGs matching the site's black/champagne-gold palette, original
logo, Lato copy and Playfair Display headings:

- `site-classic-logo-v3.jpg`: default site preview, set in `templates/base.html`.
  Preserves the original jewelry-rich design with the updated white/gold logo.
  Edited using built-in GPT Images; exact prompt is in
  `site-classic-logo.prompt.txt`, full-resolution output in
  `sources/site-classic-logo.png`. Exported as a 1200 x 630 JPEG.
  `site-v2.jpg` is the unused alternative design, retained for reference.
- `trade-shows-jis-fall-v3.jpg`: approved current JIS Fall preview.
- `trade-shows/`: generated JIS Spring/JCK previews and a freshness manifest.
  The route selects an image matching the active event and its details.
  `trade-shows-v2.jpg` is the unused earlier design, retained for reference.
- `miguel-v2.jpg`, `giancarlo-v2.jpg`, `ari-v2.jpg`: member previews selected by
  `social_image` in `catalog/team.json`.

Twitter uses the same image as Open Graph. Existing `asset_url` fingerprinting
versions the image URLs. Product pages retain their product-specific previews.

Each backdrop was generated separately with the built-in GPT Images tool on
2026-09-20. Exact prompts are recorded in `prompts.json`; original generated
backgrounds are in `backdrops/`. Final images composite the original company
logo and unmodified supplied portraits in Chrome, with exact typeset text.
Portrait resolution is limited by the supplied photographs; faces are neither
regenerated nor retouched.

Regenerate the three member previews without calling the image model again:

```sh
node scripts/render_team_social.cjs
```

Requires Node, Playwright and Chrome. `CE_PLAYWRIGHT_MODULE` may point to an
installed Playwright package; `CE_CHROME_PATH` may select a Chrome executable.
The script leaves the edited main preview intact, waits for fonts and images,
rejects text overflow, and renders static
JPEGs. `social_backdrop`, `photo_position` and `photo_scale` in the team catalog
control each member's composition. Rebuild after changing names, roles or photos.
No image generation runs during web requests. Prior preview assets remain intact.

Trade-show updates use `uv run --extra dev python -m scripts.build_trade_show_social`.
See [the update guide](../../../../docs/trade-show-social-previews.md) for automatic
pre-commit rebuilding, freshness checks, browser setup and changing shows.
