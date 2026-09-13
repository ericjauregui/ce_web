# Team contacts and generated assets

## Source and presentation

Data is `catalog/team.json` (singular), processed in `domains/team.py`. Views are `templates/team.html`, `templates/team_member.html`; digital-card styles are `static/css/styles/team_member.css`.

Use real supplied portraits from `static/team/`. Preserve contact links, Save Contact, sharing, QR, catalog navigation, reels, and footer. Approved styling uses a distinctive portrait border/backdrop integrated with the existing site, not a wholesale redesign or generated replacement face.

Giancarlo/Ari previously had HEIC bytes in `.jpg` files. Safari displayed them; Chromium failed. Verify signatures and decoding, not extensions. Preserve correctly encoded JPEGs and check loaded state/natural dimensions in Chromium after replacement.

## Static branded QR workflow

- Assets: `static/assets/team-qr/{slug}.svg` and `manifest.json`.
- Payload: direct vCard 3.0, not a URL to a `.vcf`. Preserve escaping, CRLF/line folding, and contact data.
- Style: black background, white modules, centered company logo. Branded rendering does not prove camera scannability.
- QR vCards intentionally omit embedded photos to avoid excessive density. Downloadable contacts can be handled separately.
- `ensure_team_qr_assets(team, team_path, static_dir)` compares SHA-256 of team source bytes plus `_QR_GENERATOR_VERSION`, checks expected SVG existence, and returns unchanged assets without re-rendering on a match.
- Generation uses a lock, temporary files and `os.replace`, writes the manifest last, and removes obsolete generated member SVGs. Preserve these safeguards.
- Bump generator version for generator changes or logo artwork changes: the fingerprint does not independently hash the logo.
- Preserve legacy `/team/<slug>/contact-qr.svg` redirects and `/team/<slug>/contact.vcf` downloads.

For source/generator changes, use the existing generation path and inspect asset diffs. Verify a subsequent unchanged load does not rewrite SVGs. Do not move generation to client-side page loads.

## Social previews

`scripts/render_team_social.cjs` renders 1200x630 JPEGs from team data and supplied photos. `social_image`, `photo_position`, and `photo_scale` control destinations/framing. Read `static/assets/team-social/README.md` for runtime requirements.

Regenerate after names, titles, portraits, or framing change. Social assets are generated ahead of deployment, not on requests. Decorative backgrounds may be generated; portraits remain real supplied photos.

## Verification

- `tests.test_team_routes` covers routes/downloads/asset contracts.
- Inspect `tests/e2e/team_business_card.cjs` before using the specialized browser harness; do not assume an old runtime path still exists.
- Check long emails/details at 320px, 390px, and desktop.
- For sharing changes, test native share success/cancel/error, copy fallback/denial, and no-JavaScript links.
- Distinguish rendered QR, automated decoding, physical camera scanning, and actual contact import in reports.
