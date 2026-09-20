# Member link previews

These are the previous preview assets. Current previews and distinct GPT Images
backdrops live in `../social/`; see `../social/README.md`. The renderer below now
rebuilds the member previews; destinations are in
`catalog/team.json`. The main preview is a separate edit of the original artwork.

The 1200 × 630 JPEGs are rendered from `catalog/team.json` and the original
supplied files in `static/team/`. Faces are not AI-generated or retouched.
Cropping and framing are controlled by `photo_position` and `photo_scale`.

Regenerate after names, titles, portraits or framing change:

```sh
node scripts/render_team_social.cjs
```

This requires Playwright and Chrome. Optionally set `CE_CHROME_PATH`.
The renderer reads each member's `social_image` destination. Assets are generated
ahead of deployment, not during page requests. The site's `asset_url` adds a
file-version query parameter for caches.

`backdrop.png` was created with the built-in GPT Images tool. Final prompt:

> Use case: ads-marketing. Create a premium abstract background ONLY for
> California Earrings digital business card social link previews. Landscape
> 1200:630 composition. Deep near-black obsidian background, restrained warm
> champagne gold highlights, fine art deco curved gold lines framing the far
> upper left and far lower right corners, subtle black satin material and a
> gentle amber halo on the left third. Middle and right two thirds must be very
> dark, quiet negative space for readable typography later. Elegant jeweler
> brand, understated, tasteful. No people, no faces, no jewelry products, no
> lettering, no text, no logos, no watermarks. This will be composited in a browser
> with exact original supplied member photographs and exact typeset text, so
> output only the decorative background.
